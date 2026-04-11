# R2D2 – ROS2 Robotics Project

A real-world R2D2 build (~75cm) running ROS2 Jazzy Jalisco on a Raspberry Pi 4 (8GB).

## Hardware

**Main Computer**
- Raspberry Pi 4 (8GB) – Ubuntu 24.04 Server (ARM64, headless)

**Sensors & Cameras**
- ASUS Xtion Pro – USB 3D depth camera (openni2)
- USB Webcam – front camera
- HMC5883L (GY-273) – I2C 3-axis compass / IMU
- SRF02 ultrasonic – I2C, downward-angled for stair detection (addr 0x71)
- Ultrasonic sensor (head) – I2C, forward distance (model TBD)

**Drive System**
- MD25 motor controller – differential drive, 2x DC motors with encoders (UART mode)
- EMG30 motors – 12V, 30:1 gearbox, 360 encoder ticks/revolution, 100mm wheels
- Chassis ESP32 (LOLIN D1 Mini) – micro-ROS node (motors, odometry, IMU, stair sensor, SSD1306 OLED)

**Head**
- Head ESP32 (LOLIN D1 Mini) – micro-ROS node ✓ online
- A4988 stepper driver – head rotation (wiring pending)
- SerLCD 40x2 – UART display (wiring pending)
- Ultrasonic sensor – I2C forward distance (model TBD)

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
  r2d2_bringup/      # Launch files + config (cameras, foxglove, systemd services)
  r2d2_description/  # URDF/XACRO robot model + robot_state_publisher launch
  r2d2_base/         # odom→base_link TF broadcaster
  r2d2_head/         # Head ESP32 ROS2 interface (stepper, display) – placeholder
  r2d2_perception/   # Camera processing, object detection
  r2d2_navigation/   # Nav2 config + maps
  r2d2_behavior/     # Behaviour trees, state machine
  r2d2_audio/        # ReSpeaker DOA/VAD, wake word, Whisper STT, TTS

esp32/
  r2d2_chassis_esp32/  # PlatformIO – Chassis ESP32 firmware (vollständig)
    src/
      config.h / main.cpp / oled_display / hmc5883l / srf02 / md25
  r2d2_head_esp32/     # PlatformIO – Head ESP32 firmware (Skeleton, online)
    src/
      config.h           # Pin- und Topic-Definitionen (Pins TBD)
      main.cpp           # micro-ROS Skeleton – status heartbeat
```

## systemd Services

Alle Services starten automatisch beim Boot:

| Service | Funktion | USB Device |
|---------|----------|------------|
| `r2d2.service` | Foxglove Bridge + Kameras + URDF + TF | – |
| `microros-agent-chassis.service` | micro-ROS Agent Chassis ESP32 | `5AA7004892` → ttyACM1 |
| `microros-agent-head.service` | micro-ROS Agent Head ESP32 | `5AA7003331` → ttyACM0 |

```bash
# Installation (einmalig):
sudo cp ~/ros2_ws/src/r2d2_bringup/r2d2.service /etc/systemd/system/
sudo cp ~/ros2_ws/src/r2d2_bringup/microros-agent-chassis.service /etc/systemd/system/
sudo cp ~/ros2_ws/src/r2d2_bringup/microros-agent-head.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable r2d2.service microros-agent-chassis.service microros-agent-head.service

# Steuerung:
sudo systemctl start|stop|restart microros-agent-chassis.service
sudo systemctl start|stop|restart microros-agent-head.service
journalctl -u microros-agent-chassis.service -f
journalctl -u microros-agent-head.service -f
```

## Foxglove Studio

Verbindung: `ws://r2d2.local:8765` (oder IP des Pi)

Layout importieren: `src/r2d2_bringup/config/foxglove_layout.json`

Panels: Kompass Plot | Ultraschall Plot | Odometrie Plot | Status | 3D View + Teleop | Kamera RGB

Für 3D View mit URDF (in r2d2.service bereits integriert):
- Fixed frame → `base_link`, Display frame → `odom`, Follow mode → Off
- `/robot_description` Topic aktivieren

## Connection Architecture

```
Raspberry Pi 4
├── USB Hub
│   ├── Chassis ESP32  (ttyACM1, by-id: 5AA7004892)
│   │   ├── MD25           (UART2 GPIO16/17 – 38400 baud, 2 stop bits)
│   │   ├── HMC5883L       (I2C GPIO21/22 – 0x1E)
│   │   ├── SRF02          (I2C GPIO21/22 – 0x71, BSS138 shifter)
│   │   └── SSD1306 OLED   (SPI GPIO18/23/5/4/26)
│   └── Head ESP32     (ttyACM0, by-id: 5AA7003331) ✓ online
│       ├── A4988 stepper  (GPIO – wiring pending)
│       ├── SerLCD 40x2    (UART – wiring pending)
│       └── Ultrasonic     (I2C – model TBD)
├── ASUS Xtion Pro     (USB – depth + RGB camera)
├── USB Webcam         (USB – front camera)
└── ReSpeaker Mic Array V1.0  (USB)
```

## Chassis ESP32 – ROS2 Topics

| Topic | Typ | Rate | Inhalt |
|-------|-----|------|--------|
| `/r2d2/chassis/status` | std_msgs/String | 1 Hz | Heartbeat + Uptime |
| `/r2d2/chassis/compass` | sensor_msgs/MagneticField | 10 Hz | HMC5883L X/Y/Z |
| `/r2d2/chassis/stair_alert` | sensor_msgs/Range | 5 Hz | SRF02 Entfernung |
| `/r2d2/chassis/cmd_vel` | geometry_msgs/Twist | (subscriber) | Motorsteuerung |
| `/r2d2/chassis/odom` | nav_msgs/Odometry | 10 Hz | Position + Heading |

