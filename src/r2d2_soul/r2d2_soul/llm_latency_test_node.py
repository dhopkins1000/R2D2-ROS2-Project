#!/usr/bin/env python3
"""
llm_latency_test_node.py

Measures the end-to-end latency of calling Claude Code CLI as a subprocess.
Fires a single test prompt on startup, logs timing breakdown, and publishes
result to /r2d2/llm_test as a JSON string.

Usage:
    ros2 run r2d2_soul llm_latency_test

    # With custom soul workspace path:
    ros2 run r2d2_soul llm_latency_test --ros-args -p soul_workspace:=/home/r2d2/soul

What it measures:
    - Wall-clock time from subprocess.run() to parsed JSON result.
    - Includes: Claude Code startup, network round-trip, inference, response.

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


class LlmLatencyTestNode(Node):

    def __init__(self):
        super().__init__('llm_latency_test_node')

        # ROS2 parameter — override on CLI with:
        #   --ros-args -p soul_workspace:=/your/path
        self.declare_parameter('soul_workspace', '/home/r2d2/soul')
        self.soul_workspace = (
            self.get_parameter('soul_workspace').get_parameter_value().string_value
        )

        self.publisher_ = self.create_publisher(String, '/r2d2/llm_test', 10)

        self.get_logger().info(
            f'Soul workspace: {self.soul_workspace}'
        )
        self.get_logger().info('Firing test in 2s...')

        # Fire once after a short delay so ROS2 is fully up
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
                f'  Total latency : {result["latency_total_s"]:.2f}s'
            )
            self.get_logger().info(
                f'  Model response: {result["model_response"]}'
            )
            self.get_logger().info(
                f'  Session ID    : {result["session_id"]}'
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
        cmd = ['claude', '-p', prompt, '--output-format', 'json']
        if session_id:
            cmd.extend(['--resume', session_id])

        t_start = time.monotonic()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.soul_workspace,   # <-- this is the key line
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

        return {
            'latency_total_s': latency,
            'model_response':  envelope.get('result', ''),
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
