#!/bin/bash
# ============================================================
# build_microros_lib.sh
# Lädt die fertig kompilierte micro-ROS Library für ESP32
# direkt vom micro_ros_arduino GitHub Release herunter.
#
# Kein Build, kein Docker, kein CMake.
# Einfach herunterladen und extrahieren.
#
# Aufruf:
#   bash esp32/r2d2_chassis_esp32/scripts/build_microros_lib.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_DIR}/lib/microros"

# Release v2.0.8-jazzy (letztes Jazzy Release von micro_ros_arduino)
RELEASE_URL="https://github.com/micro-ROS/micro_ros_arduino/archive/refs/tags/v2.0.8-jazzy.zip"
RELEASE_ZIP="/tmp/micro_ros_arduino_jazzy.zip"
EXTRACT_DIR="/tmp/micro_ros_arduino_jazzy"

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

# Entpackter Ordner heißt micro_ros_arduino-2.0.8-jazzy
REPO_DIR="${EXTRACT_DIR}/micro_ros_arduino-2.0.8-jazzy"

if [ ! -d "${REPO_DIR}" ]; then
    echo "[ERROR] Erwartetes Verzeichnis nicht gefunden: ${REPO_DIR}"
    echo "        Inhalt von ${EXTRACT_DIR}:"
    ls -la "${EXTRACT_DIR}"
    exit 1
fi

# --- Schritt 3: ESP32-Library herausziehen ---
echo "[3/4] Kopiere ESP32 Library nach ${OUTPUT_DIR}..."

# In micro_ros_arduino liegt die Library unter src/esp32/
ESP32_LIB="${REPO_DIR}/src/esp32"

if [ ! -d "${ESP32_LIB}" ]; then
    echo "[ERROR] ESP32 Library-Verzeichnis nicht gefunden: ${ESP32_LIB}"
    echo "        Verfügbare Targets unter src/:"
    ls "${REPO_DIR}/src/" || true
    exit 1
fi

rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

# libmicroros.a
if [ -f "${ESP32_LIB}/libmicroros.a" ]; then
    cp "${ESP32_LIB}/libmicroros.a" "${OUTPUT_DIR}/"
else
    echo "[ERROR] libmicroros.a nicht gefunden unter ${ESP32_LIB}"
    ls -la "${ESP32_LIB}/" || true
    exit 1
fi

# include/ Headers (liegen eine Ebene höher unter src/include/)
if [ -d "${REPO_DIR}/src/include" ]; then
    cp -r "${REPO_DIR}/src/include" "${OUTPUT_DIR}/"
else
    echo "[WARN] src/include nicht gefunden – suche alternativ..."
    find "${REPO_DIR}/src" -name "*.h" | head -5
fi

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

if [ -d "${OUTPUT_DIR}/include" ]; then
    echo "✅ include/ ($(ls ${OUTPUT_DIR}/include | wc -l) Einträge)"
else
    echo "❌ include/ nicht gefunden."
    exit 1
fi

echo ""
echo "✅ Fertig! Nächster Schritt:"
echo "   cd esp32/r2d2_chassis_esp32 && pio run"
