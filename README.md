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
- Ultrasonic sensor (head) – I2C, forward distance

**Drive System**
- MD25 motor controller – differential drive, 2x DC motors with encoders (UART mode)
- EMG30 motors – 12V, 30:1 gearbox, 360 encoder ticks/revolution, 100mm wheels
- Chassis ESP32 (LOLIN D1 Mini) – micro-ROS node (motors, odometry, IMU, stair sensor, SSD1306 OLED)

**Head**
- Head ESP32 (LOLIN D1 Mini) – micro-ROS node (stepper motor, SerLCD 40x2, ultrasonic)
- Cortex ESP32 (LOLIN D1 Mini) – power controller + HT16K33 RGB 8x8 status matrix (always on)
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
  r2d2_bringup/      # Launch files + config (cameras, foxglove, systemd services)
  r2d2_description/  # URDF/XACRO robot model + robot_state_publisher launch
  r2d2_base/         # odom→base_link TF broadcaster
  r2d2_head/         # Head ESP32 interface (stepper, display)
  r2d2_perception/   # Camera processing, object detection
  r2d2_navigation/   # Nav2 config + maps
  r2d2_behavior/     # Behaviour trees, state machine
  r2d2_audio/        # ReSpeaker DOA/VAD, wake word, Whisper STT, TTS

esp32/
  r2d2_chassis_esp32/  # PlatformIO – Chassis ESP32 firmware
    src/
      config.h           # Pin- und Topic-Definitionen
      main.cpp           # micro-ROS Reconnect-Loop + Publisher/Subscriber
      oled_display.h/cpp # OLED Implementierung (Adafruit SSD1306 SPI)
      hmc5883l.h/.cpp    # Kompass-Treiber
      srf02.h/.cpp       # Ultraschall-Treiber
      md25.h/.cpp        # Motor-Treiber + Encoder-Auslesen
```

## systemd Services

Beide Services starten automatisch beim Boot:

| Service | Funktion | Abhängigkeit |
|---------|----------|--------------|
| `r2d2.service` | Foxglove Bridge + Kameras | network.target |
| `microros-agent.service` | micro-ROS Agent (ESP32) | r2d2.service |

```bash
# Installation (einmalig):
sudo cp ~/ros2_ws/src/r2d2_bringup/r2d2.service /etc/systemd/system/
sudo cp ~/ros2_ws/src/r2d2_bringup/microros-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable r2d2.service microros-agent.service

# Steuerung:
sudo systemctl start|stop|restart r2d2.service
sudo systemctl start|stop|restart microros-agent.service
journalctl -u r2d2.service -f
journalctl -u microros-agent.service -f
```

## Foxglove Studio

Verbindung: `ws://r2d2.local:8765` (oder IP des Pi)

Layout importieren: `src/r2d2_bringup/config/foxglove_layout.json`

Panels: Kompass Plot | Ultraschall Plot | Odometrie Plot | Status | 3D View + Teleop | Kamera RGB

Für 3D View mit URDF:
1. `ros2 launch r2d2_description description.launch.py` starten
2. `ros2 launch r2d2_base base.launch.py` starten (odom→base_link TF)
3. Fixed frame → `odom`
4. `/robot_description` Topic aktivieren

## Connection Architecture

```
Raspberry Pi 4
├── Chassis ESP32      (USB-C Serial – micro-ROS, /dev/ttyACM0)
│   ├── MD25           (UART2 GPIO16/17 – motors + encoders, 38400 baud, 2 stop bits)
│   ├── HMC5883L       (I2C GPIO21/22 – compass/IMU, 0x1E, direkt 3.3V)
│   ├── SRF02          (I2C GPIO21/22 – stair sensor, 0x71, BSS138 level shifter)
│   └── SSD1306 OLED   (SPI GPIO18/23/5/4/26 – status display, Adafruit v2.1 onboard shifter)
├── Head ESP32         (Bluetooth – micro-ROS)
│   ├── A4988 stepper  (GPIO STEP/DIR – head rotation)
│   ├── SerLCD 40x2    (UART + 3.3V logic level – display)
│   └── Ultrasonic     (I2C – distance sensor)
├── Cortex ESP32       (always on – power controller)
│   ├── HT16K33        (I2C – RGB 8x8 status matrix)
│   ├── Relay 1        (GPIO – 12V MD25)
│   └── Relay 2        (GPIO – 5V USB Hub)
├── ASUS Xtion Pro     (USB – depth + RGB camera)
├── USB Webcam         (USB – front camera)
└── ReSpeaker Mic Array V1.0  (USB via spiral cable through head axis)
```

## Chassis ESP32 – ROS2 Topics

| Topic | Typ | Rate | Inhalt |
|-------|-----|------|--------|
| `/r2d2/chassis/status` | std_msgs/String | 1 Hz | Heartbeat + Uptime |
| `/r2d2/chassis/compass` | sensor_msgs/MagneticField | 10 Hz | HMC5883L X/Y/Z Rohdaten |
| `/r2d2/chassis/stair_alert` | sensor_msgs/Range | 5 Hz | SRF02 Entfernung in Metern |
| `/r2d2/chassis/cmd_vel` | geometry_msgs/Twist | (subscriber) | Motorsteuerung |
| `/r2d2/chassis/odom` | nav_msgs/Odometry | 10 Hz | Position + Heading aus Encoder-Daten |

## Chassis ESP32 Wiring Details

