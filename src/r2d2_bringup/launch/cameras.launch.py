#!/usr/bin/env python3
"""
Launch-Datei für beide Kameras: ASUS Xtion Pro (openni2) und USB-Webcam (usb_cam).

Fehlertoleranz:
    Wenn die Xtion nicht angeschlossen ist, beendet sich der openni2_camera_driver-Prozess.
    Ein OnProcessExit-Handler loggt eine Warnung, gibt aber KEIN Shutdown-Event aus.
    Die USB-Webcam läuft unabhängig davon weiter.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    LogInfo,
    RegisterEventHandler,
)
from launch.event_handlers import OnProcessExit
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bringup_dir = get_package_share_directory('r2d2_bringup')
    webcam_params = os.path.join(bringup_dir, 'config', 'webcam_params.yaml')

    # --- Launch-Argumente ---
    xtion_ns_arg = DeclareLaunchArgument(
        'xtion_namespace',
        default_value='camera',
        description='ROS-Namespace für die Xtion Tiefenkamera',
    )
    xtion_ns = LaunchConfiguration('xtion_namespace')

    webcam_ns_arg = DeclareLaunchArgument(
        'webcam_namespace',
        default_value='webcam',
        description='ROS-Namespace für die USB-Webcam',
    )
    webcam_ns = LaunchConfiguration('webcam_namespace')

    # --- ASUS Xtion Pro via openni2_camera (normaler Node) ---
    xtion_node = Node(
        package='openni2_camera',
        executable='openni2_camera_driver',
        name='driver',
        namespace=xtion_ns,
        parameters=[
            {'depth_registration': False},
            {'use_device_time': True},
            {'rgb_frame_id': [xtion_ns, '_rgb_optical_frame']},
            {'depth_frame_id': [xtion_ns, '_depth_optical_frame']},
            {'ir_frame_id': [xtion_ns, '_ir_optical_frame']},
        ],
        respawn=False,
        output='screen',
    )

    # Fehlertoleranz: Nur Warnung loggen wenn Xtion-Prozess endet.
    # Kein Shutdown-Event → Webcam und Foxglove laufen weiter.
    xtion_exit_handler = RegisterEventHandler(
        OnProcessExit(
            target_action=xtion_node,
            on_exit=[
                LogInfo(
                    msg=(
                        '[r2d2_bringup] WARNUNG: Xtion-Node beendet. '
                        'ASUS Xtion Pro möglicherweise nicht angeschlossen. '
                        'Betrieb ohne Tiefenkamera wird fortgesetzt.'
                    )
                ),
            ],
        )
    )

    # --- USB-Webcam via usb_cam ---
    webcam_node = Node(
        package='usb_cam',
        executable='usb_cam_node_exe',
        name='usb_cam',
        namespace=webcam_ns,
        parameters=[webcam_params],
        respawn=False,
        output='screen',
    )

    return LaunchDescription([
        xtion_ns_arg,
        webcam_ns_arg,
        xtion_node,
        xtion_exit_handler,
        webcam_node,
    ])
