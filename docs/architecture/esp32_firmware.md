# ESP32 Firmware Architecture

## Overview

Drei ESP32 Nodes, alle mit micro-ROS (Jazzy):
- **Chassis ESP32** – Motoren, Sensoren, Odometrie
- **Head ESP32** – Kopf, Display, Ultraschall
- **Cortex ESP32** – Power Controller + RGB Status Matrix (immer aktiv)

## Chassis ESP32 (LOLIN D32)

### Responsibilities
- MD25 motor controller interface (UART)
- Differential drive: empfängt `/cmd_vel`, publiziert `/odom`
- HMC5883L compass/IMU (I2C Bus 0)
- Stair sensor ultrasonic (I2C Bus 0)
- SSD1306 OLED status display (SPI)
- Publiziert `/r2d2/chassis/status` (Heartbeat)

### Bus Layout
```
I2C Bus 0 (GPIO 21/22)  →  HMC5883L + Ultrasonic stair
UART (GPIO 16/17)        →  MD25 motor controller
SPI                      →  SSD1306 OLED
USB Serial               →  micro-ROS Agent on Pi (/dev/ttyACM0)
```

### micro-ROS Topics
| Topic | Direction | Type |
|---|---|---|
| `/cmd_vel` | Subscribe | geometry_msgs/Twist |
| `/odom` | Publish | nav_msgs/Odometry |
| `/imu` | Publish | sensor_msgs/Imu |
| `/stair_sensor` | Publish | sensor_msgs/Range |
| `/r2d2/chassis/status` | Publish | std_msgs/String |

## Head ESP32 (LOLIN D32)

### Responsibilities
- A4988 stepper motor für Kopfrotation (±100°)
- SerLCD 40x2 display (UART, 5V via logic level converter)
- Ultrasonic distance sensor (I2C)
- Verbunden via Bluetooth micro-ROS

> **Hinweis:** Die HT16K33 RGB 8x8 Matrix wurde vom Head ESP32
> zum **Cortex ESP32** verschoben. Begründung: Status soll auch
> ohne aktiven Pi sichtbar sein. Siehe [cortex_esp32.md](cortex_esp32.md).

### Bus Layout
```
I2C Bus 0 (GPIO 21/22)  →  (frei / Reserve)
I2C Bus 1 (GPIO 16/17)  →  Ultrasonic (head)
UART + 3.3V LLC         →  SerLCD 40x2
GPIO STEP + DIR         →  A4988 stepper
Bluetooth               →  micro-ROS Agent on Pi
```

### micro-ROS Topics
| Topic | Direction | Type |
|---|---|---|
| `/r2d2/head/cmd` | Subscribe | std_msgs/Float32 (angle °) |
| `/r2d2/head/ultrasonic` | Publish | sensor_msgs/Range |
| `/r2d2/head/display` | Subscribe | std_msgs/String |

## Cortex ESP32 (LOLIN D32) – Power Controller + Status

Siehe [cortex_esp32.md](cortex_esp32.md) für vollständige Details.

### Responsibilities
- **Immer aktiv** (~0.05W, kein ROS2 nötig)
- HT16K33 RGB 8x8 Matrix – visueller Zustandsindikator
- Watchdog für Pi Heartbeat
- Power Relay Control (MD25 12V, USB Hub 5V, Pi 5V)
- Wake/Sleep Sequenzierung
- Subscribt `/r2d2/power/state` wenn Pi aktiv ist

### Bus Layout
```
I2C Bus 0 (GPIO 21/22)  →  HT16K33 RGB 8x8 Matrix
GPIO                    →  Relay 1 (12V MD25)
GPIO                    →  Relay 2 (5V USB Hub)
GPIO                    →  Pi Power Enable
GPIO (input)            →  Pi Shutdown Monitor
```

## micro-ROS Build

**Problem:** `micro_ros_platformio` schlägt auf Jazzy/ARM64 fehl
(fehlende CMake-Pakete: rmw_test_fixture, rosidl_typesupport_cpp).

**Lösung:** Prebuilt static library aus `micro_ros_arduino` Release.
Siehe [ADR 005](../decisions/005-microros-prebuilt-library.md).

```bash
# Einmalig: library herunterladen
bash esp32/r2d2_chassis_esp32/scripts/build_microros_lib.sh

# Bauen + flashen
cd esp32/r2d2_chassis_esp32
source /opt/ros/jazzy/setup.bash
pio run --target upload
```

**micro-ROS Agent starten:**
```bash
source ~/microros_ws/install/setup.bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0 -b 115200
```
