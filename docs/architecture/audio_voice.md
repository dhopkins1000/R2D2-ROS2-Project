# Audio & Voice Architecture

## Hardware

**ReSpeaker Mic Array V1.0**
- 7 microphones + XVSM-2000 DSP chip
- 8 output channels via USB audio
  - Channel 0: beamformed, noise-cancelled processed output ← use this
  - Channels 1-6: raw microphone inputs
  - Channel 7: playback reference
- Sample rate: 8000–32000 Hz (use 16000 Hz for Whisper compatibility)
- DOA (Direction of Arrival) readable via USB HID interface (0–359°)
- Hardware noise cancellation and beamforming onboard DSP
- Placement: mounted in R2D2 dome for 360° coverage
- Connected via USB spiral cable through head rotation axis (max ±100°)

**Speaker + Amplifier**
- Mini amplifier in chassis
- Connected to Pi audio output

## ROS2 Node Pipeline

```
ReSpeaker (USB, ch0, 16kHz)
        │
        ▼
  respeaker_node
    ├── /r2d2/audio/doa          (Int16 – 0-359°)
    └── /r2d2/audio/raw_audio    (audio stream)
        │
        ▼
  wake_word_node  (openWakeWord – "Hey R2D2")
    └── /r2d2/audio/wake_word    (Bool)
        │  (only active after wake word)
        ▼
  whisper_node  (local STT, offline)
    └── /r2d2/audio/command      (String)
        │
        ▼
  Behaviour Tree
    ├── DOA → /r2d2/head/cmd     (head rotates toward speaker)
    └── command → action
        │
        ▼
  tts_node
    └── audio output via speaker
```

## Wake Word Detection

**Recommended: openWakeWord**
- Runs locally, no cloud dependency
- ~5% CPU on Pi4 – very lightweight
- Custom wake word trainable ("Hey R2D2")
- Processes short audio frames only, not continuous stream
- Python, easy ROS2 node integration
- https://github.com/dscripka/openWakeWord

Alternative: **Porcupine** (Picovoice) – even more efficient but paid for custom wake words.

## Speech Recognition

**Whisper** (OpenAI, runs locally)
- Model: `tiny` or `base` for Pi4 performance
- Triggered only after wake word → minimal CPU load
- Offline, no cloud
- 16kHz input, compatible with ReSpeaker output

## DOA Head Tracking

The DOA angle from ReSpeaker triggers head rotation:
```
/r2d2/audio/doa (0-359°)
    → behavior_node maps to head rotation angle
    → /r2d2/head/cmd
    → Head ESP32 → A4988 stepper
```
R2D2 automatically turns its head toward the person speaking.
Max rotation: ±100° (limited by spiral cable).

## Gain Tuning

ReSpeaker V1.0 default gain is low. Tune via:
```bash
amixer -c <card_number> scontrols
amixer -c <card_number> sset 'Mic' 80%
```