## Head ESP32 – ROS2 Topics (geplant)

| Topic | Typ | Inhalt |
|-------|-----|--------|
| `/r2d2/head/status` | std_msgs/String | Heartbeat ✓ live |
| `/r2d2/head/cmd` | std_msgs/Float32 | Zielwinkel in Grad (subscriber) |
| `/r2d2/head/position` | std_msgs/Float32 | Aktueller Winkel |
| `/r2d2/head/distance` | sensor_msgs/Range | Ultraschall vorne |

## Chassis ESP32 Wiring Details

| Signal | ESP32 Pin | Gerät | Hinweis |
|--------|-----------|-------|---------|
| UART2 TX | GPIO17 | MD25 Rx | 3.3V direkt |
| UART2 RX | GPIO16 | MD25 Tx | Spannungsteiler 1kΩ+2.2kΩ |
| I2C SDA | GPIO21 | HMC5883L + SRF02 | SRF02 via BSS138 |
| I2C SCL | GPIO22 | HMC5883L + SRF02 | SRF02 via BSS138 |
| SPI SCK | GPIO18 | OLED Clk | direkt |
| SPI MOSI | GPIO23 | OLED Data | direkt |
| SPI CS | GPIO5 | OLED CS | direkt |
| DC | GPIO4 | OLED DC | direkt |
| RST | GPIO26 | OLED Rst | nicht GPIO2! |
| VCC | VCC (5V) | OLED Vin | USB-Durchschleif |

## Voice / Audio Node Architecture (r2d2_audio)

```
ReSpeaker (USB, 8 raw channels, 16kHz)
         │
         ▼
  respeaker_node
    ├── /r2d2/audio/doa   (Int16 – direction 0-359°, GCC-PHAT)
    └── /r2d2/audio/vad   (Bool  – voice activity detected)
         │
         ▼
  wake_word_node  ("Hey Jarvis" placeholder → custom "Hey R2D2" planned)
    └── /r2d2/audio/wake_word  (Bool)
         │
         ▼
  whisper_node  (local STT, offline, tiny model, de)
    └── /r2d2/audio/command    (String)
         │
         ▼
  voice_node  (FM synthesis, sample-based R2D2 voice)
    └── /r2d2/voice_intent     (subscriber)
```

## Status

- [x] Ubuntu 24.04 + ROS2 Jazzy installed
- [x] r2d2.service: Foxglove Bridge + Kameras + URDF + TF (systemd, autostart)
- [x] microros-agent-chassis.service: Chassis ESP32 (systemd, autostart, by-id)
- [x] microros-agent-head.service: Head ESP32 (systemd, autostart, by-id)
- [x] Foxglove Studio verbunden + Layout konfiguriert
- [x] Chassis ESP32 vollständig: compass, stair_alert, cmd_vel, odom ✓
- [x] Remote-Steuerung via Foxglove Teleop Panel ✓
- [x] r2d2_description: URDF Basismodell live in Foxglove 3D View
- [x] r2d2_base: odom→base_link TF broadcaster
- [x] ReSpeaker VAD + DOA working
- [x] Head ESP32 online – /r2d2/head/status live ✓
- [ ] Head ESP32 Hardware verdrahten (A4988, SerLCD, Ultraschall)
- [ ] Head ESP32 Firmware: Stepper + Display + Ultraschall
- [ ] Ultraschall Sensor im Kopf identifizieren
- [ ] Wake word: echtes "Hey R2D2" Modell trainieren
- [ ] Whisper STT Node testen
- [ ] Nav2 + SLAM (sobald R2D2 auf dem Boden fährt)
- [ ] Cortex ESP32 (power controller + RGB matrix)
- [ ] Behaviour trees

## Notes

### systemd Services einrichten (einmalig)
```bash
sudo cp ~/ros2_ws/src/r2d2_bringup/r2d2.service /etc/systemd/system/
sudo cp ~/ros2_ws/src/r2d2_bringup/microros-agent-chassis.service /etc/systemd/system/
sudo cp ~/ros2_ws/src/r2d2_bringup/microros-agent-head.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable r2d2.service microros-agent-chassis.service microros-agent-head.service
```

### USB Device IDs (stabil, unabhängig von Boot-Reihenfolge)
```
Chassis ESP32: usb-1a86_USB_Single_Serial_5AA7004892-if00 → /dev/ttyACM1
Head ESP32:    usb-1a86_USB_Single_Serial_5AA7003331-if00 → /dev/ttyACM0
```

### ⚠️ Port-Konflikt
Jeder `/dev/ttyACM*` Port kann nur von einem Prozess gleichzeitig genutzt werden.
`pio device monitor` und `micro_ros_agent` nie gleichzeitig auf demselben Port!
Prüfen: `fuser /dev/ttyACM0` / `fuser /dev/ttyACM1`

### EMG30 Encoder / Odometrie
- 360 Ticks/Umdrehung, 100mm Rad → 0.000873m/Tick, Spurbreite 0.30m

### MD25 Serial Protokoll
`Serial2.begin(38400, SERIAL_8N2, 16, 17)`
- SET SPEED 1: `[0x00, 0x31, speed]` (0=rückwärts, 128=stop, 255=vorwärts)
- SET SPEED 2: `[0x00, 0x32, speed]`
- GET ENCODERS: `[0x00, 0x25]` → 8 Bytes
- DISABLE TIMEOUT: `[0x00, 0x38]`

### SRF02: Adresse 0x71 (nicht 0x70)

### ReSpeaker VAD Tuning
`--ros-args -p vad_threshold:=200` (calibrated: silence=74, speech=361)
