#!/usr/bin/env python3
"""
Top-Level Launch-Datei fuer den R2D2-Roboter.

Startet:
  - cameras.launch.py       (ASUS Xtion Pro + USB-Webcam)
  - foxglove.launch.py      (Foxglove Bridge WebSocket auf Port 8765)
  - description.launch.py   (robot_state_publisher + joint_state_publisher)
  - base.launch.py          (odom->base_link TF broadcaster)
  - audio.launch.py         (ReSpeaker, Wake Word, Whisper STT, Voice Output)
  - soul.launch.py          (LLM Node / Claude Code Interface)
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    bringup_dir     = get_package_share_directory('r2d2_bringup')
    description_dir = get_package_share_directory('r2d2_description')
    base_dir        = get_package_share_directory('r2d2_base')
    audio_dir       = get_package_share_directory('r2d2_audio')
    soul_dir        = get_package_share_directory('r2d2_soul')

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

    description_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(description_dir, 'launch', 'description.launch.py')
        ),
    )

    base_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(base_dir, 'launch', 'base.launch.py')
        ),
    )

    audio_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(audio_dir, 'launch', 'audio.launch.py')
        ),
    )

    soul_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(soul_dir, 'launch', 'soul.launch.py')
        ),
    )

    return LaunchDescription([
        LogInfo(msg='[r2d2_bringup] Starte R2D2-Bringup...'),
        cameras_launch,
        foxglove_launch,
        description_launch,
        base_launch,
        audio_launch,
        soul_launch,
        LogInfo(msg='[r2d2_bringup] Alle Launch-Aktionen gestartet.'),
    ])
