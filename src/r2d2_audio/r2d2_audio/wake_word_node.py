#!/usr/bin/env python3
"""
Wake Word Detection Node for R2D2

Uses openWakeWord (local, offline) to detect a wake word.

Publishes:
  /r2d2/audio/wake_word    (std_msgs/Bool)  - True when wake word detected
  /r2d2/audio/listening    (std_msgs/Bool)  - True = actively listening for command

API verified for installed version:
  Model(wakeword_model_paths=[...], vad_threshold=0.5)
  predict(audio: np.ndarray[int16]) -> dict[str, float]

Available built-in models (onnx):
  alexa, hey_mycroft, hey_jarvis, hey_rhasspy, timer, weather

Default: hey_jarvis (placeholder until custom "Hey R2D2" model is trained)
Custom model training: https://github.com/dscripka/openWakeWord

Audio format: int16, single channel (CH0 from ReSpeaker), 16kHz, 1280 samples/chunk
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
import sounddevice as sd
import numpy as np
import threading
import queue
import os

try:
    from openwakeword.model import Model as WakeWordModel
    import openwakeword
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False

# Audio config
SAMPLE_RATE  = 16000
CHANNELS     = 8
PROCESSED_CH = 0       # CH0 = best quality channel from ReSpeaker
CHUNK_SIZE   = 1280    # 80ms at 16kHz – required by openWakeWord

# Defaults
DEFAULT_THRESHOLD      = 0.5
DEFAULT_LISTEN_TIMEOUT = 5.0


class WakeWordNode(Node):
    def __init__(self):
        super().__init__('wake_word_node')

        # ROS2 parameters
        self.declare_parameter('threshold', DEFAULT_THRESHOLD)
        self.declare_parameter('listen_timeout', DEFAULT_LISTEN_TIMEOUT)
        self.declare_parameter('model_path', '')  # empty = use default hey_jarvis

        self.threshold      = self.get_parameter('threshold').value
        self.listen_timeout = self.get_parameter('listen_timeout').value
        model_path          = self.get_parameter('model_path').value

        # Publishers
        self.wake_pub   = self.create_publisher(Bool, '/r2d2/audio/wake_word', 10)
        self.listen_pub = self.create_publisher(Bool, '/r2d2/audio/listening', 10)

        # Audio queue (int16 chunks)
        self.audio_queue = queue.Queue(maxsize=10)
        self._running    = True

        if not OPENWAKEWORD_AVAILABLE:
            self.get_logger().error('openWakeWord not installed!')
            return

        # Resolve model path
        if model_path:
            model_paths = [model_path]
            self.get_logger().info(f'Using custom model: {model_path}')
        else:
            # Find default built-in hey_jarvis model
            available = openwakeword.get_pretrained_model_paths()
            jarvis_models = [p for p in available if 'hey_jarvis' in p]
            if not jarvis_models:
                self.get_logger().error(
                    f'hey_jarvis model not found. Available: {available}'
                )
                return
            model_paths = [jarvis_models[0]]
            self.get_logger().warn(
                f'No custom model set. Using placeholder: {os.path.basename(model_paths[0])}\n'
                'Train a custom "Hey R2D2" model at: '
                'https://github.com/dscripka/openWakeWord'
            )

        # Load model with built-in Silero VAD
        self.get_logger().info('Loading wake word model...')
        self.model = WakeWordModel(
            wakeword_model_paths=model_paths,
            vad_threshold=0.5   # Silero VAD reduces false positives
        )
        self.get_logger().info(
            f'Wake word model loaded. '
            f'Threshold={self.threshold}, Listen timeout={self.listen_timeout}s'
        )

        # Start threads
        self._audio_thread   = threading.Thread(target=self._capture_audio, daemon=True)
        self._process_thread = threading.Thread(target=self._process_audio, daemon=True)
        self._audio_thread.start()
        self._process_thread.start()

        self.get_logger().info('Wake word node ready')

    # ------------------------------------------------------------------ #
    #  Audio capture                                                       #
    # ------------------------------------------------------------------ #

    def _find_respeaker(self):
        for i, d in enumerate(sd.query_devices()):
            if 'ReSpeaker' in d['name'] and d['max_input_channels'] >= 8:
                return i
        return None

    def _capture_audio(self):
        device_idx = self._find_respeaker()
        if device_idx is None:
            self.get_logger().error('ReSpeaker not found')
            return

        self.get_logger().info(f'Capturing audio from device {device_idx}')

        def callback(indata, frames, time_info, status):
            if status:
                self.get_logger().warn(f'Audio: {status}', throttle_duration_sec=5.0)
            # Extract CH0 as int16 – openWakeWord requires int16
            chunk = indata[:, PROCESSED_CH].copy()
            try:
                self.audio_queue.put_nowait(chunk)
            except queue.Full:
                pass  # drop frame if processing is too slow

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

    # ------------------------------------------------------------------ #
    #  Wake word inference                                                 #
    # ------------------------------------------------------------------ #

    def _process_audio(self):
        while self._running and rclpy.ok():
            try:
                chunk = self.audio_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # openWakeWord expects int16 numpy array
            prediction = self.model.predict(chunk)

            for model_name, score in prediction.items():
                if score >= self.threshold:
                    self.get_logger().info(
                        f'Wake word detected! [{model_name}] score={score:.3f}'
                    )
                    # Publish detection
                    wake_msg = Bool()
                    wake_msg.data = True
                    self.wake_pub.publish(wake_msg)

                    # Signal Whisper node to start listening
                    listen_msg = Bool()
                    listen_msg.data = True
                    self.listen_pub.publish(listen_msg)

                    # Cooldown: clear queue to avoid re-triggering
                    with self.audio_queue.mutex:
                        self.audio_queue.queue.clear()
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
