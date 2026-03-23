# R2D2 – System Architecture Overview

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Raspberry Pi 4 (8GB)                  │
│                                                         │
│  r2d2_bringup      r2d2_perception    r2d2_navigation   │
│  r2d2_audio        r2d2_behavior      r2d2_description  │
│  micro-ROS Agent   Foxglove Bridge                      │
└────────┬──────────────────┬───────────────┬─────────────┘
         │ USB Serial        │ Bluetooth      │ USB
         ▼                  ▼               ▼
  Chassis ESP32        Head ESP32      ReSpeaker
  (LOLIN D32)          (LOLIN D32)     Mic Array
```

## ROS2 Node Architecture

### Topics Overview

| Topic | Type | Publisher | Subscriber |
|---|---|---|---|
| `/cmd_vel` | Twist | Nav2 / Teleop | r2d2_base |
| `/odom` | Odometry | r2d2_base | Nav2 |
| `/camera/rgb/image_raw` | Image | openni2 | perception, foxglove |
| `/camera/depth/image` | Image | openni2 | Nav2 costmap |
| `/camera/depth/points` | PointCloud2 | openni2 | Nav2, SLAM |
| `/webcam/image_raw` | Image | usb_cam | perception, foxglove |
| `/r2d2/audio/doa` | Int16 | respeaker_node | behavior, head |
| `/r2d2/audio/wake_word` | Bool | wake_word_node | behavior |
| `/r2d2/audio/command` | String | whisper_node | behavior |
| `/r2d2/audio/speak` | String | behavior | tts_node |
| `/r2d2/head/cmd` | Float32 | behavior | r2d2_head |
| `/r2d2/chassis/status` | String | r2d2_base | foxglove |
| `/r2d2/power/state` | String | cortex_node | all |
| `/imu` | Imu | r2d2_base | Nav2 |
| `/stair_sensor` | Range | r2d2_base | behavior |

## Package Responsibilities

### r2d2_bringup
Launch files and configuration only. No executable code.
Starts: cameras, foxglove bridge, all other packages.

### r2d2_base
Interface to Chassis ESP32 via micro-ROS.
- MD25 motor controller (UART)
- Differential drive odometry
- HMC5883L compass/IMU (I2C)
- Stair sensor ultrasonic (I2C)
- SSD1306 OLED status display (SPI)

### r2d2_head
Interface to Head ESP32 via micro-ROS (Bluetooth).
- A4988 stepper motor (head rotation)
- HT16K33 RGB 8x8 matrix
- SerLCD 40x2 display
- Ultrasonic distance sensor

### r2d2_perception
- Xtion Pro depth processing (depth_image_proc)
- Object detection (webcam)
- Pointcloud generation for Nav2

### r2d2_navigation
- Nav2 configuration
- slam_toolbox
- Map management

### r2d2_audio
See [audio_voice.md](audio_voice.md) for details.
- ReSpeaker node (DOA, audio stream)
- Wake word detection
- Whisper STT
- TTS output

### r2d2_behavior
- Behaviour Trees (BehaviorTree.CPP)
- State machine (idle, active, navigating, interacting)
- R2D2 personality / emote logic

### r2d2_description
- URDF/XACRO robot model
- TF tree
- RViz / Foxglove visualization config
