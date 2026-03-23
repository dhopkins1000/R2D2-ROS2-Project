# ESP32 Firmware Architecture

## Overview

Two ESP32 nodes + one Cortex ESP32 power controller.
All use micro-ROS (Jazzy) to communicate with the Pi.

## Chassis ESP32 (LOLIN D32)

### Responsibilities
- MD25 motor controller interface (UART)
- Differential drive: receives `/cmd_vel`, publishes `/odom`
- HMC5883L compass/IMU (I2C Bus 0)
- Stair sensor ultrasonic (I2C Bus 0)
- SSD1306 OLED status display (SPI)
- Publishes `/r2d2/chassis/status`

### Bus Layout
```
I2C Bus 0 (GPIO 21/22)  →  HMC5883L + Ultrasonic stair
UART (GPIO 16/17)        →  MD25 motor controller
SPI                      →  SSD1306 OLED
USB Serial               →  micro-ROS Agent on Pi
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
- A4988 stepper motor for head rotation
- HT16K33 RGB 8x8 LED matrix
- SerLCD 40x2 display (UART, 5V via logic level converter)
- Ultrasonic distance sensor (I2C)
- Connected via Bluetooth micro-ROS

### Bus Layout
```
I2C Bus 0 (GPIO 21/22)  →  HT16K33 RGB Matrix
I2C Bus 1 (GPIO 16/17)  →  Ultrasonic (head)
UART + 3.3V LLC         →  SerLCD 40x2
GPIO STEP + DIR         →  A4988 stepper
Bluetooth               →  micro-ROS Agent on Pi
```

### micro-ROS Topics
| Topic | Direction | Type |
|---|---|---|
| `/r2d2/head/cmd` | Subscribe | std_msgs/Float32 (angle) |
| `/r2d2/head/ultrasonic` | Publish | sensor_msgs/Range |
| `/r2d2/head/display` | Subscribe | std_msgs/String |
| `/r2d2/head/leds` | Subscribe | std_msgs/String |

## Cortex ESP32 – Power Controller

See [power_management.md](power_management.md) for full details.

### Responsibilities
- Always-on watchdog
- Power relay control (MD25, USB Hub, Pi)
- Wake/sleep sequencing
- Timer-based activation

### Connections
```
GPIO  →  Relay 1 (12V MD25)
GPIO  →  Relay 2 (5V USB Hub)
GPIO  →  Pi power enable
GPIO  →  Pi shutdown monitor (reads Pi GPIO)
Serial (optional)  →  debug
```

## micro-ROS Build Notes

`micro_ros_platformio` has known build issues on Jazzy/ARM64.

**Current workaround (WIP):**
Extract prebuilt static library from `~/microros_ws` on the Pi
and link directly in PlatformIO, bypassing the source build.

**Build environment:**
- PlatformIO installed on Pi (not Mac – needs ROS2 environment)
- `source /opt/ros/jazzy/setup.bash` required before `platformio run`
- micro-ROS Agent: `~/microros_ws` (built from source)
