#!/usr/bin/env python3
"""
voice_node.py - ROS2 node for R2D2 voice output

Subscribes to /r2d2/voice_intent (std_msgs/String) and plays the
corresponding .wav files via aplay (ALSA). Publishes playback status
to /r2d2/voice_playing.

Topic contract
--------------
Subscriber: /r2d2/voice_intent   std_msgs/String
    JSON as produced by the LLM voice output block:
    {"speak": true, "intent": "task_complete", "emotion": "happy", "intensity": "high"}

Publisher:  /r2d2/voice_playing  std_msgs/String
    {"playing": true, "phrases": ["phrase_task_done", "phrase_happy"]}

Busy policy: incoming intents are dropped while audio is playing.
Set the ROS parameter 'queue_while_busy' to True to queue instead.
"""

import json
import os
import subprocess
import threading
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from r2d2_audio.intent_mapper import resolve_from_json

# Default sounds directory: <package>/sounds/
_PKG_DIR = Path(__file__).parent.parent
DEFAULT_SOUNDS_DIR = str(_PKG_DIR / "sounds")


class VoiceNode(Node):

    def __init__(self):
        super().__init__("voice_node")

        self.declare_parameter("sounds_dir", DEFAULT_SOUNDS_DIR)
        self.declare_parameter("queue_while_busy", False)

        self._sounds_dir = Path(self.get_parameter("sounds_dir").value)
        self._queue_mode = self.get_parameter("queue_while_busy").value

        self._playing = False
        self._lock = threading.Lock()

        self._sub = self.create_subscription(
            String, "/r2d2/voice_intent", self._on_intent, 10
        )
        self._pub = self.create_publisher(String, "/r2d2/voice_playing", 10)

        self.get_logger().info(
            f"VoiceNode ready. sounds_dir={self._sounds_dir}  queue={self._queue_mode}"
        )

        # Startup sound
        threading.Thread(target=self._play_phrases, args=(["phrase_startup"],), daemon=True).start()

    def _on_intent(self, msg: String) -> None:
        try:
            result = resolve_from_json(msg.data)
        except (json.JSONDecodeError, KeyError) as exc:
            self.get_logger().warn(f"Invalid intent JSON: {exc}  raw={msg.data!r}")
            return

        if not result["speak"]:
            return

        with self._lock:
            if self._playing and not self._queue_mode:
                self.get_logger().debug("Audio busy, dropping intent")
                return

        self.get_logger().info(
            f"voice: intent={result['intent']} emotion={result['emotion']} "
            f"intensity={result['intensity']} -> {result['phrases']}"
        )

        threading.Thread(
            target=self._play_phrases, args=(result["phrases"],), daemon=True
        ).start()

    def _play_phrases(self, phrases: list) -> None:
        with self._lock:
            self._playing = True
        self._publish_status(playing=True, phrases=phrases)

        try:
            for phrase in phrases:
                wav = self._sounds_dir / f"{phrase}.wav"
                if not wav.exists():
                    self.get_logger().warn(f"Missing sound file: {wav}")
                    continue
                try:
                    subprocess.run(["aplay", "-q", str(wav)], check=True, timeout=5.0)
                except subprocess.TimeoutExpired:
                    self.get_logger().error(f"aplay timeout: {wav.name}")
                except subprocess.CalledProcessError as exc:
                    self.get_logger().error(f"aplay error for {wav.name}: {exc}")
        finally:
            with self._lock:
                self._playing = False
            self._publish_status(playing=False, phrases=[])

    def _publish_status(self, playing: bool, phrases: list) -> None:
        msg = String()
        msg.data = json.dumps({"playing": playing, "phrases": phrases})
        self._pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = VoiceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
