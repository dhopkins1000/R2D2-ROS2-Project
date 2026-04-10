#!/usr/bin/env python3
"""
Launch robot_state_publisher mit R2D2 URDF.
Published Topics:
  /robot_description  (std_msgs/String)
  /tf                 (tf2_msgs/TFMessage)
  /tf_static          (tf2_msgs/TFMessage)
"""

import os
import xacro

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('r2d2_description')
    xacro_file = os.path.join(pkg_dir, 'urdf', 'r2d2.urdf.xacro')

    robot_description = xacro.process_file(xacro_file).toxml()

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': False,
        }]
    )

    # joint_state_publisher für die Räder (Encoder-Daten kommen später aus Odometrie)
    joint_state_publisher = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher',
        output='screen',
    )

    return LaunchDescription([
        robot_state_publisher,
        joint_state_publisher,
    ])
