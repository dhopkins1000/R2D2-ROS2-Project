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

**Audio**
- Speaker + mini amplifier in chassis

## Software Stack

| Layer | Technology |
|---|---|
| OS | Ubuntu 24.04 Server (ARM64) |
| ROS2 | Jazzy Jalisco (LTS) |
| Visualization | Foxglove Studio (Mac) via WebSocket |
| ESP32 Firmware | micro-ROS (Jazzy) via PlatformIO |
| Navigation | Nav2 + slam_toolbox |
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
  r2d2_audio/        # Sound output

esp32/
  r2d2_chassis_esp32/  # PlatformIO project – Chassis ESP32 firmware
```

## Connection Architecture

```
Raspberry Pi 4
├── Chassis ESP32  (USB Serial – micro-ROS)
│   ├── MD25 motor controller  (UART)
│   ├── HMC5883L compass       (I2C Bus 1)
│   ├── Ultrasonic stair       (I2C Bus 1)
│   └── SSD1306 OLED status    (SPI)
└── Head ESP32     (Bluetooth – micro-ROS)
    ├── A4988 stepper          (GPIO STEP/DIR)
    ├── HT16K33 RGB 8x8        (I2C Bus 0)
    ├── SerLCD 40x2            (UART + logic level converter)
    └── Ultrasonic head        (I2C Bus 1)
```

## Status

- [x] Ubuntu 24.04 + ROS2 Jazzy installed
- [x] r2d2_bringup: Xtion Pro + Webcam + Foxglove Bridge (systemd service)
- [x] Foxglove Studio connected from Mac
- [x] GitHub repo cleaned up, ROS2 workspace pushed
- [x] micro-ROS Agent built from source (~/microros_ws)
- [x] PlatformIO installed on Pi + ESP32 project skeleton created
- [ ] micro-ROS firmware build for ESP32 (micro_ros_platformio Jazzy/ARM64 issue - WIP)
- [ ] Chassis ESP32 wiring + first topic published
- [ ] MD25 drive node (r2d2_base)
- [ ] Nav2 + SLAM
- [ ] Head ESP32
- [ ] Behaviour trees

## Notes

### micro-ROS on Jazzy/ARM64
`micro_ros_platformio` has known issues building on Jazzy/ARM64. Next approach:
extract prebuilt static library from `~/microros_ws` and link directly in PlatformIO,
bypassing the source build step.
