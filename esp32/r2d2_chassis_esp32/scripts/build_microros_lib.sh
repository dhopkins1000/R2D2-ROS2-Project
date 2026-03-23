#!/bin/bash
# ============================================================
# build_microros_lib.sh
# Baut die micro-ROS Client Static Library für ESP32 (Jazzy)
# auf dem Raspberry Pi – umgeht den ARM64-Source-Build-Bug
# in micro_ros_platformio.
#
# Aufruf: bash esp32/r2d2_chassis_esp32/scripts/build_microros_lib.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_DIR}/lib/microros"

echo "==== micro-ROS ESP32 Library Builder ===="
echo "Ziel: ${OUTPUT_DIR}"

# --- Schritt 1: Docker prüfen (einfachster Build-Weg) ---
if command -v docker &>/dev/null; then
    echo "[1/3] Docker gefunden – baue via micro-ROS Docker Image..."
    mkdir -p "${OUTPUT_DIR}/include"

    docker run --rm \
        -v "${OUTPUT_DIR}":/custom_lib \
        microros/micro_ros_static_library_builder:jazzy \
        bash -c "
            cd / && \
            ros2 run micro_ros_setup create_firmware_ws.sh generate_lib && \
            ros2 run micro_ros_setup build_firmware.sh && \
            cp /firmware/build/libmicroros.a /custom_lib/ && \
            cp -r /firmware/build/include /custom_lib/ \
        "
    echo "[OK] Library gebaut via Docker."

# --- Fallback: Native Build mit vorhandenen ROS2-Tools ---
else
    echo "[1/3] Kein Docker – versuche nativen Build..."

    # ROS2 sourcen
    if [ -f "/opt/ros/jazzy/setup.bash" ]; then
        source /opt/ros/jazzy/setup.bash
    else
        echo "[ERROR] ROS2 Jazzy nicht gefunden unter /opt/ros/jazzy"
        exit 1
    fi

    # micro_ros_platformio temporär klonen
    TMPDIR=$(mktemp -d)
    echo "[2/3] Klone micro_ros_platformio nach ${TMPDIR}..."
    git clone --depth 1 https://github.com/micro-ROS/micro_ros_platformio.git "${TMPDIR}/micro_ros_platformio"

    mkdir -p "${OUTPUT_DIR}/include"

    echo "[3/3] Baue Library (board=lolin_d32, transport=serial, distro=jazzy)..."
    cd "${TMPDIR}/micro_ros_platformio"
    python3 library_builder.py \
        --board lolin_d32 \
        --transport serial \
        --distro jazzy \
        --output-dir "${OUTPUT_DIR}"

    # Aufräumen
    rm -rf "${TMPDIR}"
    echo "[OK] Library gebaut (nativer Build)."
fi

# --- Ergebnis prüfen ---
echo ""
echo "==== Ergebnis ===="
if [ -f "${OUTPUT_DIR}/libmicroros.a" ]; then
    echo "✅ libmicroros.a  →  ${OUTPUT_DIR}/libmicroros.a"
    ls -lh "${OUTPUT_DIR}/libmicroros.a"
else
    echo "❌ libmicroros.a nicht gefunden – Build fehlgeschlagen."
    exit 1
fi

if [ -d "${OUTPUT_DIR}/include" ]; then
    echo "✅ include/       →  ${OUTPUT_DIR}/include/"
else
    echo "❌ include/ nicht gefunden."
    exit 1
fi

echo ""
echo "Jetzt kannst Du in VS Code / PlatformIO bauen:"
echo "  cd esp32/r2d2_chassis_esp32"
echo "  pio run"
