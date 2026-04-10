#!/usr/bin/env python3
"""
voice_node.py — R2D2 Sample-Based Voice ROS2 Node

Subscribes to /r2d2/voice_intent (std_msgs/String) and plays
authentically R2D2-like sounds using real sample playback.

Topic contract
--------------
Subscriber: /r2d2/voice_intent   std_msgs/String
    {"speak": true, "intent": "task_complete", "emotion": "excited", "intensity": "high"}

Publisher:  /r2d2/voice_playing  std_msgs/String
    {"playing": true, "intent": "task_complete", "emotion": "excited"}

Sample library layout (relative to ROS package install dir):
    sounds/                 <- emotional phrase MP3s (r2d2_sounds/ copied here)
        excited.mp3
        worried.mp3
        ...
    sounds/phonemes/        <- micro phoneme WAVs (from McGill R2D2 Simulator)
        boop.wav
        berp.wav
        ...
"""

import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from r2d2_audio.sample_library import SampleLibrary
from r2d2_audio.utterance_builder import UtteranceBuilder

_PKG_DIR = Path(__file__).parent.parent
DEFAULT_SOUNDS_DIR = str(_PKG_DIR / "sounds")
DEFAULT_ALSA_DEVICE = "plughw:1,0"

VALID_INTENTS = {
    "affirmative", "negative", "question", "greeting", "goodbye",
    "task_complete", "task_failed", "thinking", "warning", "comment",
}
VALID_EMOTIONS = {
    "happy", "sad", "excited", "scared",
    "confused", "curious", "angry", "neutral",
}
VALID_INTENSITIES = {"low", "medium", "high"}


class VoiceNode(Node):

    def __init__(self):
        super().__init__("voice_node")

        self.declare_parameter("sounds_dir", DEFAULT_SOUNDS_DIR)
        self.declare_parameter("alsa_device", DEFAULT_ALSA_DEVICE)
        self.declare_parameter("queue_while_busy", False)

        sounds_dir = self.get_parameter("sounds_dir").value
        self._device = self.get_parameter("alsa_device").value
        self._queue_mode = self.get_parameter("queue_while_busy").value

        # Load samples (blocking, ~1-3s depending on library size)
        self.get_logger().info(f"Loading sample library from {sounds_dir} ...")
        self._library = SampleLibrary(sounds_dir)
        self._builder = UtteranceBuilder(self._library)
        self.get_logger().info(
            f"Voice ready. phrases={len(self._library.available_phrases())} "
            f"phonemes={len(self._library.available_phonemes())} "
            f"device={self._device}"
        )

        self._playing = False
        self._lock = threading.Lock()

        self._sub = self.create_subscription(
            String, "/r2d2/voice_intent", self._on_intent, 10
        )
        self._pub = self.create_publisher(String, "/r2d2/voice_playing", 10)

        # Startup sound
        threading.Thread(
            target=self._play_audio,
            args=(self._builder.build_startup(), "greeting", "excited"),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------

    def _on_intent(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.get_logger().warn(f"Invalid JSON: {exc}")
            return

        if not data.get("speak", True):
            return

        with self._lock:
            if self._playing and not self._queue_mode:
                self.get_logger().debug("Audio busy, dropping intent")
                return

        intent    = data.get("intent",    "comment")
        emotion   = data.get("emotion",   "neutral")
        intensity = data.get("intensity", "medium")

        # Clamp to valid values
        if intent    not in VALID_INTENTS:    intent    = "comment"
        if emotion   not in VALID_EMOTIONS:   emotion   = "neutral"
        if intensity not in VALID_INTENSITIES: intensity = "medium"

        self.get_logger().info(
            f"voice: intent={intent} emotion={emotion} intensity={intensity}"
        )

        audio = self._builder.build(intent, emotion, intensity)
        if audio is None:
            self.get_logger().warn("No audio produced (missing samples?)")
            return

        threading.Thread(
            target=self._play_audio,
            args=(audio, intent, emotion),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------

    def _play_audio(self, audio, intent: str, emotion: str) -> None:
        with self._lock:
            self._playing = True
        self._publish_status(True, intent, emotion)

        try:
            wav_bytes = self._library.render_to_wav_bytes(audio)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp = f.name
            try:
                subprocess.run(
                    ["aplay", "-q", "-D", self._device, tmp],
                    check=True, timeout=15.0
                )
            except subprocess.TimeoutExpired:
                self.get_logger().error("aplay timeout")
            except subprocess.CalledProcessError as exc:
                self.get_logger().error(f"aplay error: {exc}")
            finally:
                os.unlink(tmp)
        except Exception as exc:
            self.get_logger().error(f"Audio error: {exc}")
        finally:
            with self._lock:
                self._playing = False
            self._publish_status(False, "", "")

    def _publish_status(self, playing: bool, intent: str, emotion: str) -> None:
        msg = String()
        msg.data = json.dumps({"playing": playing, "intent": intent, "emotion": emotion})
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
