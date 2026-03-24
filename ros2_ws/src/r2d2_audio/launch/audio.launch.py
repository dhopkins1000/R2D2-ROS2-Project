from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import LogInfo
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    config = os.path.join(
        get_package_share_directory('r2d2_audio'),
        'config', 'audio_params.yaml'
    )

    return LaunchDescription([
        LogInfo(msg='Starting R2D2 Audio nodes...'),

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
                'model_path': '',   # set to path of custom r2d2.onnx model
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
    ])
