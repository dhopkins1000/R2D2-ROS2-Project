#!/bin/bash
# ============================================================
# build_microros_lib.sh
# Baut die micro-ROS Static Library für ESP32 (Jazzy, serial)
#
# Voraussetzungen:
#   - Docker installiert und laufend
#
# Aufruf:
#   bash esp32/r2d2_chassis_esp32/scripts/build_microros_lib.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_DIR}/lib/microros"
PLATFORMIO_REPO="/tmp/micro_ros_platformio"

echo "==== micro-ROS ESP32 Library Builder ===="
echo "Ziel: ${OUTPUT_DIR}"
echo ""

# --- Voraussetzung: Docker ---
if ! command -v docker &>/dev/null; then
    echo "[ERROR] Docker nicht gefunden."
    exit 1
fi

# --- Schritt 1: micro_ros_platformio mit Submodulen klonen ---
echo "[1/3] Klone micro_ros_platformio (inkl. Submodule)..."

if [ -d "${PLATFORMIO_REPO}" ]; then
    # Bereits vorhanden – prüfen ob Submodule da sind
    if [ ! -f "${PLATFORMIO_REPO}/microros_static_library/library_generation/library_generation.sh" ]; then
        echo "      Submodule fehlen – lade nach..."
        cd "${PLATFORMIO_REPO}"
        git submodule update --init --recursive
        cd -
    else
        echo "      Bereits vorhanden mit Submodulen – überspringe."
    fi
else
    git clone \
        --recurse-submodules \
        https://github.com/micro-ROS/micro_ros_platformio.git \
        "${PLATFORMIO_REPO}"
fi

# Sicherheitscheck
if [ ! -f "${PLATFORMIO_REPO}/microros_static_library/library_generation/library_generation.sh" ]; then
    echo "[ERROR] library_generation.sh immer noch nicht gefunden!"
    echo "        Pfad: ${PLATFORMIO_REPO}/microros_static_library/library_generation/"
    ls -la "${PLATFORMIO_REPO}/" || true
    exit 1
fi

echo "      library_generation.sh gefunden ✅"

# --- Schritt 2: Output-Verzeichnis vorbereiten ---
mkdir -p "${OUTPUT_DIR}"

# --- Schritt 3: Docker Build ---
echo ""
echo "[2/3] Starte Docker Build..."
echo "      Mounts:"
echo "        /project    ← ${PLATFORMIO_REPO}"
echo "        /custom_lib ← ${OUTPUT_DIR}"
echo "      MICROROS_LIBRARY_FOLDER=microros_static_library"
echo "      (dauert ~5-15 Min beim ersten Mal)"
echo ""

docker run --rm \
    -v "${PLATFORMIO_REPO}":/project \
    -v "${OUTPUT_DIR}":/custom_lib \
    --env MICROROS_LIBRARY_FOLDER=microros_static_library \
    microros/micro_ros_static_library_builder:jazzy

echo ""
echo "[3/3] Prüfe Ergebnis..."

# --- Ergebnis prüfen ---
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
    echo "✅ include/ ($(ls ${OUTPUT_DIR}/include | wc -l) Einträge)"
else
    echo "❌ include/ nicht gefunden."
    exit 1
fi

echo ""
echo "✅ Fertig! Nächster Schritt:"
echo "   cd esp32/r2d2_chassis_esp32 && pio run"
