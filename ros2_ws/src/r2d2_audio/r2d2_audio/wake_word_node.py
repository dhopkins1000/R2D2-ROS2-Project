#!/usr/bin/env python3
"""
Wake Word Detection Node

Listens to ReSpeaker audio and detects "Hey R2D2" wake word
using openWakeWord (local, offline, ~5% CPU on Pi4).

Subscribes:
  (audio directly via sounddevice, not via topic for latency)

Publishes:
  /r2d2/audio/wake_word    (std_msgs/Bool)   - True when wake word detected
  /r2d2/audio/listening    (std_msgs/Bool)   - True = actively listening for command

Requires:
  pip install openwakeword sounddevice
  Wake word model: r2d2.onnx (custom trained or use default)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
import sounddevice as sd
import numpy as np
import threading
import queue

try:
    from openwakeword.model import Model as WakeWordModel
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False

# Audio config - must match ReSpeaker output
SAMPLE_RATE  = 16000
CHANNELS     = 8
PROCESSED_CH = 0       # beamformed channel
CHUNK_SIZE   = 1280    # openWakeWord expects 80ms chunks at 16kHz

# Wake word sensitivity (0.0 - 1.0)
THRESHOLD = 0.5

# After wake word: listen for command for N seconds
LISTEN_TIMEOUT = 5.0


class WakeWordNode(Node):
    def __init__(self):
        super().__init__('wake_word_node')

        # Parameters
        self.declare_parameter('threshold', THRESHOLD)
        self.declare_parameter('listen_timeout', LISTEN_TIMEOUT)
        self.declare_parameter('model_path', '')  # empty = use default model

        self.threshold     = self.get_parameter('threshold').value
        self.listen_timeout = self.get_parameter('listen_timeout').value
        model_path         = self.get_parameter('model_path').value

        # Publishers
        self.wake_pub     = self.create_publisher(Bool, '/r2d2/audio/wake_word', 10)
        self.listen_pub   = self.create_publisher(Bool, '/r2d2/audio/listening', 10)

        # Audio queue
        self.audio_queue = queue.Queue()

        # Load wake word model
        if not OPENWAKEWORD_AVAILABLE:
            self.get_logger().error(
                'openWakeWord not installed! Run: pip install openwakeword'
            )
            return

        self.get_logger().info('Loading wake word model...')
        if model_path:
            self.model = WakeWordModel(wakeword_models=[model_path])
        else:
            # Default: use built-in "hey jarvis" as placeholder
            # Replace with custom r2d2 model when trained
            self.model = WakeWordModel(inference_framework='onnx')
            self.get_logger().warn(
                'No custom wake word model specified. '
                'Using default model. Train a custom "Hey R2D2" model at: '
                'https://github.com/dscripka/openWakeWord'
            )

        self.get_logger().info(f'Wake word threshold: {self.threshold}')
        self.get_logger().info(f'Listen timeout: {self.listen_timeout}s')

        # Start audio capture thread
        self._running = True
        self._audio_thread = threading.Thread(
            target=self._capture_audio, daemon=True
        )
        self._process_thread = threading.Thread(
            target=self._process_audio, daemon=True
        )
        self._audio_thread.start()
        self._process_thread.start()

        self.get_logger().info('Wake word node ready - listening for "Hey R2D2"')

    def _find_respeaker(self):
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if 'ReSpeaker' in d['name'] and d['max_input_channels'] >= 8:
                return i
        return None

    def _capture_audio(self):
        device_idx = self._find_respeaker()
        if device_idx is None:
            self.get_logger().error('ReSpeaker not found for wake word detection')
            return

        def callback(indata, frames, time_info, status):
            # Extract beamformed channel 0, convert to float32 for model
            audio = indata[:, PROCESSED_CH].astype(np.float32)
            self.audio_queue.put(audio)

        with sd.InputStream(
            device=device_idx,
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK_SIZE,
            dtype='int16',
            callback=callback
        ):
            while self._running and rclpy.ok():
                pass

    def _process_audio(self):
        while self._running and rclpy.ok():
            try:
                audio_chunk = self.audio_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # Run wake word inference
            prediction = self.model.predict(audio_chunk)

            # Check all models for detection above threshold
            for model_name, score in prediction.items():
                if score >= self.threshold:
                    self.get_logger().info(
                        f'Wake word detected! Model: {model_name}, Score: {score:.2f}'
                    )
                    # Publish wake word event
                    msg = Bool()
                    msg.data = True
                    self.wake_pub.publish(msg)

                    # Signal: now listening for command
                    listen_msg = Bool()
                    listen_msg.data = True
                    self.listen_pub.publish(listen_msg)

                    # TODO: trigger Whisper STT node for LISTEN_TIMEOUT seconds
                    break

    def destroy_node(self):
        self._running = False
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = WakeWordNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
