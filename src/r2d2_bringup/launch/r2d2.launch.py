#!/usr/bin/env python3
"""
Top-Level Launch-Datei für den R2D2-Roboter.

Startet:
  - audio.launch.py     (ReSpeaker, Wake Word, Whisper STT, Voice Output)
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
    audio_dir   = get_package_share_directory('r2d2_audio')

    audio_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(audio_dir, 'launch', 'audio.launch.py')
        ),
    )

    cameras_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_dir, 'launch', 'cameras.launch.py')
        ),
    )

    foxglove_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_dir, 'launch', 'foxglove.launch.py')
        ),
    )

    return LaunchDescription([
        LogInfo(msg='[r2d2_bringup] Starte R2D2-Bringup...'),
        audio_launch,
        cameras_launch,
        foxglove_launch,
        LogInfo(msg='[r2d2_bringup] Alle Launch-Aktionen gestartet.'),
    ])
