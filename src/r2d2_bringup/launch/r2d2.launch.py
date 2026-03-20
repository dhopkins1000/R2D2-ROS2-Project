#!/usr/bin/env python3
"""
Top-Level Launch-Datei für den R2D2-Roboter.

Startet:
  - cameras.launch.py   (ASUS Xtion Pro + USB-Webcam)
  - foxglove.launch.py  (Foxglove Bridge WebSocket auf Port 8765)
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    bringup_dir = get_package_share_directory('r2d2_bringup')
    launch_dir = os.path.join(bringup_dir, 'launch')

    cameras_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'cameras.launch.py')
        ),
    )

    foxglove_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'foxglove.launch.py')
        ),
    )

    return LaunchDescription([
        LogInfo(msg='[r2d2_bringup] Starte R2D2-Bringup...'),
        cameras_launch,
        foxglove_launch,
        LogInfo(msg='[r2d2_bringup] Alle Launch-Aktionen gestartet.'),
    ])
