#!/usr/bin/env python3
"""
llm_node.py

Listens on /r2d2/llm_input for text prompts and calls Claude Code CLI
for each message received. Publishes the structured JSON response to
/r2d2/llm_response.

Designed to run permanently as a ROS2 node. The voice pipeline (STT)
or any other node can trigger it by publishing to /r2d2/llm_input.
You can also test it manually:

    ros2 topic pub --once /r2d2/llm_input std_msgs/msg/String \
        '{data: "What should I do right now?"}'

Topics:
    Subscribed:  /r2d2/llm_input    std_msgs/String   — prompt text
    Published:   /r2d2/llm_response std_msgs/String   — JSON response
                 /r2d2/llm_busy     std_msgs/Bool     — True while processing

ROS2 Parameters:
    soul_workspace  (string)  Absolute path to the soul workspace.
                              AGENTS.md is loaded from here.
                              Default: /home/r2d2/soul

    effort          (string)  Claude Code effort level: low, medium, high, max.
                              Default: low

    session_persist (bool)    If True, reuse session_id across calls within
                              the same node lifetime (conversational memory).
                              If False, each call is independent.
                              Default: False

Note on ros2 topic echo output:
    ros2 topic echo truncates long strings in terminal display. The full JSON
    is always published intact. Use the node log output to see complete field
    values, or pipe through: ros2 topic echo /r2d2/llm_response | python3 -c
    "import sys,json; [print(json.dumps(json.loads(l.split('data: ')[1]), indent=2))
    for l in sys.stdin if 'data:' in l]"

Response published to /r2d2/llm_response is a JSON string:
    {
        "goal":         "idle",
        "goal_params":  {},
        "utterance":    {"intent": "...", "intensity": 0.5},
        "lcd":          {"line1": "...", "line2": ""},
        "mood_delta":   {"curiosity": 0.0, "boredom": 0.0, "social": 0.0},
        "memory_write": null,
        "internal_note": null,
        "_meta": {
            "latency_s":   3.7,
            "cost_usd":    0.03,
            "session_id":  "...",
            "cache_read":  11700,
            "error":       null
        }
    }
"""

import json
import subprocess
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String


# OUTPUT_FORMAT JSON schema — Claude Code validates the response against this
# and returns it in envelope["structured_output"] as a parsed dict.
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


class LlmNode(Node):

    def __init__(self):
        super().__init__('llm_node')

        self.declare_parameter('soul_workspace', '/home/r2d2/soul')
        self.declare_parameter('effort', 'low')
        self.declare_parameter('session_persist', False)

        self.soul_workspace = Path(
            self.get_parameter('soul_workspace').get_parameter_value().string_value
        )
        self.effort = (
            self.get_parameter('effort').get_parameter_value().string_value
        )
        self.session_persist = (
            self.get_parameter('session_persist').get_parameter_value().bool_value
        )
        self.agents_md = str(self.soul_workspace / 'AGENTS.md')

        self._session_id: str | None = None
        self._busy = False

        self._pub_response = self.create_publisher(String, '/r2d2/llm_response', 10)
        self._pub_busy = self.create_publisher(Bool, '/r2d2/llm_busy', 10)
        self._sub = self.create_subscription(
            String,
            '/r2d2/llm_input',
            self._on_input,
            10,
        )

        self.get_logger().info(f'Soul workspace  : {self.soul_workspace}')
        self.get_logger().info(f'Agent file      : {self.agents_md}')
        self.get_logger().info(f'Effort          : {self.effort}')
        self.get_logger().info(f'Session persist : {self.session_persist}')
        self.get_logger().info('Listening on /r2d2/llm_input — ready.')

    def _on_input(self, msg: String):
        prompt = msg.data.strip()
        if not prompt:
            self.get_logger().warn('Received empty prompt — ignoring.')
            return

        if self._busy:
            self.get_logger().warn(
                f'Still processing previous request — dropping: "{prompt[:60]}"'
            )
            return

        self._busy = True
        self._publish_busy(True)
        self.get_logger().info(f'Prompt received: "{prompt[:80]}"')

        result = self._call_claude(prompt)
        self._publish_response(result)

        self._busy = False
        self._publish_busy(False)

    def _call_claude(self, prompt: str) -> dict:
        session_id = self._session_id if self.session_persist else None

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
                cwd='/tmp',
            )
        except subprocess.TimeoutExpired:
            return self._error_response('subprocess timed out after 60s', t_start)
        except FileNotFoundError:
            return self._error_response(
                'claude binary not found — is Claude Code on PATH?', t_start
            )

        latency = time.monotonic() - t_start

        if proc.returncode != 0:
            self.get_logger().error(
                f'claude exit {proc.returncode}: {proc.stderr.strip()[:200]}'
            )
            return self._error_response(
                f'claude exited with code {proc.returncode}', t_start,
                stderr=proc.stderr.strip()
            )

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            return self._error_response(f'JSON parse failed: {e}', t_start)

        new_session = envelope.get('session_id', '')
        if self.session_persist and new_session:
            self._session_id = new_session

        structured = envelope.get('structured_output')
        if not structured:
            self.get_logger().warn('No structured_output in envelope — check --json-schema.')
            structured = {}

        usage = envelope.get('usage', {})
        structured['_meta'] = {
            'latency_s':    round(latency, 2),
            'cost_usd':     envelope.get('total_cost_usd', 0.0),
            'session_id':   new_session,
            'cache_read':   usage.get('cache_read_input_tokens', 0),
            'cache_create': usage.get('cache_creation_input_tokens', 0),
            'error':        None,
        }

        # Log response fields explicitly — ros2 topic echo truncates long strings
        lcd = structured.get('lcd', {})
        self.get_logger().info('--- LLM Response ---')
        self.get_logger().info(f'  goal      : {structured.get("goal")}')
        self.get_logger().info(f'  intent    : {structured.get("utterance", {}).get("intent")}')
        self.get_logger().info(f'  intensity : {structured.get("utterance", {}).get("intensity")}')
        self.get_logger().info(f'  lcd line1 : {lcd.get("line1", "")}')
        self.get_logger().info(f'  lcd line2 : {lcd.get("line2", "")}')
        self.get_logger().info(f'  mood_delta: {structured.get("mood_delta")}')
        self.get_logger().info(f'  memory    : {structured.get("memory_write")}')
        self.get_logger().info(f'  latency   : {latency:.1f}s')
        self.get_logger().info(f'  cache_read: {usage.get("cache_read_input_tokens", 0)}')

        return structured

    def _publish_response(self, response: dict):
        msg = String()
        msg.data = json.dumps(response)
        self._pub_response.publish(msg)

    def _publish_busy(self, busy: bool):
        msg = Bool()
        msg.data = busy
        self._pub_busy.publish(msg)

    def _error_response(self, error: str, t_start: float, stderr: str = '') -> dict:
        latency = time.monotonic() - t_start
        self.get_logger().error(f'LLM error: {error}')
        return {
            'goal': 'idle',
            'goal_params': {},
            'utterance': {'intent': 'alert_warning', 'intensity': 0.8},
            'lcd': {'line1': 'LLM error — check logs', 'line2': ''},
            'mood_delta': {'curiosity': 0.0, 'boredom': 0.0, 'social': 0.0},
            'memory_write': None,
            'internal_note': error,
            '_meta': {
                'latency_s':    round(latency, 2),
                'cost_usd':     0.0,
                'session_id':   '',
                'cache_read':   0,
                'cache_create': 0,
                'error':        error,
                'stderr':       stderr,
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
