#!/usr/bin/env python3
"""
llm_node.py

Listens on /r2d2/llm_input for text prompts, calls the Claude Agent SDK,
and publishes the structured JSON response to /r2d2/llm_response.

ARCHITECTURE — Claude Agent SDK:
    Uses the official claude-agent-sdk Python package which wraps the Claude
    Code CLI correctly, handling the stream-json protocol, session management,
    and auth via the existing Claude Code CLI login (no separate API key needed).

    The SDK is async; ROS2 callbacks are sync. A dedicated asyncio event loop
    runs in a background thread. Each prompt is submitted as a coroutine via
    asyncio.run_coroutine_threadsafe() and awaited synchronously with .result().

    Install: pip install claude-agent-sdk --break-system-packages

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
    soul_workspace   (string)  Absolute path to soul workspace.
                               AGENTS.md is loaded from here.
                               Default: /home/r2d2/soul

    effort           (string)  Effort level: low, medium, high, max.
                               Default: low

    response_timeout (float)   Seconds before giving up on a response.
                               Default: 60.0

    session_persist  (bool)    Reuse session across calls for conversational
                               continuity. Default: False
"""

import asyncio
import json
import threading
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

# Claude Agent SDK — install with:
#   pip install claude-agent-sdk --break-system-packages
try:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
        AssistantMessage,
    )
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


# R2D2 output schema — validated server-side, response lands in structured_output
OUTPUT_SCHEMA = {
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
}


class ClaudeSDKRunner:
    """
    Wraps the async claude-agent-sdk in a background asyncio event loop
    so it can be called synchronously from ROS2 callbacks.

    Uses ClaudeSDKClient for session persistence (conversation continuity)
    or query() for stateless single-shot calls.
    """

    def __init__(self, agents_md: str, effort: str, session_persist: bool, logger):
        self._agents_md = agents_md
        self._effort = effort
        self._session_persist = session_persist
        self._log = logger
        self._client: ClaudeSDKClient | None = None

        # Dedicated asyncio loop in a background thread
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name='claude_sdk_loop',
        )
        self._thread.start()

        # If session_persist, create a persistent client
        if self._session_persist and SDK_AVAILABLE:
            future = asyncio.run_coroutine_threadsafe(
                self._create_client(), self._loop
            )
            try:
                future.result(timeout=30)
                self._log.info('ClaudeSDKClient ready (session_persist=True)')
            except Exception as e:
                self._log.error(f'Failed to create ClaudeSDKClient: {e}')

    async def _create_client(self):
        """Create a persistent ClaudeSDKClient for multi-turn conversations."""
        options = self._build_options()
        self._client = ClaudeSDKClient(options=options)
        await self._client.__aenter__()

    def _build_options(self) -> ClaudeAgentOptions:
        """Build SDK options from configuration."""
        return ClaudeAgentOptions(
            # Load the soul workspace agent definition
            agent=self._agents_md,
            # Effort level maps to Claude Code --effort
            effort=self._effort,
            # Structured JSON output schema
            output_format="json",
            json_schema=OUTPUT_SCHEMA,
            # No tools needed — text/reasoning only
            allowed_tools=[],
        )

    def call(self, prompt: str, timeout: float = 60.0) -> dict:
        """
        Submit a prompt to Claude and wait synchronously for the response.
        Blocks for at most `timeout` seconds.
        """
        if not SDK_AVAILABLE:
            return self._error('claude-agent-sdk not installed — run: pip install claude-agent-sdk --break-system-packages')

        future = asyncio.run_coroutine_threadsafe(
            self._async_call(prompt), self._loop
        )
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            return self._error(f'SDK call timed out after {timeout}s')
        except Exception as e:
            return self._error(f'SDK call failed: {e}')

    async def _async_call(self, prompt: str) -> dict:
        """Async coroutine: send prompt, collect messages, return structured result."""
        from claude_agent_sdk import query

        t_start = time.monotonic()

        try:
            if self._session_persist and self._client:
                # Use persistent client for conversational continuity
                message_iter = self._client.query(prompt=prompt)
            else:
                # Stateless single-shot call
                message_iter = query(
                    prompt=prompt,
                    options=self._build_options(),
                )

            result_msg = None
            async for message in message_iter:
                if isinstance(message, ResultMessage):
                    result_msg = message
                    break  # terminal — done

        except Exception as e:
            return self._error(f'SDK exception: {e}')

        latency = time.monotonic() - t_start

        if result_msg is None:
            return self._error('No ResultMessage received from SDK')

        if result_msg.is_error:
            return self._error(f'Claude returned error: {result_msg.result}')

        # Structured output is in result_msg.structured_output when json_schema is set
        structured = getattr(result_msg, 'structured_output', None)
        if not structured:
            # Fallback: try parsing result as JSON
            try:
                structured = json.loads(result_msg.result or '{}')
            except (json.JSONDecodeError, TypeError):
                structured = {}
            self._log.warn('structured_output missing — fell back to parsing result field')

        # Attach metadata
        usage = getattr(result_msg, 'usage', None) or {}
        structured['_meta'] = {
            'latency_s':    round(latency, 2),
            'cost_usd':     getattr(result_msg, 'total_cost_usd', 0.0) or 0.0,
            'session_id':   getattr(result_msg, 'session_id', '') or '',
            'cache_read':   usage.get('cache_read_input_tokens', 0) if isinstance(usage, dict) else 0,
            'cache_create': usage.get('cache_creation_input_tokens', 0) if isinstance(usage, dict) else 0,
            'error':        None,
        }
        return structured

    def shutdown(self):
        """Clean up the persistent client and stop the event loop."""
        if self._client:
            asyncio.run_coroutine_threadsafe(
                self._client.__aexit__(None, None, None), self._loop
            )
        self._loop.call_soon_threadsafe(self._loop.stop)

    def _error(self, msg: str) -> dict:
        self._log.error(f'LLM error: {msg}')
        return {
            'goal': 'idle',
            'goal_params': {},
            'utterance': {'intent': 'alert_warning', 'intensity': 0.8},
            'lcd': {'line1': 'LLM Fehler', 'line2': 'Siehe Log'},
            'mood_delta': {'curiosity': 0.0, 'boredom': 0.0, 'social': 0.0},
            'memory_write': None,
            'internal_note': msg,
            '_meta': {
                'latency_s': 0.0, 'cost_usd': 0.0, 'session_id': '',
                'cache_read': 0, 'cache_create': 0, 'error': msg,
            },
        }


