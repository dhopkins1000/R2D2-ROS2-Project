#!/bin/bash
# ============================================================
# build_microros_lib.sh
# Lädt die fertig kompilierte micro-ROS Library für ESP32
# direkt vom micro_ros_arduino GitHub Release herunter.
#
# Aufruf:
#   bash esp32/r2d2_chassis_esp32/scripts/build_microros_lib.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_DIR}/lib/microros"

RELEASE_URL="https://github.com/micro-ROS/micro_ros_arduino/archive/refs/tags/v2.0.8-jazzy.zip"
RELEASE_ZIP="/tmp/micro_ros_arduino_jazzy.zip"
EXTRACT_DIR="/tmp/micro_ros_arduino_jazzy"
REPO_DIR="${EXTRACT_DIR}/micro_ros_arduino-2.0.8-jazzy"

echo "==== micro-ROS ESP32 Library Downloader ===="
echo "Release: v2.0.8-jazzy"
echo "Ziel:    ${OUTPUT_DIR}"
echo ""

# --- Schritt 1: ZIP herunterladen ---
echo "[1/4] Lade micro_ros_arduino v2.0.8-jazzy herunter..."
if [ -f "${RELEASE_ZIP}" ]; then
    echo "      (bereits vorhanden, überspringe Download)"
else
    wget -q --show-progress -O "${RELEASE_ZIP}" "${RELEASE_URL}"
fi

# --- Schritt 2: Extrahieren ---
echo "[2/4] Extrahiere ZIP..."
rm -rf "${EXTRACT_DIR}"
mkdir -p "${EXTRACT_DIR}"
unzip -q "${RELEASE_ZIP}" -d "${EXTRACT_DIR}"

if [ ! -d "${REPO_DIR}" ]; then
    echo "[ERROR] Erwartetes Verzeichnis nicht gefunden: ${REPO_DIR}"
    ls -la "${EXTRACT_DIR}"
    exit 1
fi

# --- Schritt 3: Library + Headers kopieren ---
echo "[3/4] Kopiere ESP32 Library nach ${OUTPUT_DIR}..."

ESP32_LIB="${REPO_DIR}/src/esp32"

if [ ! -f "${ESP32_LIB}/libmicroros.a" ]; then
    echo "[ERROR] libmicroros.a nicht gefunden unter ${ESP32_LIB}"
    ls -la "${ESP32_LIB}/" || true
    exit 1
fi

rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}/include"

# Library
cp "${ESP32_LIB}/libmicroros.a" "${OUTPUT_DIR}/"

# Headers: In micro_ros_arduino liegen sie direkt als Unterordner in src/
# (src/std_msgs/, src/rcl/, src/rmw/ etc.) – nicht in src/include/
# Wir kopieren alle Unterordner aus src/ außer den Board-spezifischen Ordnern
echo "      Kopiere Header-Verzeichnisse aus src/..."
for dir in "${REPO_DIR}/src"/*/; do
    dirname=$(basename "${dir}")
    # Board-Verzeichnisse überspringen (enthalten .a files, keine Headers)
    case "${dirname}" in
        esp32|cortex_m0|cortex_m3|cortex_m4|cortex_m7|samd|sam|teensy*|portenta*|giga*|opta*|renesas*)
            echo "      Überspringe Board-Verzeichnis: ${dirname}"
            ;;
        *)
            cp -r "${dir}" "${OUTPUT_DIR}/include/"
            ;;
    esac
done

# --- Schritt 4: Aufräumen ---
echo "[4/4] Räume auf..."
rm -rf "${EXTRACT_DIR}"

# --- Ergebnis prüfen ---
echo ""
echo "==== Ergebnis ===="

if [ -f "${OUTPUT_DIR}/libmicroros.a" ]; then
    echo "✅ libmicroros.a"
    ls -lh "${OUTPUT_DIR}/libmicroros.a"
else
    echo "❌ libmicroros.a nicht gefunden."
    exit 1
fi

HEADER_COUNT=$(ls "${OUTPUT_DIR}/include" | wc -l)
if [ "${HEADER_COUNT}" -gt 0 ]; then
    echo "✅ include/ (${HEADER_COUNT} Pakete)"
    ls "${OUTPUT_DIR}/include"
else
    echo "❌ include/ leer oder nicht gefunden."
    exit 1
fi

echo ""
echo "✅ Fertig! Nächster Schritt:"
echo "   cd esp32/r2d2_chassis_esp32 && pio run"
