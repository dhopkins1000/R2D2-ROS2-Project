#!/usr/bin/env python3
"""
ReSpeaker Mic Array V1.0 Node

Publishes:
  /r2d2/audio/doa          (std_msgs/Int16)   - Direction of Arrival 0-359 degrees

USB ID verified: 2886:0007 Seeed Technology Co., Ltd. ReSpeaker Microphone Array

ReSpeaker V1.0 DOA: read via USB control transfer (not bulk endpoint)
  bmRequestType = 0xC0 (vendor, device-to-host)
  bRequest      = 0x00
  wValue        = 0x0008  (DOA register)
  wIndex        = 0x001C
  data_length   = 4 bytes -> int32 angle in degrees
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int16
import usb.core
import usb.util
import sounddevice as sd
import numpy as np
import threading
import struct

# ReSpeaker V1.0 USB IDs - verified via lsusb: 2886:0007
RESPEAKER_VENDOR_ID  = 0x2886
RESPEAKER_PRODUCT_ID = 0x0007

# DOA USB control transfer parameters (ReSpeaker V1.0 protocol)
DOA_REQUEST_TYPE = 0xC0  # vendor, device-to-host
DOA_REQUEST      = 0x00
DOA_VALUE        = 0x0008
DOA_INDEX        = 0x001C
DOA_LENGTH       = 4

# Audio config
SAMPLE_RATE   = 16000
CHANNELS      = 8
PROCESSED_CH  = 0
BLOCK_SIZE    = 1024


class ReSpeakerNode(Node):
    def __init__(self):
        super().__init__('respeaker_node')

        self.doa_pub = self.create_publisher(Int16, '/r2d2/audio/doa', 10)

        self.dev = None
        self._init_usb()

        self.create_timer(0.1, self._poll_doa)

        self._audio_thread = threading.Thread(target=self._start_audio, daemon=True)
        self._audio_thread.start()

        self.get_logger().info('ReSpeaker node started')
        self.get_logger().info(f'Sample rate: {SAMPLE_RATE}Hz, Channels: {CHANNELS}')

    def _init_usb(self):
        """Find ReSpeaker USB device for DOA control transfer."""
        self.dev = usb.core.find(
            idVendor=RESPEAKER_VENDOR_ID,
            idProduct=RESPEAKER_PRODUCT_ID
        )
        if self.dev is None:
            self.get_logger().warn('ReSpeaker USB device not found - DOA unavailable')
            return

        # Only detach interface 0 (HID/control) - leave interface 2 (audio) alone
        try:
            if self.dev.is_kernel_driver_active(0):
                self.dev.detach_kernel_driver(0)
        except usb.core.USBError:
            pass

        try:
            self.dev.set_configuration()
        except usb.core.USBError:
            pass

        self.get_logger().info('ReSpeaker USB device found - DOA via control transfer')

    def _poll_doa(self):
        """Read DOA via USB control transfer (ReSpeaker V1.0 protocol)."""
        if self.dev is None:
            return
        try:
            data = self.dev.ctrl_transfer(
                DOA_REQUEST_TYPE,
                DOA_REQUEST,
                DOA_VALUE,
                DOA_INDEX,
                DOA_LENGTH
            )
            if len(data) == 4:
                angle = struct.unpack('<i', bytes(data))[0]
                if 0 <= angle <= 359:
                    msg = Int16()
                    msg.data = int(angle)
                    self.doa_pub.publish(msg)
                    self.get_logger().debug(f'DOA: {angle}°')
        except usb.core.USBTimeoutError:
            pass
        except Exception as e:
            self.get_logger().warn(
                f'DOA read error: {e}',
                throttle_duration_sec=5.0
            )

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
            while rclpy.ok():
                pass

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            self.get_logger().warn(
                f'Audio status: {status}',
                throttle_duration_sec=5.0
            )
        # Channel 0 = beamformed DSP output
        # processed_audio = indata[:, PROCESSED_CH]
        # TODO: publish as audio topic
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
