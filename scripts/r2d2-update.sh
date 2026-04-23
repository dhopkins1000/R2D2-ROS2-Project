#!/bin/bash
# =============================================================
#  R2D2 – Startup Update Script
#  Runs on every boot before ROS2 services start.
#
#  Flow:
#    1. git pull origin main
#    2. If changes detected → colcon build --symlink-install
#    3. Exit 0 on success (r2d2.service starts)
#    4. Exit 1 on build failure (r2d2.service blocked)
# =============================================================

set -euo pipefail

# --- Config ---
WORKSPACE="/home/r2d2/ros2_ws"
ROS_SETUP="/opt/ros/jazzy/setup.bash"
LOG_DIR="${WORKSPACE}/logs"
LOG_FILE="${LOG_DIR}/r2d2-update.log"
GIT_REMOTE="origin"
GIT_BRANCH="main"

# --- Log-Verzeichnis anlegen falls nicht vorhanden ---
mkdir -p "${LOG_DIR}"

# --- Logging ---
exec >> "${LOG_FILE}" 2>&1
echo ""
echo "========================================"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] R2D2 startup update"
echo "========================================"

# --- Netzwerk abwarten (max 30s) ---
echo "[INFO] Waiting for network..."
for i in $(seq 1 15); do
    if ping -c1 -W2 github.com &>/dev/null; then
        echo "[INFO] Network ready after ${i}s"
        break
    fi
    if [ "$i" -eq 15 ]; then
        echo "[WARN] No network after 30s – skipping git pull, using cached workspace"
        exit 0
    fi
    sleep 2
done

# --- Git Pull ---
cd "${WORKSPACE}"
echo "[INFO] Fetching from ${GIT_REMOTE}/${GIT_BRANCH}..."

git fetch "${GIT_REMOTE}" "${GIT_BRANCH}" 2>&1

# Prüfen ob es Änderungen gibt
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "${GIT_REMOTE}/${GIT_BRANCH}")

if [ "${LOCAL}" = "${REMOTE}" ]; then
    echo "[INFO] Already up to date (${LOCAL:0:8}) – skipping build"
    exit 0
fi

echo "[INFO] Changes detected: ${LOCAL:0:8} → ${REMOTE:0:8}"
git log --oneline "${LOCAL}..${REMOTE}" 2>&1

# Pull (fast-forward only – kein auto-merge)
git pull --ff-only "${GIT_REMOTE}" "${GIT_BRANCH}" 2>&1

# --- Colcon Build ---
echo "[INFO] Starting colcon build..."
source "${ROS_SETUP}"

cd "${WORKSPACE}"
if colcon build --symlink-install 2>&1; then
    echo "[OK] Build successful – ROS2 services will start"
    exit 0
else
    echo "[ERROR] Build FAILED – r2d2.service will NOT start"
    echo "[ERROR] Fix the error and reboot, or run manually:"
    echo "[ERROR]   cd ${WORKSPACE} && colcon build --symlink-install"
    echo "[ERROR]   sudo systemctl start r2d2.service"
    exit 1
fi