class LlmNode(Node):

    def __init__(self):
        super().__init__('llm_node')

        self.declare_parameter('soul_workspace',   '/home/r2d2/soul')
        self.declare_parameter('effort',           'low')
        self.declare_parameter('response_timeout', 60.0)
        self.declare_parameter('session_persist',  False)

        soul_workspace  = Path(self.get_parameter('soul_workspace').get_parameter_value().string_value)
        effort          = self.get_parameter('effort').get_parameter_value().string_value
        self._timeout   = self.get_parameter('response_timeout').get_parameter_value().double_value
        session_persist = self.get_parameter('session_persist').get_parameter_value().bool_value
        agents_md       = str(soul_workspace / 'AGENTS.md')

        self._busy = False
        self._pub_response = self.create_publisher(String, '/r2d2/llm_response', 10)
        self._pub_busy     = self.create_publisher(Bool,   '/r2d2/llm_busy',     10)
        self._sub = self.create_subscription(
            String, '/r2d2/llm_input', self._on_input, 10
        )

        self.get_logger().info(f'Soul workspace  : {soul_workspace}')
        self.get_logger().info(f'Agent file      : {agents_md}')
        self.get_logger().info(f'Effort          : {effort}')
        self.get_logger().info(f'Session persist : {session_persist}')
        self.get_logger().info(f'Response timeout: {self._timeout}s')
        self.get_logger().info(f'SDK available   : {SDK_AVAILABLE}')

        if not SDK_AVAILABLE:
            self.get_logger().error(
                'claude-agent-sdk not installed! '
                'Run: pip install claude-agent-sdk --break-system-packages'
            )

        self._runner = ClaudeSDKRunner(
            agents_md, effort, session_persist, self.get_logger()
        )
        self.get_logger().info('LLM node ready — listening on /r2d2/llm_input')

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

        result = self._runner.call(prompt, timeout=self._timeout)
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
        self._runner.shutdown()
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
