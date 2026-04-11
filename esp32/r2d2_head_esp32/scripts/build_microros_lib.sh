#!/bin/bash
# Identisch mit Chassis-Skript – zieht prebuilt micro-ROS Library
# fuer Head ESP32
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."
bash ../r2d2_chassis_esp32/scripts/build_microros_lib.sh
