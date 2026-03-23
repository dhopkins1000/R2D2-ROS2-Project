#!/bin/bash
# ============================================================
# build_microros_lib.sh
# Baut die micro-ROS Static Library für ESP32 (Jazzy, serial)
# via Docker micro_ros_static_library_builder
#
# Aufruf:
#   bash esp32/r2d2_chassis_esp32/scripts/build_microros_lib.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_DIR}/lib/microros"

echo "==== micro-ROS ESP32 Library Builder ===="
echo "Ziel:      ${OUTPUT_DIR}"
echo "Distro:    jazzy"
echo "Transport: serial"
echo ""

mkdir -p "${OUTPUT_DIR}"

if ! command -v docker &>/dev/null; then
    echo "[ERROR] Docker nicht gefunden."
    exit 1
fi

echo "[1/2] Starte Docker Build..."
echo "      (erster Lauf: Image bereits gecacht, dauert ~5-10 Min)"
echo ""

# Korrekter Aufruf: Image-Entrypoint nimmt -d (distro) und -t (transport)
# als direkte Argumente. Nur /custom_lib muss gemountet werden.
docker run --rm \
    -v "${OUTPUT_DIR}":/custom_lib \
    microros/micro_ros_static_library_builder:jazzy \
    -d jazzy \
    -t serial

echo ""
echo "[2/2] Prüfe Ergebnis..."

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
    echo "✅ include/"
    echo "   $(ls ${OUTPUT_DIR}/include | wc -l) Header-Verzeichnisse"
else
    echo "❌ include/ nicht gefunden."
    exit 1
fi

echo ""
echo "✅ Fertig! Nächster Schritt:"
echo "   cd esp32/r2d2_chassis_esp32 && pio run"
