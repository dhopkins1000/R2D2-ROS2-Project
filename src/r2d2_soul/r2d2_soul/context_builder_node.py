#!/usr/bin/env python3
"""
context_builder_node.py

Assembles mood state and episodic memory into a structured natural-language
prompt and publishes it to /r2d2/llm_input.

This node is the bridge between the character layer (mood, memory) and the
LLM reasoning engine. It fires in two modes:

  1. INTERACTIVE  — triggered by a message on /r2d2/llm_trigger (string).
                    The trigger text becomes part of the prompt (e.g. STT output).

  2. AUTONOMOUS   — triggered when mood.boredom exceeds boredom_threshold.
                    R2D2 decides for himself what to do next.

The assembled prompt includes:
  - Current mood vector
  - Time since last interaction
  - Recent episodic memory (last N events)
  - Known places (once SLAM is operational)
  - The trigger text or autonomous prompt

Topics:
    Subscribed:
        /r2d2/mood            std_msgs/String  — JSON mood state
        /r2d2/memory_summary  std_msgs/String  — JSON memory summary
        /r2d2/llm_trigger     std_msgs/String  — text trigger (STT / manual)

    Published:
        /r2d2/llm_input       std_msgs/String  — assembled context prompt
        /r2d2/events          std_msgs/String  — interaction event on trigger

ROS2 Parameters:
    boredom_threshold (float)  Boredom level that triggers autonomous mode.
                               Default: 0.8

    min_trigger_interval (float)  Minimum seconds between autonomous triggers
                                  to prevent LLM spam.
                                  Default: 300.0  (5 minutes)

    max_memory_events (int)    Max recent events included in prompt.
                               Default: 5
"""

import json
import time
from datetime import datetime, timezone

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class ContextBuilderNode(Node):

    def __init__(self):
        super().__init__('context_builder_node')

        self.declare_parameter('boredom_threshold',   0.8)
        self.declare_parameter('min_trigger_interval', 300.0)
        self.declare_parameter('max_memory_events',   5)

        self._boredom_threshold    = self.get_parameter('boredom_threshold').get_parameter_value().double_value
        self._min_trigger_interval = self.get_parameter('min_trigger_interval').get_parameter_value().double_value
        self._max_memory_events    = self.get_parameter('max_memory_events').get_parameter_value().integer_value

        # Latest state from subscribed topics
        self._mood:   dict = {}
        self._memory: dict = {}
        self._last_trigger_time: float = 0.0
        self._last_interaction_time: float = time.monotonic()

        # Publishers
        self._pub_llm    = self.create_publisher(String, '/r2d2/llm_input', 10)
        self._pub_events = self.create_publisher(String, '/r2d2/events',    10)

        # Subscribers
        self.create_subscription(String, '/r2d2/mood',           self._on_mood,    10)
        self.create_subscription(String, '/r2d2/memory_summary', self._on_memory,  10)
        self.create_subscription(String, '/r2d2/llm_trigger',    self._on_trigger, 10)

        # Autonomous boredom check — every 10 seconds
        self.create_timer(10.0, self._check_boredom)

        self.get_logger().info(f'Boredom threshold    : {self._boredom_threshold}')
        self.get_logger().info(f'Min trigger interval : {self._min_trigger_interval}s')
        self.get_logger().info(f'Max memory events    : {self._max_memory_events}')
        self.get_logger().info('context_builder_node ready.')

    # ------------------------------------------------------------------
    # Subscribers
    # ------------------------------------------------------------------

    def _on_mood(self, msg: String):
        try:
            self._mood = json.loads(msg.data)
        except json.JSONDecodeError:
            pass

    def _on_memory(self, msg: String):
        try:
            self._memory = json.loads(msg.data)
        except json.JSONDecodeError:
            pass

    def _on_trigger(self, msg: String):
        """Interactive trigger — STT output or manual ros2 topic pub."""
        text = msg.data.strip()
        if not text:
            return

        self._last_interaction_time = time.monotonic()
        self._last_trigger_time     = time.monotonic()

        # Log as interaction event so memory_node picks it up
        self._publish_event('interaction', summary=f'User said: {text[:80]}')

        prompt = self._build_prompt(trigger_text=text, autonomous=False)
        self._publish_prompt(prompt)
        self.get_logger().info(f'Interactive trigger: "{text[:60]}"')

    # ------------------------------------------------------------------
    # Autonomous boredom trigger
    # ------------------------------------------------------------------

    def _check_boredom(self):
        if not self._mood:
            return  # no mood data yet

        boredom = self._mood.get('boredom', 0.0)
        if boredom < self._boredom_threshold:
            return

        now = time.monotonic()
        if now - self._last_trigger_time < self._min_trigger_interval:
            return  # too soon since last trigger

        self._last_trigger_time = now
        prompt = self._build_prompt(trigger_text=None, autonomous=True)
        self._publish_prompt(prompt)
        self.get_logger().info(
            f'Autonomous trigger fired (boredom={boredom:.2f})'
        )

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    def _build_prompt(self, trigger_text: str | None, autonomous: bool) -> str:
        """Assemble a rich context prompt for the LLM."""
        lines = []

        # --- Mood ---
        if self._mood:
            m = self._mood
            lines.append('Current mood:')
            lines.append(
                f'  energy={m.get("energy", "?"):.2f}  '
                f'curiosity={m.get("curiosity", "?"):.2f}  '
                f'boredom={m.get("boredom", "?"):.2f}  '
                f'social={m.get("social", "?"):.2f}'
            )
        else:
            lines.append('Current mood: unknown')

        # --- Time since last interaction ---
        idle_s  = time.monotonic() - self._last_interaction_time
        idle_min = int(idle_s / 60)
        if idle_min < 1:
            lines.append('Time since last interaction: less than a minute')
        else:
            lines.append(f'Time since last interaction: {idle_min} minute(s)')

        # --- Memory ---
        if self._memory:
            events = self._memory.get('recent_events', [])
            events = events[-self._max_memory_events:]  # most recent N
            total  = self._memory.get('total_events', 0)

            if events:
                lines.append(f'\nRecent memory (last {len(events)} of {total} events):')
                for ev in events:
                    ts      = ev.get('timestamp', '')[:16].replace('T', ' ')
                    loc     = ev.get('location', '')
                    summary = ev.get('summary', ev.get('type', ''))
                    loc_str = f' [{loc}]' if loc else ''
                    lines.append(f'  {ts}{loc_str} — {summary}')
            else:
                lines.append('\nRecent memory: none yet')

            places = self._memory.get('known_places', [])
            if places:
                labels = ', '.join(p['label'] for p in places)
                lines.append(f'Known places: {labels}')

        # --- Trigger ---
        lines.append('')
        if autonomous:
            lines.append(
                'You have been idle for a while and your boredom is high. '
                'Decide what you want to do next on your own initiative. '
                'Be true to your character.'
            )
        else:
            lines.append(f'Daniel just said: "{trigger_text}"')
            lines.append('Respond in character as R2D2.')

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Publishers
    # ------------------------------------------------------------------

    def _publish_prompt(self, prompt: str):
        msg = String()
        msg.data = prompt
        self._pub_llm.publish(msg)

    def _publish_event(self, event_type: str, summary: str = '', location: str = ''):
        event = {'type': event_type}
        if summary:
            event['summary'] = summary
        if location:
            event['location'] = location
        msg = String()
        msg.data = json.dumps(event)
        self._pub_events.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ContextBuilderNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
