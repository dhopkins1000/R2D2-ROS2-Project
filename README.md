# R2D2 – ROS2 Robotics Project

A real-world R2D2 build (~75cm) running ROS2 Jazzy Jalisco on a Raspberry Pi 4 (8GB).

## Hardware

**Main Computer**
- Raspberry Pi 4 (8GB) – Ubuntu 24.04 Server (ARM64, headless)

**Sensors & Cameras**
- ASUS Xtion Pro – USB 3D depth camera (openni2)
- USB Webcam – front camera
- HMC5883L (GY-273) – I2C 3-axis compass / IMU
- Ultrasonic sensor (chassis) – I2C, downward-angled for stair detection
- Ultrasonic sensor (head) – I2C, forward distance

**Drive System**
- MD25 motor controller – differential drive, 2x DC motors with encoders
- Chassis ESP32 (LOLIN D32) – micro-ROS node (motors, odometry, IMU, stair sensor, SSD1306 OLED)

**Head**
- Head ESP32 (LOLIN D32) – micro-ROS node (stepper motor, HT16K33 RGB 8x8 matrix, SerLCD 40x2, ultrasonic)
- A4988 stepper driver – head rotation

**Audio & Voice**
- ReSpeaker Mic Array V1.0 (USB, 7 mics + XVSM-2000 DSP)
  - 8 channels (ch0 = beamformed output), 16kHz max 32kHz
  - DOA (Direction of Arrival) via USB HID
  - Hardware noise cancellation + beamforming onboard
- Speaker + mini amplifier in chassis

## Software Stack

| Layer | Technology |
|---|---|
| OS | Ubuntu 24.04 Server (ARM64) |
| ROS2 | Jazzy Jalisco (LTS) |
| Visualization | Foxglove Studio (Mac) via WebSocket |
| ESP32 Firmware | micro-ROS (Jazzy) via PlatformIO |
| Navigation | Nav2 + slam_toolbox |
| Speech Recognition | Whisper (local, offline) |
| Wake Word | Porcupine or openWakeWord |
| Development | VS Code Remote SSH + OpenCode |

## ROS2 Workspace Structure

```
~/ros2_ws/src/
  r2d2_bringup/      # Launch files + config (cameras, foxglove)
  r2d2_description/  # URDF/XACRO robot model
  r2d2_base/         # Chassis ESP32 interface (MD25, odometry)
  r2d2_head/         # Head ESP32 interface (stepper, display, LEDs)
  r2d2_perception/   # Camera processing, object detection
  r2d2_navigation/   # Nav2 config + maps
  r2d2_behavior/     # Behaviour trees, state machine
  r2d2_audio/        # Voice input (ReSpeaker), speech recognition, TTS output

esp32/
  r2d2_chassis_esp32/  # PlatformIO project – Chassis ESP32 firmware
```

## Connection Architecture

```
Raspberry Pi 4
├── Chassis ESP32      (USB Serial – micro-ROS)
│   ├── MD25           (UART – motors + encoders)
│   ├── HMC5883L       (I2C Bus 0 – compass/IMU)
│   ├── Ultrasonic     (I2C Bus 0 – stair sensor)
│   └── SSD1306 OLED   (SPI – status display)
├── Head ESP32         (Bluetooth – micro-ROS)
│   ├── A4988 stepper  (GPIO STEP/DIR – head rotation)
│   ├── HT16K33        (I2C Bus 0 – RGB 8x8 matrix)
│   ├── SerLCD 40x2    (UART + 3.3V logic level – display)
│   └── Ultrasonic     (I2C Bus 1 – distance sensor)
├── ASUS Xtion Pro     (USB – depth + RGB camera)
├── USB Webcam         (USB – front camera)
└── ReSpeaker Mic Array V1.0  (USB – voice input + DOA)
```

## Voice / Audio Node Architecture (r2d2_audio)

```
ReSpeaker (USB, ch0 beamformed, 16kHz)
         │
         ▼
  respeaker_node
    ├── /r2d2/audio/doa          (Int16 – speaking direction 0-359°)
    └── /r2d2/audio/raw_audio    (Audio stream)
         │
         ▼
  wake_word_node  ("Hey R2D2")
    └── /r2d2/audio/wake_word    (Bool)
         │
         ▼
  whisper_node  (local STT, offline)
    └── /r2d2/audio/command      (String – recognized command)
         │
         ▼
  Behaviour Tree
    ├── DOA → /r2d2/head/cmd     (Head rotates toward speaker)
    └── Command → action         (Navigate, speak, emote...)
         │
         ▼
  tts_node  (Text-to-Speech)
    └── /r2d2/audio/speak        (String → audio output via speaker)
```

## Status

- [x] Ubuntu 24.04 + ROS2 Jazzy installed
- [x] r2d2_bringup: Xtion Pro + Webcam + Foxglove Bridge (systemd service)
- [x] Foxglove Studio connected from Mac
- [x] GitHub repo cleaned up, ROS2 workspace pushed
- [x] micro-ROS Agent built from source (~/microros_ws)
- [x] PlatformIO installed on Pi + ESP32 project skeleton created
- [x] ReSpeaker Mic Array V1.0 recognized (USB, 8ch, 16kHz)
- [ ] micro-ROS firmware build for ESP32 (micro_ros_platformio Jazzy/ARM64 – WIP)
- [ ] Chassis ESP32 wiring + first topic published
- [ ] MD25 drive node (r2d2_base)
- [ ] Nav2 + SLAM
- [ ] Head ESP32
- [ ] r2d2_audio: ReSpeaker node + wake word + Whisper STT
- [ ] Behaviour trees

## Notes

### micro-ROS on Jazzy/ARM64
`micro_ros_platformio` has known issues building on Jazzy/ARM64. Next approach:
extract prebuilt static library from `~/microros_ws` and link directly in PlatformIO,
bypassing the source build step.

### ReSpeaker Mic Array V1.0
- 8 channels: 7 raw mics + 1 beamformed processed output (ch0)
- Use ch0 for speech recognition – hardware DSP already handles noise cancellation
- DOA readable via USB HID interface – enables head tracking toward speaker
- Optimal sample rate: 16000 Hz (Whisper compatible)
- alsamixer gain tuning needed (currently low volume)
