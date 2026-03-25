# ESP32 Firmware Architecture

## Overview

Drei ESP32 Nodes, alle mit micro-ROS (Jazzy):
- **Chassis ESP32** – Motoren, Sensoren, Odometrie
- **Head ESP32** – Kopf, Display, Ultraschall
- **Cortex ESP32** – Power Controller + RGB Status Matrix (immer aktiv)

## Chassis ESP32 (LOLIN D32)

### Responsibilities
- MD25 motor controller interface (**UART**, not I2C – see decision below)
- Differential drive: empfängt `/cmd_vel`, publiziert `/odom`
- HMC5883L compass/IMU (I2C)
- SRF02 stair sensor ultrasonic (I2C, 5V – via BSS138 shifter)
- SSD1306 OLED status display (SPI)
- Publiziert `/r2d2/chassis/status` (Heartbeat)

### Bus Layout
```
UART2 (GPIO 16/17)      →  MD25 motor controller (9600 baud)
                           GPIO17 TX → MD25 RX (direct)
                           GPIO16 RX ← MD25 TX (via 1kΩ/2kΩ divider)
I2C Bus 0 (GPIO 21/22)  →  HMC5883L (0x1E, 3.3V direct)
                           SRF02 (0x70, 5V via BSS138 shifter)
SPI                      →  SSD1306 OLED (Adafruit v2.1, onboard shifter)
                           CLK=18, MOSI=23, CS=5, DC=2, RST=4
USB-C                    →  micro-ROS Agent on Pi (/dev/ttyACM0)
```

### Why MD25 on UART (not I2C)
MD25 communicates encoder positions at high frequency during motor operation.
If MD25 is on I2C, it blocks the bus for extended periods, potentially
causing the safety-critical SRF02 stair sensor to miss readings.

Conclusion: MD25 on dedicated UART2, SRF02 + HMC5883L on I2C Bus 0.

### micro-ROS Topics
| Topic | Direction | Type |
|---|---|---|
| `/cmd_vel` | Subscribe | geometry_msgs/Twist |
| `/odom` | Publish | nav_msgs/Odometry |
| `/imu` | Publish | sensor_msgs/Imu |
| `/stair_sensor` | Publish | sensor_msgs/Range |
| `/r2d2/chassis/status` | Publish | std_msgs/String |

### config.h (Pin Definitions)
```cpp
// UART2 – MD25
#define MD25_UART        Serial2
#define MD25_BAUD        9600
#define MD25_TX_PIN      17
#define MD25_RX_PIN      16

// I2C Bus 0
#define I2C0_SDA_PIN     21
#define I2C0_SCL_PIN     22
#define HMC5883L_ADDR    0x1E
#define SRF02_ADDR       0x70

// SPI – SSD1306 OLED
#define OLED_CLK_PIN     18
#define OLED_MOSI_PIN    23
#define OLED_CS_PIN       5
#define OLED_DC_PIN       2
#define OLED_RST_PIN      4
```

## Head ESP32 (LOLIN D32)

### Responsibilities
- A4988 stepper motor für Kopfrotation (±100°)
- SerLCD 40x2 display (UART, 5V via logic level converter)
- Ultrasonic distance sensor (I2C)
- Verbunden via Bluetooth micro-ROS

> **Hinweis:** Die HT16K33 RGB 8x8 Matrix wurde vom Head ESP32
> zum **Cortex ESP32** verschoben – Status soll auch ohne aktiven Pi sichtbar sein.

### Bus Layout
```
I2C Bus 1 (GPIO 16/17)  →  Ultrasonic (head)
UART + LLC              →  SerLCD 40x2 (5V via BSS138/LLC)
GPIO 26 STEP + 27 DIR   →  A4988 stepper
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

**Problem:** `micro_ros_platformio` schlägt auf Jazzy/ARM64 fehl.
**Lösung:** Prebuilt static library aus `micro_ros_arduino` v2.0.8-jazzy Release.
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

**Wichtig:** ESP32 verbindet sich auf `/dev/ttyACM0` (nicht ttyUSB0).
Der Firmware-Code nutzt `set_microros_transports()` (kein Argument) – nicht
`set_microros_serial_transports(Serial)`.
