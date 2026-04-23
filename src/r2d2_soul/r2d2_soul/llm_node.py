#!/usr/bin/env python3
"""
llm_node.py

Listens on /r2d2/llm_input for text prompts and forwards them to a
persistent Claude Code subprocess. Publishes the structured JSON response
to /r2d2/llm_response.

ARCHITECTURE — Persistent Process (stream-json):
    Previous approach: subprocess.run() per call → Node.js startup ~4s per call.
    New approach:      subprocess.Popen() once at startup, stdin/stdout pipes kept
                       open. Prompts sent as stream-json lines on stdin; responses
                       read from stdout until terminal event received.

    Node.js starts ONCE. Subsequent calls cost only network + inference time.
    Expected latency after first call: 3–6s (warm cache) vs 17–22s before.

    Claude Code stream-json protocol:
        stdin  ← {"type": "user", "message": "<prompt>"}\\n
        stdout → {"type": "assistant", ...}\\n   (intermediate, ignored)
                 {"type": "result", "subtype": "success", ...}\\n  (terminal)
                 {"type": "result", "subtype": "error",   ...}\\n  (terminal)

Usage:
    ros2 run r2d2_soul llm_node

    # Test without voice node:
    ros2 topic pub --once /r2d2/llm_input std_msgs/msg/String \\
        '{data: "Wie ist dein Status?"}'

Topics:
    Subscribed:  /r2d2/llm_input    std_msgs/String  — prompt text
    Published:   /r2d2/llm_response std_msgs/String  — JSON response dict
                 /r2d2/llm_busy     std_msgs/Bool    — True while processing

ROS2 Parameters:
    soul_workspace   (string)  Absolute path to soul workspace.
                               AGENTS.md is loaded from here.
                               Default: /home/r2d2/soul

    effort           (string)  Claude Code effort level: low, medium, high, max.
                               Default: low

    response_timeout (float)   Seconds to wait for a response before giving up
                               and restarting the process.
                               Default: 60.0

    max_restarts     (int)     Max consecutive process restarts before giving up.
                               Default: 3
"""

import json
import queue
import subprocess
import threading
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String