| Signal | ESP32 Pin | Gerät | Hinweis |
|--------|-----------|-------|---------|
| UART2 TX | GPIO17 | MD25 Rx | 3.3V direkt (MD25 toleriert) |
| UART2 RX | GPIO16 | MD25 Tx | Spannungsteiler 1kΩ+2.2kΩ (5V→3.44V) |
| I2C SDA | GPIO21 | HMC5883L + SRF02 | SRF02 via BSS138 Level Shifter |
| I2C SCL | GPIO22 | HMC5883L + SRF02 | SRF02 via BSS138 Level Shifter |
| SPI SCK | GPIO18 | OLED Clk | direkt (Adafruit onboard Shifter) |
| SPI MOSI | GPIO23 | OLED Data | direkt |
| SPI CS | GPIO5 | OLED CS | direkt |
| DC | GPIO4 | OLED DC | direkt |
| RST | GPIO26 | OLED Rst | GPIO26 (nicht GPIO2 – Boot-Pin!) |
| VCC | VCC (5V) | OLED Vin | 5V vom USB-Durchschleif-Pin |

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
- [x] r2d2.service: Foxglove Bridge + Kameras (systemd, autostart)
- [x] microros-agent.service: micro-ROS Agent ESP32 (systemd, autostart)
- [x] Foxglove Studio verbunden + Layout konfiguriert (Sensor-Panels + Teleop + 3D)
- [x] GitHub repo cleaned up, ROS2 workspace pushed
- [x] micro-ROS Agent built from source (~/microros_ws)
- [x] Chassis ESP32 Firmware vollständig:
  - /r2d2/chassis/compass (sensor_msgs/MagneticField, 10 Hz) ✓
  - /r2d2/chassis/stair_alert (sensor_msgs/Range, 5 Hz) ✓
  - /r2d2/chassis/cmd_vel (geometry_msgs/Twist, subscriber) ✓ Räder drehen
  - /r2d2/chassis/odom (nav_msgs/Odometry, 10 Hz) ✓ Encoder-Odometrie live
- [x] Remote-Steuerung via Foxglove Teleop Panel ✓
- [x] r2d2_description: URDF Basismodell (Zylinder-Chassis, Räder, Kopf, Sensor-Frames)
- [x] r2d2_base: odom→base_link TF broadcaster (Pi-Systemzeit, löst stamp.sec=0 Problem)
- [x] Foxglove 3D View: Roboter sichtbar, bewegt sich live mit Odometrie
- [x] ReSpeaker VAD + DOA working
- [ ] URDF verfeinern (realistischere R2D2-Geometrie)
- [ ] description.launch.py + base.launch.py in r2d2.service integrieren
- [ ] Wake word node (openWakeWord – "Hey R2D2")
- [ ] Whisper STT node
- [ ] Nav2 + SLAM
- [ ] Head ESP32
- [ ] Cortex ESP32 (power controller + RGB matrix)
- [ ] Behaviour trees

## Notes

### Starten (manuell, für Entwicklung)
```bash
# Terminal 1 – URDF + TF
source ~/ros2_ws/install/setup.bash
ros2 launch r2d2_description description.launch.py &
ros2 launch r2d2_base base.launch.py

# TF prüfen:
ros2 run tf2_ros tf2_echo odom base_link
```

### systemd Services einrichten
```bash
sudo cp ~/ros2_ws/src/r2d2_bringup/r2d2.service /etc/systemd/system/
sudo cp ~/ros2_ws/src/r2d2_bringup/microros-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable r2d2.service microros-agent.service
```

### ⚠️ Port-Konflikt: /dev/ttyACM0
`/dev/ttyACM0` kann immer nur von **einem** Prozess gleichzeitig genutzt werden.
- Prüfen mit: `fuser /dev/ttyACM0`
- Lösung: `sudo kill <PID>` dann Agent neu starten

### EMG30 Encoder / Odometrie
- Encoder: 360 Ticks pro Radumdrehung (output shaft, nach 30:1 Getriebe)
- Rad-Durchmesser: 100mm → Umfang: 0.3142m → 0.000873m pro Tick
- Spurbreite: 0.30m (in md25.cpp anpassbar)

### MD25 Serial Protokoll
Jumper: Serial mode, 38400 bps, 1 start bit, 2 stop bits, no parity.
`Serial2.begin(38400, SERIAL_8N2, 16, 17)`

| Kommando | Bytes | Beschreibung |
|----------|-------|--------------|
| SET SPEED 1 | `[0x00, 0x31, speed]` | 0=rückwärts, 128=stop, 255=vorwärts |
| SET SPEED 2 | `[0x00, 0x32, speed]` | wie oben |
| GET ENCODERS | `[0x00, 0x25]` → 8 Bytes | 2× int32, high byte first |
| RESET ENCODERS | `[0x00, 0x35]` | Zähler auf 0 |
| DISABLE TIMEOUT | `[0x00, 0x38]` | Kein Auto-Stop nach 2s |

### SRF02 I2C Adresse
Meldet sich auf **0x71** (nicht 0x70 wie im Datenblatt). Bereits in config.h gesetzt.

### ReSpeaker Mic Array V1.0 – DOA
- DOA via GCC-PHAT, 6 Außenmics, 65mm Durchmesser
- VAD: silence=74, speech=361, threshold=218
- Tuning: `--ros-args -p vad_threshold:=200`
