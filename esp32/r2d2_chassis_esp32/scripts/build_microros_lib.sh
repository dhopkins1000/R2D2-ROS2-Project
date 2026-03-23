#!/bin/bash
# ============================================================
# build_microros_lib.sh
# Baut die micro-ROS Static Library für ESP32 (Jazzy, serial)
#
# Strategie (in Reihenfolge):
#   1. micro_ros_setup aus ~/microros_ws  ← bereits auf dem Pi gebaut
#   2. Docker-Fallback (direkt via library_generation.sh)
#
# Aufruf:
#   bash esp32/r2d2_chassis_esp32/scripts/build_microros_lib.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_DIR}/lib/microros"
FIRMWARE_WS="/tmp/microros_firmware_ws"

echo "==== micro-ROS ESP32 Library Builder ===="
echo "Ziel: ${OUTPUT_DIR}"
echo ""

mkdir -p "${OUTPUT_DIR}"

# ============================================================
# STRATEGIE 1: micro_ros_setup (bereits in ~/microros_ws)
# ============================================================
MICROROS_WS="${HOME}/microros_ws"

if [ -f "${MICROROS_WS}/install/setup.bash" ]; then
    echo "[Strategie 1] Verwende micro_ros_setup aus ${MICROROS_WS}"

    source /opt/ros/jazzy/setup.bash
    source "${MICROROS_WS}/install/setup.bash"

    # Firmware-Workspace frisch anlegen
    rm -rf "${FIRMWARE_WS}"
    mkdir -p "${FIRMWARE_WS}"
    cd "${FIRMWARE_WS}"

    echo "[1/3] Erstelle Firmware-Workspace (generate_lib)..."
    ros2 run micro_ros_setup create_firmware_ws.sh generate_lib

    echo "[2/3] Baue Library (serial, jazzy)..."
    ros2 run micro_ros_setup build_firmware.sh

    echo "[3/3] Kopiere Ergebnis nach ${OUTPUT_DIR}..."
    # Library + Headers in unser Projektverzeichnis
    cp "${FIRMWARE_WS}/firmware/build/libmicroros.a" "${OUTPUT_DIR}/"
    cp -r "${FIRMWARE_WS}/firmware/build/include" "${OUTPUT_DIR}/"

    echo "[OK] micro_ros_setup Build abgeschlossen."

# ============================================================
# STRATEGIE 2: Docker-Fallback (library_generation.sh direkt)
# ============================================================
elif command -v docker &>/dev/null; then
    echo "[Strategie 2] Verwende Docker (micro_ros_static_library_builder)"
    echo "              micro_ros_setup nicht gefunden unter ${MICROROS_WS}"
    echo ""

    # library_generation.sh aus dem micro_ros_platformio Submodul
    LIBGEN_REPO="/tmp/microros_libgen"
    if [ ! -d "${LIBGEN_REPO}" ]; then
        echo "Klone micro_ros_platformio (inkl. Submodule)..."
        git clone --recurse-submodules \
            https://github.com/micro-ROS/micro_ros_platformio.git \
            "${LIBGEN_REPO}"
    fi

    LIBGEN_SCRIPT="${LIBGEN_REPO}/microros_static_library/library_generation/library_generation.sh"
    if [ ! -f "${LIBGEN_SCRIPT}" ]; then
        echo "[ERROR] library_generation.sh nicht gefunden!"
        echo "        Versuche: cd ${LIBGEN_REPO} && git submodule update --init --recursive"
        cd "${LIBGEN_REPO}" && git submodule update --init --recursive
    fi

    echo "Starte Docker Build..."
    docker run --rm \
        -v "${LIBGEN_REPO}/microros_static_library":/microros_static_library \
        -v "${OUTPUT_DIR}":/custom_lib \
        --workdir /microros_static_library \
        microros/micro_ros_static_library_builder:jazzy \
        bash library_generation/library_generation.sh \
            --transport serial \
            --distro jazzy \
            --output-dir /custom_lib

    echo "[OK] Docker Build abgeschlossen."

else
    echo "[ERROR] Weder micro_ros_setup noch Docker gefunden."
    echo "        Bitte einen der folgenden Schritte ausführen:"
    echo "        - micro_ros_setup in ~/microros_ws bauen"
    echo "        - Docker installieren: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

# ============================================================
# Ergebnis prüfen
# ============================================================
echo ""
echo "==== Ergebnis ===="

if [ -f "${OUTPUT_DIR}/libmicroros.a" ]; then
    echo "✅ libmicroros.a"
    ls -lh "${OUTPUT_DIR}/libmicroros.a"
else
    echo "❌ libmicroros.a nicht gefunden."
    echo "   Inhalt von ${OUTPUT_DIR}:"
    ls -la "${OUTPUT_DIR}" || true
    exit 1
fi

if [ -d "${OUTPUT_DIR}/include" ]; then
    echo "✅ include/"
    echo "   $(ls ${OUTPUT_DIR}/include | wc -l) Header-Verzeichnisse"
else
    echo "❌ include/ nicht gefunden."
    exit 1
fi

echo ""
echo "Fertig! Nächster Schritt:"
echo "  cd esp32/r2d2_chassis_esp32 && pio run"
