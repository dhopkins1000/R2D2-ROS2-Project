from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import LogInfo
import os


def generate_launch_description():
    # Sounds are located inside the Python package directory
    # (placed there by Claude Code during initial setup)
    sounds_dir = os.path.expanduser(
        '~/ros2_ws/src/r2d2_audio/r2d2_audio/sounds'
    )

    return LaunchDescription([
        LogInfo(msg='[r2d2_audio] Starte Audio-Nodes...'),

        # ReSpeaker: DOA + audio stream
        Node(
            package='r2d2_audio',
            executable='respeaker_node',
            name='respeaker',
            output='screen',
        ),

        # Wake Word Detection
        Node(
            package='r2d2_audio',
            executable='wake_word_node',
            name='wake_word',
            output='screen',
            parameters=[{
                'threshold': 0.5,
                'listen_timeout': 5.0,
                'model_path': '',
            }],
        ),

        # Whisper STT (triggered by wake word)
        Node(
            package='r2d2_audio',
            executable='whisper_node',
            name='whisper',
            output='screen',
            parameters=[{
                'model_size': 'tiny',
                'language': 'de',
                'record_seconds': 5.0,
            }],
        ),

        # Voice Output (sample-based R2D2 voice)
        # Plays startup sound automatically on init.
        # Subscribes to /r2d2/voice_intent, publishes /r2d2/voice_playing.
        Node(
            package='r2d2_audio',
            executable='voice_node',
            name='voice',
            output='screen',
            parameters=[{
                'sounds_dir':       sounds_dir,
                'alsa_device':      'plughw:1,0',
                'queue_while_busy': False,
            }],
        ),

        LogInfo(msg='[r2d2_audio] Alle Audio-Nodes gestartet.'),
    ])
