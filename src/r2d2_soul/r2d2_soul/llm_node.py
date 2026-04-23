#!/usr/bin/env python3
"""
llm_node.py

Listens on /r2d2/llm_input for text prompts, calls gemini-cli in headless
mode, and publishes the structured JSON response to /r2d2/llm_response.

BACKEND: gemini-cli (google-gemini/gemini-cli)
    - Install: npm install -g @google/gemini-cli
    - Auth:    export GOOGLE_API_KEY=<key from aistudio.google.com>
    - GEMINI.md in /home/r2d2/soul is loaded automatically as system context

WHY gemini-cli OVER PYTHON SDK:
    gemini-cli is a full agent — tool calls, web search, MCP servers,
    and file context are built in. The Python SDK is inference-only and
    would require reimplementing all of that manually.

LATENCY:
    gemini-cli has Node.js startup overhead per call (~2-4s).
    Gemini models are fast — inference itself is typically <2s.
    Total expected: 4-8s per call, significantly less than Claude Code.
    Improvement possible later via SDK or persistent session approaches.

OUTPUT FORMAT:
    gemini-cli --output-format json returns:
        {"response": "<model text>", "stats": {...}}
    The model text must be valid JSON (enforced via GEMINI.md instructions).
    We parse response → JSON, with fence stripping as fallback.

Usage:
    ros2 run r2d2_soul llm_node

    # Test:
    ros2 topic pub --once /r2d2/llm_input std_msgs/msg/String \\
        '{data: "Wie ist dein Status?"}'

Topics:
    Subscribed:  /r2d2/llm_input    std_msgs/String  — prompt text
    Published:   /r2d2/llm_response std_msgs/String  — JSON response dict
                 /r2d2/llm_busy     std_msgs/Bool    — True while processing

ROS2 Parameters:
    soul_workspace   (string)  Path to soul workspace. GEMINI.md is read
                               from here as gemini-cli system context.
                               Default: /home/r2d2/soul

    model            (string)  Gemini model to use.
                               Default: gemini-2.5-flash

    response_timeout (float)   Seconds before giving up.
                               Default: 60.0
"""

import json
import re
import subprocess
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String


# Strip markdown code fences — defensive fallback if model ignores GEMINI.md
_FENCE_RE = re.compile(r'^```(?:json)?\s*\n?(.*?)\n?```\s*$', re.DOTALL)


def strip_fences(text: str) -> str:
    m = _FENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


