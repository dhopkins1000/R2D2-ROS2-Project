# Bill of Materials

## Main Computer
| Component | Model | Interface | Notes |
|---|---|---|---|
| Single Board Computer | Raspberry Pi 4 (8GB) | – | Ubuntu 24.04 Server ARM64 |

## Cameras & Vision
| Component | Model | Interface | Notes |
|---|---|---|---|
| 3D Depth Camera | ASUS Xtion Pro | USB | openni2 driver, RGB + Depth + IR |
| Webcam | USB Webcam | USB | Front camera, MJPEG |

## Audio
| Component | Model | Interface | Notes |
|---|---|---|---|
| Microphone Array | ReSpeaker Mic Array V1.0 | USB | 7 mics, DSP, DOA, 8ch |
| Amplifier | Mini USB Amplifier | 3.5mm / USB | In chassis |
| Speaker | – | – | In chassis |

## Drive System
| Component | Model | Interface | Notes |
|---|---|---|---|
| Motor Controller | MD25 | UART | Dual DC, encoders, built-in PID |
| Drive Motors | 2x DC Motor | MD25 | With encoders, differential drive |

## ESP32 Boards
| Component | Model | Interface | Notes |
|---|---|---|---|
| Chassis ESP32 | LOLIN D32 | USB-C | micro-ROS, motors/sensors |
| Head ESP32 | LOLIN D32 | USB-C / BT | micro-ROS, head/display |
| Cortex ESP32 | LOLIN D32 | – | Power controller, always-on |

## Sensors
| Component | Model | Interface | Location | Notes |
|---|---|---|---|---|
| IMU / Compass | HMC5883L (GY-273) | I2C | Chassis | 3-axis compass |
| Ultrasonic | – | I2C | Chassis | Stair / downward detection |
| Ultrasonic | – | I2C | Head | Forward distance |

## Head Components
| Component | Model | Interface | Notes |
|---|---|---|---|
| Stepper Motor | – | GPIO (A4988) | Head rotation, max ±100° |
| Stepper Driver | A4988 / A4983 | GPIO STEP/DIR | – |
| LED Matrix | HT16K33 8x8 RGB | I2C | In dome |
| LCD Display | SparkFun SerLCD 40x2 | UART | 5V, needs logic level converter |

## Power
| Component | Notes |
|---|---|
| Battery | 12V, target ≥20Ah for 4h runtime |
| Powered USB Hub | Must support PPPS (per-port power switching), uhubctl compatible |
| 5V Regulator | For Pi + USB Hub |
| Relays | For switching 12V (MD25) and 5V (USB Hub) |
| Logic Level Converter | 3.3V → 5V for SerLCD RX line |

## Connectivity
| Component | Notes |
|---|---|
| USB Spiral Cable | Pi → ReSpeaker through head rotation axis |
| USB Slim Cables | For tight chassis routing |
