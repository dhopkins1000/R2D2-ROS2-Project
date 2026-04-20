#!/usr/bin/env python3
"""
llm_latency_test_node.py

Measures the end-to-end latency of calling Claude Code CLI as a subprocess.
Fires a single test prompt on startup, logs timing breakdown, and publishes
result to /r2d2/llm_test as a JSON string.

Usage:
    ros2 run r2d2_soul llm_latency_test

    # With explicit parameters:
    ros2 run r2d2_soul llm_latency_test --ros-args \
        -p soul_workspace:=/home/r2d2/soul \
        -p temperature:=0.0

What it measures:
    - Wall-clock time from subprocess.run() to parsed JSON result.
    - Includes: Claude Code startup, network round-trip, inference, response.

Temperature:
    Default is 0.0 (deterministic). For structured JSON output this is correct —
    we want schema compliance, not sampling variation. Personality and character
    come from SOUL.md, not from temperature randomness.
    Valid range: 0.0–1.0. Only change for experimentation.

The Claude Code CLI envelope format (--output-format json):
    {
        "result":     "<model response text>",
        "session_id": "<uuid for --resume>",
        "cost_usd":   0.0,
        ...
    }
The model's actual reply lives in response["result"].

Why cwd matters:
    Claude Code reads AGENTS.md from the current working directory
    automatically — the same way it does in a project folder.
    Setting cwd=soul_workspace ensures the personality and rules are
    always loaded without passing them explicitly in the prompt.
"""

import json
import re
import subprocess
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


# ---------------------------------------------------------------------------
# Test prompt — deliberately minimal so we isolate subprocess + network
# latency, not prompt complexity. The AGENTS.md in the soul workspace
# will shape the response format automatically.
# ---------------------------------------------------------------------------
TEST_PROMPT = (
    "Quick latency test. Respond with a valid JSON object matching your "
    "OUTPUT_FORMAT.md schema. Use goal=idle, a curious utterance intent, "
    "and a short lcd line1 greeting."
)

# Regex to strip markdown code fences — defensive fallback in case the
# model wraps output in ```json ... ``` despite AGENTS.md instructions.
_FENCE_RE = re.compile(r'^```(?:json)?\s*\n?(.*?)\n?```\s*$', re.DOTALL)


def strip_fences(text: str) -> str:
    """Remove markdown code fences if present. Returns raw text unchanged otherwise."""
    m = _FENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


class LlmLatencyTestNode(Node):

    def __init__(self):
        super().__init__('llm_latency_test_node')

        # ROS2 parameters — override on CLI with --ros-args -p key:=value
        self.declare_parameter('soul_workspace', '/home/r2d2/soul')
        self.declare_parameter('temperature', 0.0)

        self.soul_workspace = (
            self.get_parameter('soul_workspace').get_parameter_value().string_value
        )
        self.temperature = (
            self.get_parameter('temperature').get_parameter_value().double_value
        )

        self.publisher_ = self.create_publisher(String, '/r2d2/llm_test', 10)

        self.get_logger().info(f'Soul workspace : {self.soul_workspace}')
        self.get_logger().info(f'Temperature    : {self.temperature}')
        self.get_logger().info('Firing test in 2s...')

        self.timer = self.create_timer(2.0, self._run_test)

    def _run_test(self):
        self.timer.cancel()  # run once only

        self.get_logger().info('--- Claude Code latency test ---')
        self.get_logger().info(f'Prompt: {TEST_PROMPT}')

        result = self._call_claude(TEST_PROMPT)

        msg = String()
        msg.data = json.dumps(result, indent=2)
        self.publisher_.publish(msg)

        if result.get('error'):
            self.get_logger().error(f'FAILED: {result["error"]}')
            if result.get('stderr'):
                self.get_logger().error(f'stderr: {result["stderr"]}')
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

        Claude Code picks up AGENTS.md automatically from the cwd —
        no need to pass the personality content in the prompt.

        Returns a result dict with timing, parsed response, and session_id.
        On error, returns a dict with an 'error' key.
        """
        cmd = [
            'claude', '-p', prompt,
            '--output-format', 'json',
            '--temperature', str(self.temperature),
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
            }

        # Parse the Claude Code JSON envelope
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

        # The model reply is in envelope["result"].
        # Strip markdown fences defensively — AGENTS.md forbids them, but
        # models sometimes ignore that instruction. Log when it happens.
        raw_result = envelope.get('result', '')
        clean_result = strip_fences(raw_result)
        fences_stripped = clean_result != raw_result

        if fences_stripped:
            self.get_logger().warn(
                'Model returned markdown fences despite AGENTS.md prohibition — stripped. '
                'Consider tightening OUTPUT_FORMAT.md or the prompt.'
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
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
