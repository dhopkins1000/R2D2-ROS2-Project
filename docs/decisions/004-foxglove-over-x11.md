# ADR 004 – Foxglove Studio over X11 Forwarding

## Status
Accepted

## Context
Development happens on a Mac. ROS2 GUI tools (RViz2, rqt) require
a display. X11 forwarding via XQuartz was the traditional approach.

## Decision
Use Foxglove Studio on Mac via WebSocket (foxglove_bridge on Pi).

## Reasons
- X11 on Mac via XQuartz is unreliable: latency, crashes, poor HiDPI support
- Foxglove Studio runs natively on Mac
- WebSocket connection is low-latency and reliable on local network
- Foxglove supports all required visualizations: Image, PointCloud, TF, Plot
- foxglove_bridge integrates cleanly as a ROS2 node
- No display server needed on Pi

## Consequences
- RViz2 not used directly (Foxglove covers all use cases)
- foxglove_bridge runs as part of r2d2_bringup systemd service
- WebSocket port 8765 must be accessible on local network
