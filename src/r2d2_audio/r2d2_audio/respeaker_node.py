#!/usr/bin/env python3
"""
ReSpeaker Mic Array V1.0 Node

Publishes:
  /r2d2/audio/doa       (std_msgs/Int16)  - Direction of Arrival 0-359 degrees
  /r2d2/audio/vad       (std_msgs/Bool)   - Voice Activity Detection

Hardware: 2886:0007, Raw Firmware (8 channels, no HW DSP)
Mic layout: 6 outer mics on 65mm diameter circle + 1 center mic
DOA method: GCC-PHAT software beamforming on outer 6 mics

Mic channel mapping (verified from Seeed schematic):
  CH0-CH5: outer ring, 60° apart, starting at 0°
  CH6:     center mic
  CH7:     playback reference (not used)

Outer mic positions (radius = 32.5mm):
  CH0:  0°   → ( 32.5,   0.0) mm
  CH1: 60°   → ( 16.3,  28.1) mm
  CH2: 120°  → (-16.3,  28.1) mm
  CH3: 180°  → (-32.5,   0.0) mm
  CH4: 240°  → (-16.3, -28.1) mm
  CH5: 300°  → ( 16.3, -28.1) mm

VAD calibration (measured):
  RMS silence:  ~74
  RMS speech:   ~361
  Threshold:    218  (midpoint)

Requires:
  sudo apt install python3-sounddevice python3-numpy
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int16, Bool
import sounddevice as sd
import numpy as np
import threading

# Audio config
SAMPLE_RATE  = 16000
CHANNELS     = 8
BLOCK_SIZE   = 1024          # ~64ms at 16kHz
DOA_WINDOW   = 16000 // 4    # 250ms window for DOA estimation

# VAD threshold - calibrated for this environment
# silence ~74, speech ~361 → midpoint 218
VAD_ENERGY   = 218

# Speed of sound (m/s)
SPEED_OF_SOUND = 343.0

# Outer mic positions in meters (radius = 32.5mm)
RADIUS = 0.0325
MIC_ANGLES_DEG = [0, 60, 120, 180, 240, 300]
MIC_POSITIONS = np.array([
    [RADIUS * np.cos(np.radians(a)), RADIUS * np.sin(np.radians(a))]
    for a in MIC_ANGLES_DEG
])  # shape: (6, 2)

# Outer mic channel indices (CH0-CH5)
OUTER_MICS = [0, 1, 2, 3, 4, 5]

# All 15 pairs of outer mics for GCC-PHAT
MIC_PAIRS = [(i, j) for i in range(6) for j in range(i + 1, 6)]


class ReSpeakerNode(Node):
    def __init__(self):
        super().__init__('respeaker_node')

        # ROS2 parameter: allow threshold override without rebuild
        self.declare_parameter('vad_threshold', float(VAD_ENERGY))
        self.vad_threshold = self.get_parameter('vad_threshold').value

        # Publishers
        self.doa_pub = self.create_publisher(Int16, '/r2d2/audio/doa', 10)
        self.vad_pub = self.create_publisher(Bool, '/r2d2/audio/vad', 10)

        # Audio ring buffer
        self._audio_buffer = np.zeros((DOA_WINDOW, CHANNELS), dtype=np.float32)
        self._buffer_lock  = threading.Lock()

        # Start audio capture thread
        self._audio_thread = threading.Thread(target=self._start_audio, daemon=True)
        self._audio_thread.start()

        # DOA compute timer (every 250ms)
        self.create_timer(0.25, self._compute_doa)

        self.get_logger().info('ReSpeaker V1.0 node started')
        self.get_logger().info(
            f'GCC-PHAT DOA: {len(MIC_PAIRS)} mic pairs, '
            f'radius={RADIUS*1000:.1f}mm, VAD threshold={self.vad_threshold:.0f}'
        )

    # ------------------------------------------------------------------ #
    #  Audio capture                                                       #
    # ------------------------------------------------------------------ #

    def _find_respeaker(self):
        for i, d in enumerate(sd.query_devices()):
            if 'ReSpeaker' in d['name'] and d['max_input_channels'] >= 8:
                return i
        return None

    def _start_audio(self):
        device_idx = self._find_respeaker()
        if device_idx is None:
            self.get_logger().error('ReSpeaker audio device not found')
            return
        self.get_logger().info(f'Audio device index: {device_idx}')

        with sd.InputStream(
            device=device_idx,
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            dtype='float32',
            callback=self._audio_callback,
        ):
            while rclpy.ok():
                pass

    def _audio_callback(self, indata, frames, time_info, status):
        """Accumulate audio into ring buffer."""
        if status:
            self.get_logger().warn(f'Audio: {status}', throttle_duration_sec=5.0)
        with self._buffer_lock:
            self._audio_buffer = np.roll(self._audio_buffer, -frames, axis=0)
            self._audio_buffer[-frames:] = indata

    # ------------------------------------------------------------------ #
    #  GCC-PHAT DOA computation                                           #
    # ------------------------------------------------------------------ #

    def _gcc_phat(self, sig1: np.ndarray, sig2: np.ndarray) -> float:
        """
        Generalized Cross-Correlation with Phase Transform.
        Returns time delay estimate in samples between sig1 and sig2.
        """
        n = len(sig1) + len(sig2) - 1
        fft_len = 1 << (n - 1).bit_length()

        S1 = np.fft.rfft(sig1, n=fft_len)
        S2 = np.fft.rfft(sig2, n=fft_len)

        denom = np.abs(S1 * np.conj(S2))
        denom[denom < 1e-10] = 1e-10
        R = (S1 * np.conj(S2)) / denom

        cc = np.fft.irfft(R, n=fft_len)

        max_lag = int(np.ceil(2 * RADIUS / SPEED_OF_SOUND * SAMPLE_RATE))
        cc = np.concatenate([cc[-max_lag:], cc[:max_lag + 1]])
        peak = np.argmax(np.abs(cc))
        return float(peak - max_lag)

    def _compute_doa(self):
        """Compute DOA from audio buffer using GCC-PHAT."""
        with self._buffer_lock:
            audio = self._audio_buffer.copy()

        # VAD: RMS energy on channel 0 (center mic, most stable)
        rms = np.sqrt(np.mean(audio[:, 0] ** 2)) * 32768
        vad_active = rms > self.vad_threshold

        vad_msg = Bool()
        vad_msg.data = bool(vad_active)
        self.vad_pub.publish(vad_msg)

        if not vad_active:
            return

        # GCC-PHAT over all mic pairs → accumulate angle votes
        angle_votes = []

        for i, j in MIC_PAIRS:
            sig1 = audio[:, OUTER_MICS[i]]
            sig2 = audio[:, OUTER_MICS[j]]

            delay_sec = self._gcc_phat(sig1, sig2) / SAMPLE_RATE

            mic_dist  = np.linalg.norm(MIC_POSITIONS[i] - MIC_POSITIONS[j])
            max_delay = mic_dist / SPEED_OF_SOUND
            delay_sec = np.clip(delay_sec, -max_delay, max_delay)

            pair_vec   = MIC_POSITIONS[j] - MIC_POSITIONS[i]
            pair_angle = np.degrees(np.arctan2(pair_vec[1], pair_vec[0]))

            if max_delay > 0:
                cos_theta = np.clip(delay_sec / max_delay, -1.0, 1.0)
                theta = np.degrees(np.arccos(cos_theta))
                angle_votes.append((pair_angle + theta) % 360)
                angle_votes.append((pair_angle - theta) % 360)

        if not angle_votes:
            return

        # Circular mean
        angles_rad = np.radians(angle_votes)
        doa_angle  = int(
            np.degrees(np.arctan2(
                np.mean(np.sin(angles_rad)),
                np.mean(np.cos(angles_rad))
            )) % 360
        )

        msg = Int16()
        msg.data = doa_angle
        self.doa_pub.publish(msg)
        self.get_logger().debug(f'DOA: {doa_angle}° RMS={rms:.0f}')


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
