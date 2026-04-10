#!/usr/bin/env python3
"""
voice_node.py — R2D2 Sample-Based Voice ROS2 Node

Subscribes to /r2d2/voice_intent (std_msgs/String) and plays
authentically R2D2-like sounds using real sample playback.

Topic contract
--------------
Subscriber: /r2d2/voice_intent   std_msgs/String
    {
        "speak":     true,
        "intent":    "comment",
        "emotion":   "excited",
        "intensity": "high",
        "verbosity": 7
    }

    verbosity (1-10): proportional to LLM response length.
        1-2  = very short answer  -> 1-2 phonemes
        3-4  = one sentence       -> 2 phonemes
        5-6  = a few sentences    -> 3 phonemes
        7-8  = paragraph          -> 4 phonemes + phrase tail
        9-10 = long explanation   -> 5-6 phonemes + phrase tail

Publisher:  /r2d2/voice_playing  std_msgs/String
    {"playing": true, "intent": "comment", "emotion": "excited", "verbosity": 7}
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

        threading.Thread(
            target=self._play_audio,
            args=(self._builder.build_startup(), "greeting", "excited", 7),
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
        verbosity = int(data.get("verbosity", 5))

        if intent    not in VALID_INTENTS:     intent    = "comment"
        if emotion   not in VALID_EMOTIONS:    emotion   = "neutral"
        if intensity not in VALID_INTENSITIES: intensity = "medium"
        verbosity = max(1, min(10, verbosity))

        self.get_logger().info(
            f"voice: intent={intent} emotion={emotion} "
            f"intensity={intensity} verbosity={verbosity}"
        )

        audio = self._builder.build(intent, emotion, intensity, verbosity)
        if audio is None:
            self.get_logger().warn("No audio produced (missing samples?)")
            return

        threading.Thread(
            target=self._play_audio,
            args=(audio, intent, emotion, verbosity),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------

    def _play_audio(
        self, audio, intent: str, emotion: str, verbosity: int
    ) -> None:
        with self._lock:
            self._playing = True
        self._publish_status(True, intent, emotion, verbosity)

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
            self._publish_status(False, "", "", 0)

    def _publish_status(
        self, playing: bool, intent: str, emotion: str, verbosity: int
    ) -> None:
        msg = String()
        msg.data = json.dumps({
            "playing":   playing,
            "intent":    intent,
            "emotion":   emotion,
            "verbosity": verbosity,
        })
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
