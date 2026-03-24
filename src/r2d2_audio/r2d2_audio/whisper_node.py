#!/usr/bin/env python3
"""
Whisper Speech-to-Text Node

Activated by wake word detection. Records audio for a fixed window
and transcribes using OpenAI Whisper (local, offline).

Subscribes:
  /r2d2/audio/listening    (std_msgs/Bool)   - True = start recording

Publishes:
  /r2d2/audio/command      (std_msgs/String) - Transcribed command

Requires:
  pip install openai-whisper sounddevice
  Model: tiny or base recommended for Pi4 performance
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
import sounddevice as sd
import numpy as np
import threading
import tempfile
import os

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

# Audio config
SAMPLE_RATE    = 16000
CHANNELS       = 8
PROCESSED_CH   = 0
RECORD_SECONDS = 5       # Record window after wake word


class WhisperNode(Node):
    def __init__(self):
        super().__init__('whisper_node')

        # Parameters
        self.declare_parameter('model_size', 'tiny')   # tiny|base|small
        self.declare_parameter('language', 'de')       # de or en
        self.declare_parameter('record_seconds', float(RECORD_SECONDS))

        model_size    = self.get_parameter('model_size').value
        self.language = self.get_parameter('language').value
        self.record_s = self.get_parameter('record_seconds').value

        # Publisher
        self.command_pub = self.create_publisher(
            String, '/r2d2/audio/command', 10
        )

        # Subscriber
        self.create_subscription(
            Bool, '/r2d2/audio/listening', self._listening_cb, 10
        )

        self._recording = False

        if not WHISPER_AVAILABLE:
            self.get_logger().error(
                'Whisper not installed! Run: pip install openai-whisper'
            )
            return

        self.get_logger().info(f'Loading Whisper model: {model_size}...')
        self.model = whisper.load_model(model_size)
        self.get_logger().info(
            f'Whisper ready (model={model_size}, language={self.language})'
        )

    def _find_respeaker(self):
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if 'ReSpeaker' in d['name'] and d['max_input_channels'] >= 8:
                return i
        return None

    def _listening_cb(self, msg: Bool):
        """Triggered when wake word detected."""
        if msg.data and not self._recording:
            thread = threading.Thread(target=self._record_and_transcribe)
            thread.daemon = True
            thread.start()

    def _record_and_transcribe(self):
        """Record audio window and run Whisper transcription."""
        self._recording = True
        self.get_logger().info(
            f'Recording for {self.record_s}s...'
        )

        device_idx = self._find_respeaker()
        if device_idx is None:
            self.get_logger().error('ReSpeaker not found')
            self._recording = False
            return

        # Record audio
        num_samples = int(self.record_s * SAMPLE_RATE)
        audio_data = sd.rec(
            num_samples,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype='float32',
            device=device_idx
        )
        sd.wait()

        # Extract beamformed channel 0
        audio_mono = audio_data[:, PROCESSED_CH]

        # Save to temp file and transcribe
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            tmp_path = f.name

        try:
            import soundfile as sf
            sf.write(tmp_path, audio_mono, SAMPLE_RATE)

            result = self.model.transcribe(
                tmp_path,
                language=self.language,
                fp16=False   # Pi4 has no GPU
            )
            text = result['text'].strip()

            if text:
                self.get_logger().info(f'Command recognized: "{text}"')
                msg = String()
                msg.data = text
                self.command_pub.publish(msg)
            else:
                self.get_logger().info('No speech detected')

        except Exception as e:
            self.get_logger().error(f'Transcription error: {e}')
        finally:
            os.unlink(tmp_path)
            self._recording = False


def main(args=None):
    rclpy.init(args=args)
    node = WhisperNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
