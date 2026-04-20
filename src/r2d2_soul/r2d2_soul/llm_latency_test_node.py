#!/usr/bin/env python3
"""
llm_latency_test_node.py

Measures the end-to-end latency of calling Claude Code CLI as a subprocess.
Fires a single test prompt on startup, logs timing breakdown, and publishes
result to /r2d2/llm_test as a JSON string.

Usage:
    ros2 run r2d2_soul llm_latency_test

What it measures:
    - t_start  : before subprocess.run()
    - t_proc   : after subprocess returns (includes Claude startup + inference)
    - t_parse  : after JSON parsing

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
import subprocess
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


# ---------------------------------------------------------------------------
# Test prompt — simple enough to get a fast response, but forces JSON output
# so we validate the full round-trip including parsing.
# ---------------------------------------------------------------------------
TEST_PROMPT = (
    "You are R2D2. Respond ONLY with valid JSON, no other text: "
    '{"utterance": "a short R2D2 beep phrase", "mood": "curious"}'
)


class LlmLatencyTestNode(Node):

    def __init__(self):
        super().__init__('llm_latency_test_node')

        self.publisher_ = self.create_publisher(String, '/r2d2/llm_test', 10)

        # Fire once after a short delay so ROS2 is fully up
        self.timer = self.create_timer(2.0, self._run_test)
        self.get_logger().info('LLM latency test node started — firing in 2s...')

    def _run_test(self):
        # Only run once
        self.timer.cancel()

        self.get_logger().info('--- Claude Code latency test ---')
        self.get_logger().info(f'Prompt: {TEST_PROMPT}')

        result = self._call_claude(TEST_PROMPT)

        # Publish and log
        msg = String()
        msg.data = json.dumps(result, indent=2)
        self.publisher_.publish(msg)

        if result.get('error'):
            self.get_logger().error(f'Test FAILED: {result["error"]}')
        else:
            self.get_logger().info('--- Results ---')
            self.get_logger().info(
                f'  Total latency    : {result["latency_total_s"]:.2f}s'
            )
            self.get_logger().info(
                f'  Claude response  : {result["model_response"]}'
            )
            self.get_logger().info(
                f'  Session ID       : {result["session_id"]}'
            )
            self.get_logger().info(
                f'  Return code      : {result["returncode"]}'
            )
            self.get_logger().info('Published to /r2d2/llm_test')

    def _call_claude(self, prompt: str, session_id: str | None = None) -> dict:
        """
        Call Claude Code CLI and return a result dict with timing info.

        Returns:
            {
                'latency_total_s': float,
                'model_response':  str,      # parsed from Claude envelope
                'session_id':      str,      # for --resume in future calls
                'raw_envelope':    dict,     # full Claude JSON output
                'returncode':      int,
            }
        or on error:
            {
                'error':           str,
                'latency_total_s': float,
                'returncode':      int,
                'stderr':          str,
            }
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
                timeout=60,         # hard upper limit — adjust if needed
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
                'error': 'claude binary not found — is Claude Code installed?',
                'latency_total_s': time.monotonic() - t_start,
                'returncode': -1,
                'stderr': '',
            }

        t_proc = time.monotonic()
        latency = t_proc - t_start

        if proc.returncode != 0:
            return {
                'error': f'claude exited with code {proc.returncode}',
                'latency_total_s': latency,
                'returncode': proc.returncode,
                'stderr': proc.stderr.strip(),
            }

        # Parse Claude Code's JSON envelope
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            return {
                'error': f'Failed to parse Claude JSON envelope: {e}',
                'latency_total_s': latency,
                'returncode': proc.returncode,
                'stderr': proc.stderr.strip(),
            }

        # The model's reply is in envelope["result"]
        model_text = envelope.get('result', '')
        session = envelope.get('session_id', '')

        return {
            'latency_total_s': latency,
            'model_response':  model_text,
            'session_id':      session,
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
