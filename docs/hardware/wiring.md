# Wiring Plan

## Status
✅ Chassis ESP32 wiring finalized (2026-03-25)
🚧 Head ESP32 + Cortex ESP32 wiring pending

## Raspberry Pi 4 USB Ports

```
USB-A Port 1  →  ASUS Xtion Pro
USB-A Port 2  →  USB Webcam
USB-A Port 3  →  Chassis ESP32 (micro-ROS Serial, /dev/ttyACM0)
USB-A Port 4  →  Powered USB Hub (PPPS, uhubctl compatible)
                   ├── Hub Port 1: ReSpeaker (via spiral cable through head axis)
                   └── Hub Port 2-4: reserved
USB-C         →  Power input (5V/3A dedicated PSU)
```

## Chassis ESP32 Pinout (LOLIN D32)

### Decision: MD25 on UART (not I2C)
MD25 was moved from I2C to UART to prevent I2C bus blocking during
high-frequency encoder polling. The SRF02 stair sensor is safety-critical
(detects drop-offs) and cannot afford delayed responses.

```
UART2 (MD25 Motor Controller):
  GPIO 17 (TX2)  →  MD25 RX          (direct, 3.3V tolerated by MD25)
  GPIO 16 (RX2)  ←  MD25 TX          (via 1kΩ/2kΩ voltage divider → 3.3V)
                    Divider: MD25_TX → 1kΩ → ESP32_RX
                                           → 2kΩ → GND

I2C Bus 0 (GPIO 21/22):
  GPIO 21 (SDA)  →  HMC5883L SDA     (3.3V direct)
                 →  SRF02 SDA         (via BSS138 bidirectional shifter)
  GPIO 22 (SCL)  →  HMC5883L SCL     (3.3V direct)
                 →  SRF02 SCL         (via BSS138 bidirectional shifter)

SPI (SSD1306 OLED - Adafruit v2.1 with onboard level shifter):
  GPIO 18 (CLK)  →  OLED CLK
  GPIO 23 (MOSI) →  OLED MOSI (DIN)
  GPIO  5 (CS)   →  OLED CS
  GPIO  2 (DC)   →  OLED DC
  GPIO  4 (RST)  →  OLED RST
  5V             →  OLED Vin          (onboard shifter handles 3.3V logic)
  GND            →  OLED GND
  ⚠️ Do NOT connect OLED 3v3 pin to ESP32 – it's an output, not input

USB-C            →  Pi USB-A Port 3  (micro-ROS Serial + Power)
```

### I2C Addresses (no conflicts)
| Device | Address | Notes |
|---|---|---|
| HMC5883L | `0x1E` | Compass/IMU |
| SRF02 | `0x70` | Stair ultrasonic |

### Level Shifter Requirements
| Signal | Shifter needed | Type |
|---|---|---|
| SRF02 I2C SDA/SCL | **Yes – mandatory** | BSS138 bidirectional (5V device) |
| MD25 TX → ESP32 RX | Yes | 1kΩ/2kΩ voltage divider |
| MD25 RX ← ESP32 TX | No | MD25 tolerates 3.3V |
| SSD1306 SPI | No | Adafruit v2.1 has onboard shifter |

### BSS138 Level Shifter Wiring (SRF02 I2C)
```
ESP32 3.3V  →  BSS138 LV Vcc
SRF02 5V    →  BSS138 HV Vcc
GND         →  BSS138 GND (both sides)
ESP32 SDA   →  BSS138 LV1  →  BSS138 HV1  →  SRF02 SDA
ESP32 SCL   →  BSS138 LV2  →  BSS138 HV2  →  SRF02 SCL
```

## Head ESP32 Pinout (LOLIN D32)

```
I2C Bus 1 (GPIO 16/17):
  GPIO 16 (SDA)  →  Ultrasonic (head) SDA
  GPIO 17 (SCL)  →  Ultrasonic (head) SCL

UART + LLC:
  GPIO  1 (TX)   →  BSS138/LLC LV  →  HV  →  SerLCD RX (5V)

GPIO:
  GPIO 26        →  A4988 STEP
  GPIO 27        →  A4988 DIR

Bluetooth        →  Pi (micro-ROS)
```

## Cortex ESP32 Pinout (LOLIN D32) – TBD

```
I2C Bus 0 (GPIO 21/22):
  GPIO 21 (SDA)  →  HT16K33 RGB 8x8 Matrix SDA
  GPIO 22 (SCL)  →  HT16K33 RGB 8x8 Matrix SCL

GPIO (Power Control):
  GPIO xx        →  Relay 1 (12V MD25)
  GPIO xx        →  Relay 2 (5V USB Hub)
  GPIO xx        →  Pi Power Enable
  GPIO xx (IN)   →  Pi Shutdown Monitor
```
Note: Cortex ESP32 pin assignment TBD when hardware is assembled.

## Logic Level Converter (SerLCD)

```
ESP32 GPIO TX (3.3V)  →  LLC LV  →  LLC HV  →  SerLCD RX (5V)
ESP32 GND             →  LLC GND
3.3V                  →  LLC LV Vcc
5V                    →  LLC HV Vcc
```

## Head Rotation Cable

ReSpeaker USB cable routed through head rotation axis:
- Spiral/coiled cable with sufficient slack for ±100° rotation
- USB-A (Pi Hub) → USB Micro-B (ReSpeaker V1.0)
- Cable management: secure at bottom of rotation axis with loop
- Max rotation: ±100° (limited by cable)

## Power Wiring

```
12V Battery
    ├── Cortex ESP32 (via 5V buck converter, always on)
    ├── Relay 1 → MD25 12V input
    ├── Relay 2 → 5V buck → Powered USB Hub
    └── 5V buck → Raspberry Pi 4 (USB-C)
```

## Component Notes
- All ESP32 logic is 3.3V
- SRF02 is 5V → BSS138 bidirectional shifter **mandatory**
- MD25 default mode: I2C address 0x58, UART at 9600 baud
- MD25 UART mode: set via jumper on board
- SSD1306 (Adafruit v2.1): onboard 3.3V regulator + level shifter
- HMC5883L (GY-273): 3.3V compatible, direct connection safe
- SRF02 I2C address: 0x70 (default, changeable)
