#!/usr/bin/env python3
"""
voice_node.py - ROS2 node for R2D2 voice output

Accepts two input formats on /r2d2/voice_intent:

1. R2SC direct (preferred):
   {"speak": true, "r2sc": "W1190-1364:8:21:0.42 | C681:0.07"}

2. Legacy intent/emotion (still supported via intent_mapper):
   {"speak": true, "intent": "task_complete", "emotion": "happy", "intensity": "high"}

Publisher: /r2d2/voice_playing  std_msgs/String
   {"playing": true, "r2sc": "<codec string>"}
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

from r2d2_audio.r2sc_synth import synthesize, to_wav_bytes
from r2d2_audio.intent_mapper import resolve_from_json

# Legacy phrase -> R2SC fallback table
# Used when intent_mapper returns old-style phrase names
_PHRASE_TO_R2SC = {
    "phrase_startup":           "S420-1450:0.40 | W900:8:42:0.55 | T1200:48:0.35 | C1600:0.10",
    "phrase_yes":               "C1600:0.10 | S520-1750:0.20",
    "phrase_yes_enthusiastic":  "S520-1750:0.20 | C1600:0.10 | W900:8:42:0.55",
    "phrase_no":                "W340:75:56:0.28 | S1750-520:0.20",
    "phrase_no_firm":           "W340:75:56:0.28 | W340:75:56:0.28 | S1450-400:0.40",
    "phrase_question":          "C920:0.08 | C1600:0.10 | S520-1750:0.20",
    "phrase_question_confused": "C680:0.12 | S520-1750:0.20 | S1750-520:0.20 | C1600:0.10",
    "phrase_happy":             "W900:8:42:0.55 | T1200:48:0.35 | C1600:0.10",
    "phrase_sad":               "W720-480:5:28:0.60 | S1450-400:0.40",
    "phrase_excited":           "T1200:48:0.35 | S520-1750:0.20 | C1600:0.10 | T1200:48:0.35",
    "phrase_scared":            "T1500:60:0.35 | W340:75:56:0.28 | S1750-520:0.20",
    "phrase_curious":           "C1344:0.27 | W1131-1359:3:42:0.41",
    "phrase_frustrated":        "W340:75:56:0.28 | C680:0.12 | S1750-520:0.20 | W340:75:56:0.28",
    "phrase_greeting":          "S520-1750:0.20 | W900:8:42:0.55 | C1600:0.10",
    "phrase_goodbye":           "W900:8:42:0.55 | S1450-400:0.40",
    "phrase_thinking":          "W740:11:18:0.80 | ~0.08 | C920:0.08 | ~0.08 | C920:0.08",
    "phrase_task_done":         "S520-1750:0.20 | W1190-1364:8:21:0.42 | W900:8:42:0.55",
    "phrase_task_failed":       "S1450-400:0.40 | W340:75:56:0.28 | C680:0.12",
    "phrase_warning":           "C1950:0.14 | ~0.04 | C1950:0.14 | ~0.04 | W340:75:56:0.28",
}

DEFAULT_ALSA_DEVICE = "plughw:1,0"


class VoiceNode(Node):

    def __init__(self):
        super().__init__("voice_node")

        self.declare_parameter("alsa_device", DEFAULT_ALSA_DEVICE)
        self.declare_parameter("queue_while_busy", False)

        self._device = self.get_parameter("alsa_device").value
        self._queue_mode = self.get_parameter("queue_while_busy").value
        self._playing = False
        self._lock = threading.Lock()

        self._sub = self.create_subscription(
            String, "/r2d2/voice_intent", self._on_intent, 10
        )
        self._pub = self.create_publisher(String, "/r2d2/voice_playing", 10)

        self.get_logger().info(
            f"VoiceNode ready (R2SC). device={self._device}  queue={self._queue_mode}"
        )

        # Startup sound
        threading.Thread(
            target=self._play_r2sc,
            args=(_PHRASE_TO_R2SC["phrase_startup"],),
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

        # Prefer direct R2SC string
        if "r2sc" in data:
            r2sc = data["r2sc"]
            self.get_logger().info(f"voice (r2sc): {r2sc}")
        else:
            # Legacy: resolve intent/emotion -> phrase names -> R2SC
            try:
                result = resolve_from_json(msg.data)
                phrases = result.get("phrases", [])
                # Concatenate R2SC for each phrase with a short silence gap
                parts = [
                    _PHRASE_TO_R2SC.get(p, "C920:0.08")
                    for p in phrases
                ]
                r2sc = " | ~0.05 | ".join(parts)
                self.get_logger().info(
                    f"voice (legacy): intent={result.get('intent')} "
                    f"-> phrases={phrases}"
                )
            except Exception as exc:
                self.get_logger().warn(f"Intent resolve failed: {exc}")
                return

        threading.Thread(
            target=self._play_r2sc, args=(r2sc,), daemon=True
        ).start()

    # ------------------------------------------------------------------

    def _play_r2sc(self, r2sc: str) -> None:
        with self._lock:
            self._playing = True
        self._publish_status(playing=True, r2sc=r2sc)

        try:
            wav_bytes = to_wav_bytes(r2sc)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp_path = f.name
            try:
                subprocess.run(
                    ["aplay", "-q", "-D", self._device, tmp_path],
                    check=True, timeout=10.0
                )
            except subprocess.TimeoutExpired:
                self.get_logger().error("aplay timeout")
            except subprocess.CalledProcessError as exc:
                self.get_logger().error(f"aplay error: {exc}")
            finally:
                os.unlink(tmp_path)
        except ValueError as exc:
            self.get_logger().error(f"R2SC parse error: {exc}")
        except Exception as exc:
            self.get_logger().error(f"Synthesis error: {exc}")
        finally:
            with self._lock:
                self._playing = False
            self._publish_status(playing=False, r2sc="")

    def _publish_status(self, playing: bool, r2sc: str) -> None:
        msg = String()
        msg.data = json.dumps({"playing": playing, "r2sc": r2sc})
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
