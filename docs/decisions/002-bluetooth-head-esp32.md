# ADR 002 – Bluetooth for Head ESP32

## Status
Accepted

## Context
The Head ESP32 sits in the R2D2 dome which rotates up to ±100°.
A wired USB connection to the Pi would require cable routing through
the rotation axis alongside the ReSpeaker USB cable.

## Decision
Connect Head ESP32 to Pi via Bluetooth (micro-ROS BLE transport).

## Reasons
- No cable routing through rotation axis for Head ESP32
- Head components (stepper, LCD, LEDs, ultrasonic) are not latency-critical
- ESP32 has Bluetooth onboard – no extra hardware needed
- Simplifies head assembly and maintenance

## Consequences
- Slight latency increase for head commands (acceptable for display/LEDs)
- Bluetooth reliability must be monitored
- micro-ROS BLE transport requires specific configuration
- Chassis ESP32 keeps USB Serial (latency-critical: motors/odometry)
