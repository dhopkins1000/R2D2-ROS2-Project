#!/usr/bin/env python3
"""
soul.launch.py

Startet alle fertigen Nodes des r2d2_soul Package:
  - mood_node  : Emotionaler Zustandsvektor, persistiert in State File.
  - llm_node   : Lauscht auf /r2d2/llm_input, ruft gemini-cli auf,
                 publiziert strukturierten JSON-Response auf /r2d2/llm_response.

Noch NICHT gestartet (ausstehend):
  - memory_node         (noch nicht implementiert)
  - context_builder     (noch nicht implementiert)
  - behavior_tree       (noch nicht implementiert)
  - voice_input_node    (zurueckgestellt)
  - whisper_stt_node    (zurueckgestellt)
"""

from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node


def generate_launch_description():

    mood_node = Node(
        package='r2d2_soul',
        executable='mood_node',
        name='mood_node',
        output='screen',
        parameters=[{
            'state_file':    '/home/r2d2/soul/state/mood.json',
            'publish_rate':  1.0,
            'save_interval': 30.0,
        }],
    )

    llm_node = Node(
        package='r2d2_soul',
        executable='llm_node',
        name='llm_node',
        output='screen',
        parameters=[{
            'soul_workspace': '/home/r2d2/soul',
            'model':          'gemini-2.5-flash',
        }],
    )

    return LaunchDescription([
        LogInfo(msg='[r2d2_soul] Starte Soul-Layer...'),
        mood_node,
        llm_node,
        LogInfo(msg='[r2d2_soul] mood_node + llm_node gestartet.'),
    ])
