#!/bin/bash
# ============================================================
# build_microros_lib.sh
# Nur als Fallback – normalerweise reicht `pio run`.
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

# --- Submodule korrekt klonen ---
echo "[1/3] Klone micro_ros_platformio (inkl. Submodule)..."
if [ -d "${PLATFORMIO_REPO}" ]; then
    echo "      (bereits vorhanden, überspringe)"
else
    # WICHTIG: --recurse-submodules – sonst fehlt microros_static_library/
    git clone --depth 1 --recurse-submodules \
        https://github.com/micro-ROS/micro_ros_platformio.git \
        "${PLATFORMIO_REPO}"
fi

# Submodul-Pfad prüfen
if [ ! -f "${PLATFORMIO_REPO}/microros_static_library/library_generation/library_generation.sh" ]; then
    echo "[ERROR] library_generation.sh nicht gefunden – Submodule fehlen?"
    echo "Versuche: cd ${PLATFORMIO_REPO} && git submodule update --init --recursive"
    cd "${PLATFORMIO_REPO}" && git submodule update --init --recursive
fi

mkdir -p "${OUTPUT_DIR}"

# --- Docker Build ---
if command -v docker &>/dev/null; then
    echo "[2/3] Baue via micro-ROS Docker Image..."
    echo "      /project → ${PLATFORMIO_REPO}"
    echo "      /custom_lib → ${OUTPUT_DIR}"

    docker run --rm \
        -v "${PLATFORMIO_REPO}":/project \
        -v "${OUTPUT_DIR}":/custom_lib \
        microros/micro_ros_static_library_builder:jazzy

    echo "[OK] Docker Build abgeschlossen."
else
    echo "[ERROR] Docker nicht gefunden. Bitte Docker installieren."
    exit 1
fi

# --- Ergebnis prüfen ---
echo ""
echo "==== Ergebnis ===="
if [ -f "${OUTPUT_DIR}/libmicroros.a" ]; then
    echo "✅ libmicroros.a  →  ${OUTPUT_DIR}/libmicroros.a"
    ls -lh "${OUTPUT_DIR}/libmicroros.a"
else
    echo "❌ libmicroros.a nicht gefunden."
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
echo "Fertig! Jetzt: cd esp32/r2d2_chassis_esp32 && pio run"
