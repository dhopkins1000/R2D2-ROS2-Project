# ADR 001 – Headless Ubuntu Server, No Desktop

## Status
Accepted

## Context
R2D2 runs on a Raspberry Pi 4 (8GB) with Ubuntu 24.04.
The question was whether to install a desktop environment (GNOME minimal)
or run headless.

## Decision
Run headless. No desktop environment installed.

## Reasons
- GNOME desktop consumes 800MB–1.2GB RAM at idle → less for ROS2
- No display is ever connected to R2D2 directly
- Development happens via VS Code Remote SSH from Mac
- Visualization via Foxglove Studio on Mac (WebSocket, no X11)
- Fewer running services = more stable, less heat, less SD card writes

## Consequences
- All interaction via SSH
- Foxglove Studio replaces RViz2 / rqt for visualization
- VNC can be added later as fallback if needed (10 min setup)
