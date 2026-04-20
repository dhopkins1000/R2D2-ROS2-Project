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
                              Claude Code reads AGENTS.md from here automatically
                              because it is set as the subprocess cwd.
                              Default: /home/r2d2/soul

    effort          (string)  Claude Code --effort level: low, medium, high, max.
                              'low' minimises latency; 'high' for complex reasoning.
                              Default: low

Notes:
    --bare is intentionally NOT used: it disables CLAUDE.md/AGENTS.md
    auto-discovery, which would prevent the soul workspace from loading.

    --tools is intentionally NOT used: passing an empty string causes a
    CLI parse error. Claude Code defaults are fine for our use case.

The Claude Code CLI envelope format (--output-format json):
    {
        "result":     "<model response text>",
        "session_id": "<uuid for --resume>",
        "cost_usd":   0.0,
        ...
    }
The model's actual reply lives in response["result"].
"""

import json
import re
import subprocess
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


TEST_PROMPT = (
    "Latency test. Respond with a valid JSON object matching your "
    "OUTPUT_FORMAT.md schema. Use goal=idle, a curious utterance intent, "
    "and a short lcd line1 greeting."
)

# OUTPUT_FORMAT schema for --json-schema server-side validation.
# Matches OUTPUT_FORMAT.md in the soul workspace.
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

# Defensive fallback: strip markdown fences if the model ignores AGENTS.md.
_FENCE_RE = re.compile(r'^```(?:json)?\s*\n?(.*?)\n?```\s*$', re.DOTALL)


def strip_fences(text: str) -> str:
    m = _FENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


class LlmLatencyTestNode(Node):

    def __init__(self):
        super().__init__('llm_latency_test_node')

        self.declare_parameter('soul_workspace', '/home/r2d2/soul')
        self.declare_parameter('effort', 'low')

        self.soul_workspace = (
            self.get_parameter('soul_workspace').get_parameter_value().string_value
        )
        self.effort = (
            self.get_parameter('effort').get_parameter_value().string_value
        )

        self.publisher_ = self.create_publisher(String, '/r2d2/llm_test', 10)

        self.get_logger().info(f'Soul workspace : {self.soul_workspace}')
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
            # Always log stderr and stdout on failure — critical for debugging
            if result.get('stderr'):
                self.get_logger().error(f'stderr: {result["stderr"]}')
            if result.get('raw_stdout'):
                self.get_logger().error(f'stdout: {result["raw_stdout"]}')
        else:
            self.get_logger().info('--- Results ---')
            self.get_logger().info(
                f'  Total latency  : {result["latency_total_s"]:.2f}s'
            )
            self.get_logger().info(
                f'  Fences stripped: {result["fences_stripped"]}'
            )
            self.get_logger().info(
                f'  Model response : {result["model_response"]}'
            )
            self.get_logger().info(
                f'  Session ID     : {result["session_id"]}'
            )
            self.get_logger().info('Published to /r2d2/llm_test')

    def _call_claude(self, prompt: str, session_id: str | None = None) -> dict:
        """
        Call Claude Code CLI as a subprocess with soul_workspace as cwd.

        Claude Code picks up AGENTS.md automatically from the cwd.
        --bare is intentionally omitted: it disables AGENTS.md auto-discovery.
        --tools is intentionally omitted: empty string causes a CLI parse error.
        """
        cmd = [
            'claude', '-p', prompt,
            '--output-format', 'json',
            '--effort', self.effort,
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
                cwd=self.soul_workspace,
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

        raw_result = envelope.get('result', '')
        clean_result = strip_fences(raw_result)
        fences_stripped = clean_result != raw_result

        if fences_stripped:
            self.get_logger().warn(
                'Model returned markdown fences despite AGENTS.md + --json-schema — stripped.'
            )

        return {
            'latency_total_s': latency,
            'model_response':  clean_result,
            'fences_stripped': fences_stripped,
            'session_id':      envelope.get('session_id', ''),
            'cost_usd':        envelope.get('cost_usd', 0.0),
            'raw_envelope':    envelope,
            'returncode':      proc.returncode,
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
