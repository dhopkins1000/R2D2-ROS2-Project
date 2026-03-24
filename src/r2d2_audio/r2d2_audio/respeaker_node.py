#!/usr/bin/env python3
"""
ReSpeaker Mic Array V1.0 Node

Publishes:
  /r2d2/audio/doa          (std_msgs/Int16)   - Direction of Arrival 0-359 degrees
  /r2d2/audio/raw_audio    (audio_common_msgs/AudioData) - Processed audio (ch0)

Requires:
  pip install pyusb sounddevice
  udev rule for ReSpeaker HID access
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int16
import usb.core
import usb.util
import sounddevice as sd
import numpy as np
import threading

# ReSpeaker V1.0 USB IDs
RESPEAKER_VENDOR_ID  = 0x2886
RESPEAKER_PRODUCT_ID = 0x0018  # Mic Array V1.0

# Audio config
SAMPLE_RATE   = 16000
CHANNELS      = 8       # 8 channels total
PROCESSED_CH  = 0       # Channel 0 = beamformed output
BLOCK_SIZE    = 1024


class ReSpeakerNode(Node):
    def __init__(self):
        super().__init__('respeaker_node')

        # Publishers
        self.doa_pub = self.create_publisher(Int16, '/r2d2/audio/doa', 10)

        # USB device for DOA
        self.dev = None
        self._init_usb()

        # DOA polling timer (every 100ms)
        self.create_timer(0.1, self._poll_doa)

        # Audio stream in background thread
        self._audio_thread = threading.Thread(target=self._start_audio, daemon=True)
        self._audio_thread.start()

        self.get_logger().info('ReSpeaker node started')
        self.get_logger().info(f'Sample rate: {SAMPLE_RATE}Hz, Channels: {CHANNELS}')

    def _init_usb(self):
        """Find ReSpeaker USB HID device for DOA readout."""
        self.dev = usb.core.find(
            idVendor=RESPEAKER_VENDOR_ID,
            idProduct=RESPEAKER_PRODUCT_ID
        )
        if self.dev is None:
            self.get_logger().warn('ReSpeaker USB device not found - DOA unavailable')
            return
        if self.dev.is_kernel_driver_active(0):
            self.dev.detach_kernel_driver(0)
        self.get_logger().info('ReSpeaker USB device found')

    def _poll_doa(self):
        """Read Direction of Arrival from ReSpeaker HID interface."""
        if self.dev is None:
            return
        try:
            # DOA is in HID report, bytes 4-5 = angle in degrees
            data = self.dev.read(0x84, 64, timeout=100)
            angle = data[4] | (data[5] << 8)
            msg = Int16()
            msg.data = int(angle)
            self.doa_pub.publish(msg)
        except usb.core.USBTimeoutError:
            pass
        except Exception as e:
            self.get_logger().warn(f'DOA read error: {e}')

    def _find_respeaker_device(self):
        """Find the correct sounddevice index for ReSpeaker."""
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if 'ReSpeaker' in d['name'] and d['max_input_channels'] >= 8:
                return i
        return None

    def _start_audio(self):
        """Start audio capture in background thread."""
        device_idx = self._find_respeaker_device()
        if device_idx is None:
            self.get_logger().error('ReSpeaker audio device not found')
            return

        self.get_logger().info(f'Using audio device index: {device_idx}')

        with sd.InputStream(
            device=device_idx,
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            dtype='int16',
            callback=self._audio_callback
        ):
            # Keep thread alive while node is running
            while rclpy.ok():
                pass

    def _audio_callback(self, indata, frames, time_info, status):
        """
        Audio callback - extracts processed channel 0.
        indata shape: (BLOCK_SIZE, CHANNELS)
        """
        if status:
            self.get_logger().warn(f'Audio callback status: {status}')

        # Extract beamformed channel 0
        # processed_audio = indata[:, PROCESSED_CH]  # shape: (BLOCK_SIZE,)
        # TODO: publish as audio topic when audio_common is available
        pass


def main(args=None):
    rclpy.init(args=args)
    node = ReSpeakerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
