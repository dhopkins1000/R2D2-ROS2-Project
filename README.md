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
- Head ESP32 (LOLIN D32) – micro-ROS node (stepper motor, SerLCD 40x2, ultrasonic)
- Cortex ESP32 (LOLIN D32) – power controller + HT16K33 RGB 8x8 status matrix (always on)
- A4988 stepper driver – head rotation

**Audio & Voice**
- ReSpeaker Mic Array V1.0 (USB, 7 mics, XVSM-2000, raw firmware)
  - 8 raw channels, 16kHz
  - DOA via GCC-PHAT software beamforming (6 outer mics, 65mm diameter)
  - VAD via RMS energy threshold (calibrated: silence=74, speech=361, threshold=218)
- Speaker + mini amplifier in chassis

## Software Stack

| Layer | Technology |
|---|---|
| OS | Ubuntu 24.04 Server (ARM64) |
| ROS2 | Jazzy Jalisco (LTS) |
| Visualization | Foxglove Studio (Mac) via WebSocket |
| ESP32 Firmware | micro-ROS (Jazzy) via PlatformIO + prebuilt library |
| Navigation | Nav2 + slam_toolbox |
| DOA | GCC-PHAT software beamforming |
| VAD | RMS energy threshold |
| Speech Recognition | Whisper (local, offline) |
| Wake Word | openWakeWord |
| Development | VS Code Remote SSH + Claude Code |

## ROS2 Workspace Structure

```
~/ros2_ws/src/
  r2d2_bringup/      # Launch files + config (cameras, foxglove)
  r2d2_description/  # URDF/XACRO robot model
  r2d2_base/         # Chassis ESP32 interface (MD25, odometry)
  r2d2_head/         # Head ESP32 interface (stepper, display)
  r2d2_perception/   # Camera processing, object detection
  r2d2_navigation/   # Nav2 config + maps
  r2d2_behavior/     # Behaviour trees, state machine
  r2d2_audio/        # ReSpeaker DOA/VAD, wake word, Whisper STT, TTS

esp32/
  r2d2_chassis_esp32/  # PlatformIO – Chassis ESP32 firmware
```

## Connection Architecture

```
Raspberry Pi 4
├── Chassis ESP32      (USB Serial – micro-ROS, /dev/ttyACM0)
│   ├── MD25           (UART – motors + encoders)
│   ├── HMC5883L       (I2C Bus 0 – compass/IMU)
│   ├── Ultrasonic     (I2C Bus 0 – stair sensor)
│   └── SSD1306 OLED   (SPI – status display)
├── Head ESP32         (Bluetooth – micro-ROS)
│   ├── A4988 stepper  (GPIO STEP/DIR – head rotation)
│   ├── SerLCD 40x2    (UART + 3.3V logic level – display)
│   └── Ultrasonic     (I2C Bus 1 – distance sensor)
├── Cortex ESP32       (always on – power controller)
│   ├── HT16K33        (I2C – RGB 8x8 status matrix)
│   ├── Relay 1        (GPIO – 12V MD25)
│   └── Relay 2        (GPIO – 5V USB Hub)
├── ASUS Xtion Pro     (USB – depth + RGB camera)
├── USB Webcam         (USB – front camera)
└── ReSpeaker Mic Array V1.0  (USB via spiral cable through head axis)
```

## Voice / Audio Node Architecture (r2d2_audio)

```
ReSpeaker (USB, 8 raw channels, 16kHz)
         │
         ▼
  respeaker_node
    ├── /r2d2/audio/doa   (Int16 – direction 0-359°, GCC-PHAT)
    └── /r2d2/audio/vad   (Bool  – voice activity detected)
         │  (only when VAD=True)
         ▼
  wake_word_node  ("Hey R2D2" – openWakeWord)
    └── /r2d2/audio/wake_word    (Bool)
         │
         ▼
  whisper_node  (local STT, offline, tiny model)
    └── /r2d2/audio/command      (String)
         │
         ▼
  Behaviour Tree
    ├── DOA → /r2d2/head/cmd     (head rotates toward speaker)
    └── command → action
         │
         ▼
  tts_node
    └── /r2d2/audio/speak        (String → speaker output)
```

## Status

- [x] Ubuntu 24.04 + ROS2 Jazzy installed
- [x] r2d2_bringup: Xtion Pro + Webcam + Foxglove Bridge (systemd service)
- [x] Foxglove Studio connected from Mac
- [x] GitHub repo cleaned up, ROS2 workspace pushed
- [x] micro-ROS Agent built from source (~/microros_ws)
- [x] PlatformIO installed on Pi + ESP32 project skeleton created
- [x] ReSpeaker Mic Array V1.0 recognized (USB, 8ch raw, 16kHz)
- [x] micro-ROS firmware compiled + flashed (prebuilt library approach)
- [x] Chassis ESP32 connected to micro-ROS Agent (/r2d2/chassis/status publishing)
- [x] ReSpeaker VAD working (/r2d2/audio/vad)
- [x] ReSpeaker DOA working (/r2d2/audio/doa – GCC-PHAT, calibrated)
- [ ] Wake word node (openWakeWord – "Hey R2D2")
- [ ] Whisper STT node
- [ ] Chassis ESP32 hardware wiring (MD25, HMC5883L, Ultrasonic, OLED)
- [ ] MD25 drive node (r2d2_base)
- [ ] Nav2 + SLAM
- [ ] Head ESP32
- [ ] Cortex ESP32 (power controller + RGB matrix)
- [ ] Behaviour trees

## Notes

### micro-ROS auf Jazzy/ARM64
`micro_ros_platformio` kann auf Jazzy/ARM64 nicht nativ gebaut werden.
**Lösung:** Prebuilt static library aus `micro_ros_arduino` Release einbinden.

```bash
bash esp32/r2d2_chassis_esp32/scripts/build_microros_lib.sh
cd esp32/r2d2_chassis_esp32 && pio run --target upload
```

micro-ROS Agent:
```bash
source ~/microros_ws/install/setup.bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0 -b 115200
```

### ReSpeaker Mic Array V1.0 – DOA
- Raw firmware: 8 channels, no hardware DSP, no hardware DOA register
- DOA computed in software via GCC-PHAT beamforming (15 mic pairs)
- Mic layout: 6 outer mics on 65mm diameter circle, 60° spacing + 1 center
- VAD calibration: silence RMS ~74, speech RMS ~361, threshold=218
- VAD threshold tunable via ROS2 parameter: `--ros-args -p vad_threshold:=200`
