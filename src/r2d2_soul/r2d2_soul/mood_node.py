#!/usr/bin/env python3
"""
mood_node.py

Maintains R2D2's emotional state vector and publishes it continuously.
State persists across reboots via a JSON file.

Mood vector:
    energy:    0.0–1.0  — mapped from battery level
    curiosity: 0.0–1.0  — spikes on novel stimuli, decays slowly
    boredom:   0.0–1.0  — rises with inactivity, resets on interaction
    social:    0.0–1.0  — spikes after voice interaction, decays slowly

Mood changes via two mechanisms:
    1. Continuous decay/drift (timer-based, runs every second)
    2. Event-driven spikes (subscribes to /r2d2/events)

Events expected on /r2d2/events (JSON string):
    {"type": "interaction"}         — voice/wake-word interaction
    {"type": "novel_object"}        — camera detected something new
    {"type": "navigation_complete"} — finished a movement goal
    {"type": "battery", "level": 0.82} — battery update
    {"type": "mood_delta", "curiosity": 0.1, "boredom": -0.3, ...}
        — direct delta from llm_node response

Topics:
    Published:   /r2d2/mood    std_msgs/String  — JSON mood state (1Hz)
    Subscribed:  /r2d2/events  std_msgs/String  — JSON event triggers

ROS2 Parameters:
    state_file   (string)  Path to JSON state persistence file.
                           Default: /home/r2d2/soul/state/mood.json

    publish_rate (float)   Hz at which /r2d2/mood is published.
                           Default: 1.0

    save_interval (float)  Seconds between state file saves.
                           Default: 30.0
"""

import json
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


# ---------------------------------------------------------------------------
# Default mood state — used only when no state file exists yet
# ---------------------------------------------------------------------------
DEFAULT_MOOD = {
    'energy':    0.8,
    'curiosity': 0.5,
    'boredom':   0.1,
    'social':    0.2,
}

DECAY = {
    'curiosity': 0.0003,
    'boredom':   -0.0010,
    'social':    0.0008,
}

REST = {
    'curiosity': 0.3,
    'boredom':   0.0,
    'social':    0.1,
}

EVENT_SPIKES = {
    'interaction': {
        'boredom':   -0.8,
        'social':    +0.4,
        'curiosity': +0.1,
    },
    'novel_object': {
        'curiosity': +0.3,
        'boredom':   -0.1,
    },
    'navigation_complete': {
        'curiosity': +0.1,
        'boredom':   -0.05,
    },
}


class MoodNode(Node):

    def __init__(self):
        super().__init__('mood_node')

        self.declare_parameter('state_file',    '/home/r2d2/soul/state/mood.json')
        self.declare_parameter('publish_rate',  1.0)
        self.declare_parameter('save_interval', 30.0)

        self._state_file    = Path(self.get_parameter('state_file').get_parameter_value().string_value)
        publish_rate        = self.get_parameter('publish_rate').get_parameter_value().double_value
        self._save_interval = self.get_parameter('save_interval').get_parameter_value().double_value

        self._mood       = self._load_state()
        self._last_save  = time.monotonic()
        self._last_decay = time.monotonic()

        self._pub = self.create_publisher(String, '/r2d2/mood', 10)
        self._sub = self.create_subscription(
            String, '/r2d2/events', self._on_event, 10
        )
        self.create_timer(1.0 / publish_rate, self._tick)

        self.get_logger().info(f'State file   : {self._state_file}')
        self.get_logger().info(f'Publish rate : {publish_rate}Hz')
        self.get_logger().info(f'Save interval: {self._save_interval}s')
        self.get_logger().info(f'Loaded mood  : {self._mood}')

    # ------------------------------------------------------------------
    # Timer tick
    # ------------------------------------------------------------------

    def _tick(self):
        now = time.monotonic()
        dt  = now - self._last_decay
        self._last_decay = now

        self._apply_decay(dt)
        self._publish()

        if now - self._last_save >= self._save_interval:
            self._save_state()
            self._last_save = now

    def _apply_decay(self, dt: float):
        for key, rate in DECAY.items():
            current = self._mood[key]
            if key == 'boredom':
                self._mood['boredom'] = min(1.0, current + abs(rate) * dt)
            else:
                delta = (REST[key] - current) * rate * dt * 10.0
                self._mood[key] = self._clamp(current + delta)

    def _publish(self):
        msg = String()
        msg.data = json.dumps({k: round(v, 3) for k, v in self._mood.items()})
        self._pub.publish(msg)

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    def _on_event(self, msg: String):
        try:
            event = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn(f'Invalid event JSON: {msg.data[:100]}')
            return

        event_type = event.get('type', '')

        if event_type == 'battery':
            level = event.get('level')
            if isinstance(level, (int, float)):
                self._mood['energy'] = self._clamp(float(level))
                self.get_logger().info(f'Energy updated from battery: {level:.2f}')
            return

        if event_type == 'mood_delta':
            for key in ('curiosity', 'boredom', 'social', 'energy'):
                delta = event.get(key, 0.0)
                if delta != 0.0:
                    self._mood[key] = self._clamp(self._mood[key] + delta)
            self.get_logger().info(f'mood_delta applied: {self._mood}')
            self._save_state()
            return

        if event_type in EVENT_SPIKES:
            for key, delta in EVENT_SPIKES[event_type].items():
                self._mood[key] = self._clamp(self._mood[key] + delta)
            self.get_logger().info(f'Event "{event_type}" applied. Mood: {self._mood}')
            self._save_state()
            return

        self.get_logger().warn(f'Unknown event type: "{event_type}"')

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                mood = {k: self._clamp(float(data.get(k, v)))
                        for k, v in DEFAULT_MOOD.items()}
                self.get_logger().info(f'Loaded mood state from {self._state_file}')
                return mood
            except Exception as e:
                self.get_logger().warn(f'Failed to load state file ({e}) — using defaults')
        else:
            self.get_logger().info(f'No state file at {self._state_file} — starting with defaults')
        return dict(DEFAULT_MOOD)

    def _save_state(self):
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(self._mood, indent=2))
        except Exception as e:
            # Use print() here — logger may be unavailable during shutdown
            print(f'[mood_node] Failed to save state: {e}')

    def destroy_node(self):
        # Use print() instead of logger — ROS2 context may already be invalid
        # at this point, which would cause "publisher's context is invalid" warnings
        print('[mood_node] Saving mood state on shutdown...')
        self._save_state()
        super().destroy_node()

    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, value))


def main(args=None):
    rclpy.init(args=args)
    node = MoodNode()
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