class LlmNode(Node):

    def __init__(self):
        super().__init__('llm_node')

        self.declare_parameter('soul_workspace',   '/home/r2d2/soul')
        self.declare_parameter('model',            'gemini-2.5-flash')
        self.declare_parameter('response_timeout', 60.0)

        self._workspace = Path(
            self.get_parameter('soul_workspace').get_parameter_value().string_value
        )
        self._model   = self.get_parameter('model').get_parameter_value().string_value
        self._timeout = self.get_parameter('response_timeout').get_parameter_value().double_value

        self._busy = False
        self._pub_response = self.create_publisher(String, '/r2d2/llm_response', 10)
        self._pub_busy     = self.create_publisher(Bool,   '/r2d2/llm_busy',     10)
        self._sub = self.create_subscription(
            String, '/r2d2/llm_input', self._on_input, 10
        )

        self.get_logger().info(f'Soul workspace  : {self._workspace}')
        self.get_logger().info(f'GEMINI.md       : {self._workspace / "GEMINI.md"}')
        self.get_logger().info(f'Model           : {self._model}')
        self.get_logger().info(f'Response timeout: {self._timeout}s')
        self.get_logger().info('Listening on /r2d2/llm_input — ready.')

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

        result = self._call_gemini(prompt)
        self._log_response(result)
        self._publish_response(result)

        self._busy = False
        self._publish_busy(False)

    def _call_gemini(self, prompt: str) -> dict:
        """
        Call gemini-cli in headless mode and return a structured response dict.

        gemini-cli reads GEMINI.md from cwd automatically as system context.
        The --yolo flag auto-approves all tool actions (required for headless).
        The response JSON lands in envelope['response'] as a string.
        """
        cmd = [
            'gemini',
            '-p', prompt,
            '--output-format', 'json',
            '--model', self._model,
            '--yolo',   # auto-approve all tool actions — required for headless
        ]

        t_start = time.monotonic()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=str(self._workspace),  # GEMINI.md loaded from here
            )
        except subprocess.TimeoutExpired:
            return self._error(f'gemini timed out after {self._timeout}s')
        except FileNotFoundError:
            return self._error(
                'gemini binary not found — install with: '
                'npm install -g @google/gemini-cli'
            )

        latency = time.monotonic() - t_start

        if proc.returncode != 0:
            stderr = proc.stderr.strip()[:300]
            self.get_logger().error(f'gemini exit {proc.returncode}: {stderr}')
            return self._error(f'gemini exited with code {proc.returncode}: {stderr}')

        # Parse the gemini-cli JSON envelope
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            self.get_logger().error(f'Failed to parse gemini envelope: {e}')
            self.get_logger().error(f'Raw stdout: {proc.stdout[:300]}')
            return self._error(f'Envelope JSON parse failed: {e}')

        # The model's response is in envelope['response'] as a string
        # GEMINI.md instructs the model to output valid JSON there
        response_text = envelope.get('response', '')
        clean_text = strip_fences(response_text)

        if clean_text != response_text:
            self.get_logger().warn(
                'Model wrapped response in markdown fences despite GEMINI.md — stripped.'
            )

        try:
            structured = json.loads(clean_text)
        except json.JSONDecodeError as e:
            self.get_logger().error(f'Response is not valid JSON: {e}')
            self.get_logger().error(f'Raw response: {response_text[:300]}')
            return self._error(f'Response JSON parse failed: {e}')

        # Extract token stats from gemini envelope for monitoring
        stats = envelope.get('stats', {})
        models_stats = stats.get('models', {})
        total_cached = sum(
            m.get('tokens', {}).get('cached', 0)
            for m in models_stats.values()
        )
        total_tokens = sum(
            m.get('tokens', {}).get('total', 0)
            for m in models_stats.values()
        )

        structured['_meta'] = {
            'latency_s':    round(latency, 2),
            'cost_usd':     0.0,   # free tier — no cost tracking
            'model':        self._model,
            'total_tokens': total_tokens,
            'cached_tokens': total_cached,
            'error':        None,
        }
        return structured

    def _log_response(self, r: dict):
        lcd  = r.get('lcd', {})
        meta = r.get('_meta', {})
        self.get_logger().info('--- LLM Response ---')
        self.get_logger().info(f'  goal         : {r.get("goal")}')
        self.get_logger().info(f'  intent       : {r.get("utterance", {}).get("intent")}')
        self.get_logger().info(f'  intensity    : {r.get("utterance", {}).get("intensity")}')
        self.get_logger().info(f'  lcd line1    : {lcd.get("line1", "")}')
        self.get_logger().info(f'  lcd line2    : {lcd.get("line2", "")}')
        self.get_logger().info(f'  mood_delta   : {r.get("mood_delta")}')
        self.get_logger().info(f'  memory       : {r.get("memory_write")}')
        self.get_logger().info(f'  latency      : {meta.get("latency_s")}s')
        self.get_logger().info(f'  total_tokens : {meta.get("total_tokens")}')
        self.get_logger().info(f'  cached_tokens: {meta.get("cached_tokens")}')
        if meta.get('error'):
            self.get_logger().error(f'  error        : {meta["error"]}')

    def _publish_response(self, response: dict):
        msg = String()
        msg.data = json.dumps(response)
        self._pub_response.publish(msg)

    def _publish_busy(self, busy: bool):
        msg = Bool()
        msg.data = busy
        self._pub_busy.publish(msg)

    def _error(self, msg: str) -> dict:
        self.get_logger().error(f'LLM error: {msg}')
        return {
            'goal': 'idle',
            'goal_params': {},
            'utterance': {'intent': 'alert_warning', 'intensity': 0.8},
            'lcd': {'line1': 'LLM Fehler', 'line2': 'Siehe Log'},
            'mood_delta': {'curiosity': 0.0, 'boredom': 0.0, 'social': 0.0},
            'memory_write': None,
            'internal_note': msg,
            '_meta': {
                'latency_s': 0.0, 'cost_usd': 0.0, 'model': self._model,
                'total_tokens': 0, 'cached_tokens': 0, 'error': msg,
            },
        }


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
