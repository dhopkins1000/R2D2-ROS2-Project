# Wiring Plan

## Status
🚧 Work in progress – ESP32 re-wiring pending

## Raspberry Pi 4 USB Ports

```
USB-A Port 1  →  ASUS Xtion Pro
USB-A Port 2  →  USB Webcam
USB-A Port 3  →  Chassis ESP32 (micro-ROS Serial)
USB-A Port 4  →  Powered USB Hub
                   ├── Hub Port 1: ReSpeaker (via spiral cable through head axis)
                   └── Hub Port 2-4: reserved
USB-C         →  Power input (5V/3A dedicated PSU)
```

## Chassis ESP32 Pinout

```
I2C Bus 0:
  GPIO 21 (SDA)  →  HMC5883L SDA
                 →  Ultrasonic SDA
  GPIO 22 (SCL)  →  HMC5883L SCL
                 →  Ultrasonic SCL

UART:
  GPIO 16 (TX)   →  MD25 RX
  GPIO 17 (RX)   →  MD25 TX

SPI:
  GPIO 18 (CLK)  →  SSD1306 CLK
  GPIO 23 (MOSI) →  SSD1306 MOSI
  GPIO  5 (CS)   →  SSD1306 CS
  GPIO 17 (DC)   →  SSD1306 DC
  GPIO 16 (RST)  →  SSD1306 RST

USB-C            →  Pi USB (micro-ROS Serial + Power)
```

## Head ESP32 Pinout

```
I2C Bus 0:
  GPIO 21 (SDA)  →  HT16K33 SDA
  GPIO 22 (SCL)  →  HT16K33 SCL

I2C Bus 1:
  GPIO 16 (SDA)  →  Ultrasonic SDA
  GPIO 17 (SCL)  →  Ultrasonic SCL

UART:
  GPIO  1 (TX)   →  LLC →  SerLCD RX (5V)

GPIO:
  GPIO 26        →  A4988 STEP
  GPIO 27        →  A4988 DIR

Bluetooth        →  Pi (micro-ROS)
```

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
- USB-A (Pi Hub) → USB Micro-B (ReSpeaker)
- Cable management: secure at bottom of rotation axis with loop

## Power Wiring

```
12V Battery
    ├── Cortex ESP32 (via 5V buck converter, always on)
    ├── Relay 1 → MD25 12V input
    ├── Relay 2 → 5V buck → Powered USB Hub
    └── 5V buck → Raspberry Pi 4 (USB-C)
```

## Notes
- All ESP32 logic is 3.3V – verify 5V tolerance before direct connection
- SerLCD requires logic level conversion on RX line
- MD25 I2C address: 0x58 (default)
- HMC5883L I2C address: 0x1E
- HT16K33 I2C address: 0x70 (default)
