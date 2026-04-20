#!/usr/bin/env python3
"""
soul.launch.py

Startet alle fertigen Nodes des r2d2_soul Package:
  - llm_node   : Lauscht auf /r2d2/llm_input, ruft Claude Code auf,
                 publiziert strukturierten JSON-Response auf /r2d2/llm_response.

Noch NICHT gestartet (ausstehend):
  - mood_node         (noch nicht implementiert)
  - memory_node       (noch nicht implementiert)
  - behavior_tree     (noch nicht implementiert)
  - voice_input_node  (in Entwicklung)
  - whisper_stt_node  (in Entwicklung)
"""

from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node


def generate_launch_description():
    llm_node = Node(
        package='r2d2_soul',
        executable='llm_node',
        name='llm_node',
        output='screen',
        parameters=[{
            'soul_workspace':  '/home/r2d2/soul',
            'effort':          'low',
            'session_persist': False,
        }],
    )

    return LaunchDescription([
        LogInfo(msg='[r2d2_soul] Starte Soul-Layer...'),
        llm_node,
        LogInfo(msg='[r2d2_soul] llm_node gestartet — wartet auf /r2d2/llm_input.'),
    ])