OUTPUT_JSON_SCHEMA = json.dumps({
    "type": "object",
    "required": ["goal", "goal_params", "utterance", "lcd", "mood_delta"],
    "properties": {
        "goal":        {"type": "string"},
        "goal_params": {"type": "object"},
        "utterance": {
            "type": "object",
            "properties": {
                "intent":    {"type": ["string", "null"]},
                "intensity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        },
        "lcd": {
            "type": "object",
            "properties": {
                "line1": {"type": "string", "maxLength": 40},
                "line2": {"type": "string", "maxLength": 40},
            },
        },
        "mood_delta": {
            "type": "object",
            "properties": {
                "curiosity": {"type": "number"},
                "boredom":   {"type": "number"},
                "social":    {"type": "number"},
            },
        },
        "memory_write":  {"type": ["string", "null"]},
        "internal_note": {"type": ["string", "null"]},
    },
})

_PROCESS_DEAD = object()


class ClaudeProcessManager:
    """
    Manages a single persistent Claude Code subprocess.

    The process runs with --input-format stream-json --output-format stream-json,
    keeping Node.js alive between calls. Two background threads read stdout and
    stderr continuously. Terminal responses (type=result) are delivered via Queue.

    Thread safety: send() is NOT reentrant. LlmNode enforces this via busy flag.
    """

    def __init__(self, agents_md: str, effort: str, logger):
        self._agents_md = agents_md
        self._effort = effort
        self._log = logger
        self._proc: subprocess.Popen | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._response_queue: queue.Queue = queue.Queue()
        self._restart_count = 0

    def start(self) -> bool:
        """Launch the Claude subprocess. Returns True on success."""
        cmd = [
            'claude',
            '-p',                           # non-interactive / print mode (flag only, no arg)
            '--output-format', 'stream-json',
            '--input-format',  'stream-json',
            '--effort',        self._effort,
            '--agent',         self._agents_md,
            '--json-schema',   OUTPUT_JSON_SCHEMA,
        ]
        self._log.info(f'Launching: {" ".join(cmd[:6])} ...')
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,   # line-buffered
                cwd='/tmp',
            )
        except FileNotFoundError:
            self._log.error('claude binary not found — is Claude Code installed and on PATH?')
            return False

        self._stdout_thread = threading.Thread(
            target=self._stdout_loop, daemon=True, name='claude_stdout'
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_loop, daemon=True, name='claude_stderr'
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

        self._log.info(f'Claude process started (PID {self._proc.pid})')
        return True

    def send(self, prompt: str, timeout: float = 60.0) -> dict:
        """
        Send a prompt to the running Claude process and wait for the response.
        Returns a result dict or an error dict on failure.
        """
        if self._proc is None or self._proc.poll() is not None:
            rc = self._proc.poll() if self._proc else 'None'
            self._log.warn(f'Claude process not running (returncode={rc}) — restarting...')
            if not self._restart():
                return self._error('Process dead and restart failed')

        t_start = time.monotonic()

        msg = json.dumps({'type': 'user', 'message': prompt}) + '\n'
        try:
            self._proc.stdin.write(msg)
            self._proc.stdin.flush()
        except BrokenPipeError:
            self._log.error('stdin pipe broken — restarting process')
            self._restart()
            return self._error('Broken pipe — process restarted')

        try:
            envelope = self._response_queue.get(timeout=timeout)
        except queue.Empty:
            self._log.error(f'Response timeout after {timeout}s — restarting process')
            self._kill()
            self._restart()
            return self._error(f'Timeout after {timeout}s')

        latency = time.monotonic() - t_start

        if envelope is _PROCESS_DEAD:
            return self._error('Process died while waiting for response')

        if envelope.get('is_error') or envelope.get('subtype') == 'error':
            err = envelope.get('result', 'unknown error')
            return self._error(f'Claude error: {err}')

        structured = envelope.get('structured_output')
        if not structured:
            self._log.warn(
                f'No structured_output in envelope — schema mismatch? '
                f'result field: "{str(envelope.get("result", ""))[:100]}"'
            )
            structured = {}

        usage = envelope.get('usage', {})
        structured['_meta'] = {
            'latency_s':    round(latency, 2),
            'cost_usd':     envelope.get('total_cost_usd', 0.0),
            'session_id':   envelope.get('session_id', ''),
            'cache_read':   usage.get('cache_read_input_tokens', 0),
            'cache_create': usage.get('cache_creation_input_tokens', 0),
            'error':        None,
        }
        self._restart_count = 0
        return structured

    def shutdown(self):
        if self._proc and self._proc.poll() is None:
            self._log.info('Terminating Claude process...')
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    # ------------------------------------------------------------------
    # Background threads
    # ------------------------------------------------------------------

    def _stdout_loop(self):
        """Read stdout line by line. Put type=result envelopes into queue."""
        try:
            for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    self._log.debug(f'stdout non-JSON: {line[:120]}')
                    continue

                if obj.get('type') == 'result':
                    self._response_queue.put(obj)
                # intermediate streaming chunks (assistant, content_block, etc.) ignored

        except Exception as e:
            self._log.error(f'stdout reader exception: {e}')
        finally:
            self._log.warn('Claude stdout closed — process has exited')
            self._response_queue.put(_PROCESS_DEAD)

    def _stderr_loop(self):
        """Read stderr and log every line — critical for diagnosing process death."""
        try:
            for line in self._proc.stderr:
                line = line.strip()
                if line:
                    self._log.warn(f'[claude stderr] {line}')
        except Exception as e:
            self._log.error(f'stderr reader exception: {e}')

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _kill(self):
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass

    def _restart(self, max_restarts: int = 3) -> bool:
        self._restart_count += 1
        if self._restart_count > max_restarts:
            self._log.error(f'Max restarts ({max_restarts}) exceeded — giving up')
            return False
        backoff = min(2 ** self._restart_count, 30)
        self._log.warn(
            f'Restarting Claude process (attempt {self._restart_count}, backoff {backoff}s)...'
        )
        time.sleep(backoff)
        while not self._response_queue.empty():
            try:
                self._response_queue.get_nowait()
            except queue.Empty:
                break
        return self.start()

    def _error(self, msg: str) -> dict:
        return {
            'goal': 'idle',
            'goal_params': {},
            'utterance': {'intent': 'alert_warning', 'intensity': 0.8},
            'lcd': {'line1': 'LLM Fehler', 'line2': 'Siehe Log'},
            'mood_delta': {'curiosity': 0.0, 'boredom': 0.0, 'social': 0.0},
            'memory_write': None,
            'internal_note': msg,
            '_meta': {
                'latency_s':    0.0,
                'cost_usd':     0.0,
                'session_id':   '',
                'cache_read':   0,
                'cache_create': 0,
                'error':        msg,
            },
        }


class LlmNode(Node):

    def __init__(self):
        super().__init__('llm_node')

        self.declare_parameter('soul_workspace',   '/home/r2d2/soul')
        self.declare_parameter('effort',           'low')
        self.declare_parameter('response_timeout', 60.0)
        self.declare_parameter('max_restarts',     3)

        soul_workspace = Path(
            self.get_parameter('soul_workspace').get_parameter_value().string_value
        )
        effort   = self.get_parameter('effort').get_parameter_value().string_value
        self._timeout = self.get_parameter('response_timeout').get_parameter_value().double_value
        agents_md = str(soul_workspace / 'AGENTS.md')

        self._busy = False
        self._pub_response = self.create_publisher(String, '/r2d2/llm_response', 10)
        self._pub_busy     = self.create_publisher(Bool,   '/r2d2/llm_busy',     10)
        self._sub = self.create_subscription(
            String, '/r2d2/llm_input', self._on_input, 10
        )

        self.get_logger().info(f'Soul workspace  : {soul_workspace}')
        self.get_logger().info(f'Agent file      : {agents_md}')
        self.get_logger().info(f'Effort          : {effort}')
        self.get_logger().info(f'Response timeout: {self._timeout}s')

        self._claude = ClaudeProcessManager(agents_md, effort, self.get_logger())
        self.get_logger().info('Starting persistent Claude process...')
        if not self._claude.start():
            self.get_logger().error(
                'Failed to start Claude process — will retry on first prompt'
            )
        else:
            self.get_logger().info('Claude process ready — listening on /r2d2/llm_input')

    def _on_input(self, msg: String):
        prompt = msg.data.strip()
        if not prompt:
            self.get_logger().warn('Empty prompt — ignoring.')
            return
        if self._busy:
            self.get_logger().warn(f'Busy — dropping: "{prompt[:60]}"')
            return

        self._busy = True
        self._publish_busy(True)
        self.get_logger().info(f'Prompt: "{prompt[:80]}"')

        result = self._claude.send(prompt, timeout=self._timeout)
        self._log_response(result)
        self._publish_response(result)

        self._busy = False
        self._publish_busy(False)

    def _log_response(self, r: dict):
        lcd  = r.get('lcd', {})
        meta = r.get('_meta', {})
        self.get_logger().info('--- LLM Response ---')
        self.get_logger().info(f'  goal      : {r.get("goal")}')
        self.get_logger().info(f'  intent    : {r.get("utterance", {}).get("intent")}')
        self.get_logger().info(f'  intensity : {r.get("utterance", {}).get("intensity")}')
        self.get_logger().info(f'  lcd line1 : {lcd.get("line1", "")}')
        self.get_logger().info(f'  lcd line2 : {lcd.get("line2", "")}')
        self.get_logger().info(f'  mood_delta: {r.get("mood_delta")}')
        self.get_logger().info(f'  memory    : {r.get("memory_write")}')
        self.get_logger().info(f'  latency   : {meta.get("latency_s")}s')
        self.get_logger().info(f'  cache_read: {meta.get("cache_read")}')
        if meta.get('error'):
            self.get_logger().error(f'  error     : {meta["error"]}')

    def _publish_response(self, response: dict):
        msg = String()
        msg.data = json.dumps(response)
        self._pub_response.publish(msg)

    def _publish_busy(self, busy: bool):
        msg = Bool()
        msg.data = busy
        self._pub_busy.publish(msg)

    def destroy_node(self):
        self._claude.shutdown()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = LlmNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        node.get_logger().error(f'Unexpected error: {e}')
    finally:
        if node:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
