# Pi Autostart Setup

All R2D2 ROS2 nodes start automatically on Raspberry Pi boot via systemd.

---

## Prerequisites

The following must be installed and configured before enabling autostart:

```bash
# ROS2 Jazzy
source /opt/ros/jazzy/setup.bash

# Workspace built
cd ~/ros2_ws && colcon build

# gemini-cli installed
npm install -g @google/gemini-cli

# Google API key available
export GOOGLE_API_KEY=your_key_here
```

---

## Step 1 — Create Environment File

Create `/etc/r2d2/env` to store secrets and environment variables.
This file is read by the systemd service and never committed to git.

```bash
sudo mkdir -p /etc/r2d2
sudo tee /etc/r2d2/env << 'EOF'
GOOGLE_API_KEY=your_api_key_from_aistudio_google_com
EOF
sudo chmod 600 /etc/r2d2/env
sudo chown r2d2:r2d2 /etc/r2d2/env
```

Get a free API key at: https://aistudio.google.com/apikey

---

## Step 2 — Install systemd Service

Copy the service file and enable it:

```bash
sudo cp ~/ros2_ws/systemd/r2d2.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable r2d2.service
```

---

## Step 3 — Start and Verify

```bash
# Start manually for first test
sudo systemctl start r2d2.service

# Check status
sudo systemctl status r2d2.service

# Follow logs
journalctl -u r2d2.service -f

# Verify ROS2 topics are alive
ros2 topic list
ros2 topic echo /r2d2/mood
```

---

## Updating After Code Changes

```bash
cd ~/ros2_ws
git pull
colcon build
sudo systemctl restart r2d2.service
```

---

## Disabling Autostart

```bash
sudo systemctl disable r2d2.service
sudo systemctl stop r2d2.service
```
