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
PLATFORMIO_REPO="/tmp/micro_ros_platformio"

echo "==== micro-ROS ESP32 Library Builder ===="
echo "Ziel: ${OUTPUT_DIR}"

# --- Schritt 1: micro_ros_platformio klonen (braucht der Container als /project) ---
echo "[1/3] Klone micro_ros_platformio..."
if [ -d "${PLATFORMIO_REPO}" ]; then
    echo "      (bereits vorhanden, überspringe)"
else
    git clone --depth 1 https://github.com/micro-ROS/micro_ros_platformio.git "${PLATFORMIO_REPO}"
fi

mkdir -p "${OUTPUT_DIR}"

# --- Schritt 2: Docker Build ---
if command -v docker &>/dev/null; then
    echo "[2/3] Baue via micro-ROS Docker Image..."
    echo "      (das dauert beim ersten Mal ein paar Minuten)"

    # Der Container-Entrypoint erwartet:
    #   /project  → micro_ros_platformio Repo
    #   /custom_lib → Output: libmicroros.a + include/
    docker run --rm \
        -v "${PLATFORMIO_REPO}":/project \
        -v "${OUTPUT_DIR}":/custom_lib \
        microros/micro_ros_static_library_builder:jazzy

    echo "[OK] Docker Build abgeschlossen."

else
    echo "[2/3] Kein Docker – versuche nativen Build..."

    if [ -f "/opt/ros/jazzy/setup.bash" ]; then
        source /opt/ros/jazzy/setup.bash
    else
        echo "[ERROR] ROS2 Jazzy nicht gefunden unter /opt/ros/jazzy"
        exit 1
    fi

    echo "[3/3] Baue Library (board=lolin_d32, transport=serial, distro=jazzy)..."
    cd "${PLATFORMIO_REPO}"
    python3 library_builder.py \
        --board lolin_d32 \
        --transport serial \
        --distro jazzy \
        --output-dir "${OUTPUT_DIR}"

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
    echo "   Inhalt von ${OUTPUT_DIR}:"
    ls -la "${OUTPUT_DIR}" || true
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
