#!/usr/bin/env python3
"""Startet den Foxglove Bridge WebSocket-Server."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    bringup_dir = get_package_share_directory('r2d2_bringup')
    foxglove_params = os.path.join(bringup_dir, 'config', 'foxglove_params.yaml')

    foxglove_node = Node(
        package='foxglove_bridge',
        executable='foxglove_bridge',
        name='foxglove_bridge',
        parameters=[foxglove_params],
        respawn=False,
        output='screen',
    )

    return LaunchDescription([
        foxglove_node,
    ])
