from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='r2d2_base',
            executable='odom_tf_broadcaster',
            name='odom_tf_broadcaster',
            output='screen',
        ),
    ])
