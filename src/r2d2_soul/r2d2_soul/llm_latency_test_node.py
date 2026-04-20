#!/usr/bin/env python3
"""
llm_latency_test_node.py

Measures the end-to-end latency of calling Claude Code CLI as a subprocess.
Fires a single test prompt on startup, logs timing breakdown, and publishes
result to /r2d2/llm_test as a JSON string.

Usage:
    ros2 run r2d2_soul llm_latency_test

    # Override parameters:
    ros2 run r2d2_soul llm_latency_test --ros-args \
        -p soul_workspace:=/home/r2d2/soul \
        -p effort:=low

ROS2 Parameters:
    soul_workspace  (string)  Path to the soul workspace directory.
                              AGENTS.md is referenced from here as the agent file.
                              Default: /home/r2d2/soul

    effort          (string)  Claude Code --effort level: low, medium, high, max.
                              'low' minimises latency; 'high' for complex reasoning.
                              Default: low

Agent loading:
    --agent <path> accepts an absolute path to an AGENTS.md file directly.
    No --agents JSON construction needed. Claude Code loads the file and all
    files it references (SOUL.md, IDENTITY.md, etc.) from the soul workspace.

    Context is cached server-side after the first call — subsequent calls
    within the cache window are significantly faster (cache_read_input_tokens).

Envelope format with --json-schema:
    When --json-schema is passed, Claude Code puts the validated response in
    envelope["structured_output"] (a dict), NOT in envelope["result"] (string).
    Both fields are read; structured_output takes priority.

    {
        "result":           "",                  <- empty when schema is used
        "structured_output": {"goal": "idle"},   <- actual response
        "session_id":       "<uuid>",
        "total_cost_usd":   0.0,
        ...
    }
"""

import json
import subprocess
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


TEST_PROMPT = (
    "Latency test. Respond using your OUTPUT_FORMAT.md schema. "
    "Use goal=idle, a curious utterance intent, and a short lcd line1 greeting."
)

# OUTPUT_FORMAT JSON schema for --json-schema server-side validation.
# When used, Claude Code returns a parsed dict in envelope["structured_output"].
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


class LlmLatencyTestNode(Node):

    def __init__(self):
        super().__init__('llm_latency_test_node')

        self.declare_parameter('soul_workspace', '/home/r2d2/soul')
        self.declare_parameter('effort', 'low')

        self.soul_workspace = Path(
            self.get_parameter('soul_workspace').get_parameter_value().string_value
        )
        self.effort = (
            self.get_parameter('effort').get_parameter_value().string_value
        )
        self.agents_md = str(self.soul_workspace / 'AGENTS.md')

        self.publisher_ = self.create_publisher(String, '/r2d2/llm_test', 10)

        self.get_logger().info(f'Soul workspace : {self.soul_workspace}')
        self.get_logger().info(f'Agent file     : {self.agents_md}')
        self.get_logger().info(f'Effort         : {self.effort}')
        self.get_logger().info('Firing test in 2s...')

        self.timer = self.create_timer(2.0, self._run_test)

    def _run_test(self):
        self.timer.cancel()
        self.get_logger().info('--- Claude Code latency test ---')
        result = self._call_claude(TEST_PROMPT)

        msg = String()
        msg.data = json.dumps(result, indent=2)
        self.publisher_.publish(msg)

        if result.get('error'):
            self.get_logger().error(f'FAILED: {result["error"]}')
            if result.get('stderr'):
                self.get_logger().error(f'stderr: {result["stderr"]}')
            if result.get('raw_stdout'):
                self.get_logger().error(f'stdout: {result["raw_stdout"]}')
        else:
            self.get_logger().info('--- Results ---')
            self.get_logger().info(
                f'  Total latency      : {result["latency_total_s"]:.2f}s'
            )
            self.get_logger().info(
                f'  Cache read tokens  : {result.get("cache_read_tokens", "n/a")}'
            )
            self.get_logger().info(
                f'  Cache create tokens: {result.get("cache_create_tokens", "n/a")}'
            )
            self.get_logger().info(
                f'  Model response     : {result["model_response"]}'
            )
            self.get_logger().info(
                f'  Session ID         : {result["session_id"]}'
            )
            self.get_logger().info('Published to /r2d2/llm_test')

    def _call_claude(self, prompt: str, session_id: str | None = None) -> dict:
        """
        Call Claude Code CLI with --agent pointing directly to AGENTS.md.

        With --json-schema, the response lands in envelope["structured_output"]
        as an already-parsed dict — not in envelope["result"]. We check both.
        """
        cmd = [
            'claude', '-p', prompt,
            '--output-format', 'json',
            '--effort', self.effort,
            '--agent', self.agents_md,
            '--json-schema', OUTPUT_JSON_SCHEMA,
        ]
        if session_id:
            cmd.extend(['--resume', session_id])

        t_start = time.monotonic()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.soul_workspace),
            )
        except subprocess.TimeoutExpired:
            return {
                'error': 'subprocess timed out after 60s',
                'latency_total_s': time.monotonic() - t_start,
                'returncode': -1,
                'stderr': '',
            }
        except FileNotFoundError:
            return {
                'error': 'claude binary not found — is Claude Code installed and on PATH?',
                'latency_total_s': time.monotonic() - t_start,
                'returncode': -1,
                'stderr': '',
            }
        except PermissionError:
            return {
                'error': f'soul_workspace not accessible: {self.soul_workspace}',
                'latency_total_s': time.monotonic() - t_start,
                'returncode': -1,
                'stderr': '',
            }

        latency = time.monotonic() - t_start

        if proc.returncode != 0:
            return {
                'error': f'claude exited with code {proc.returncode}',
                'latency_total_s': latency,
                'returncode': proc.returncode,
                'stderr': proc.stderr.strip(),
                'raw_stdout': proc.stdout.strip()[:500],
            }

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            return {
                'error': f'Failed to parse Claude JSON envelope: {e}',
                'raw_stdout': proc.stdout[:500],
                'latency_total_s': latency,
                'returncode': proc.returncode,
                'stderr': proc.stderr.strip(),
            }

        # With --json-schema, response is in structured_output (dict).
        # Without --json-schema, response is in result (string).
        structured = envelope.get('structured_output')
        if structured:
            model_response = structured  # already a parsed dict
        else:
            model_response = envelope.get('result', '')

        usage = envelope.get('usage', {})

        return {
            'latency_total_s':     latency,
            'model_response':      model_response,
            'session_id':          envelope.get('session_id', ''),
            'cost_usd':            envelope.get('total_cost_usd', 0.0),
            'cache_read_tokens':   usage.get('cache_read_input_tokens', 0),
            'cache_create_tokens': usage.get('cache_creation_input_tokens', 0),
            'raw_envelope':        envelope,
            'returncode':          proc.returncode,
        }


def main(args=None):
    rclpy.init(args=args)
    node = LlmLatencyTestNode()
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
