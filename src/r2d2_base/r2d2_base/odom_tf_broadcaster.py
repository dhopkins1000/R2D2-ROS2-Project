#!/usr/bin/env python3
"""
odom_tf_broadcaster.py

Subscribes to /r2d2/chassis/odom (nav_msgs/Odometry) und broadcasted
den TF-Transform odom -> base_link damit der Roboter im Foxglove
3D Panel live mitbewegt wird.
"""

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster
from builtin_interfaces.msg import Time

import math


class OdomTFBroadcaster(Node):

    def __init__(self):
        super().__init__('odom_tf_broadcaster')

        self.tf_broadcaster = TransformBroadcaster(self)

        self.subscription = self.create_subscription(
            Odometry,
            '/r2d2/chassis/odom',
            self.odom_callback,
            10
        )

        self.get_logger().info('odom_tf_broadcaster gestartet.')

    def odom_callback(self, msg: Odometry):
        t = TransformStamped()

        # Timestamp: Pi-Zeit verwenden (ESP32 hat stamp.sec=0)
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_link'

        # Position aus Odometrie
        t.transform.translation.x = msg.pose.pose.position.x
        t.transform.translation.y = msg.pose.pose.position.y
        t.transform.translation.z = msg.pose.pose.position.z

        # Orientierung aus Odometrie (Quaternion)
        t.transform.rotation = msg.pose.pose.orientation

        self.tf_broadcaster.sendTransform(t)


def main(args=None):
    rclpy.init(args=args)
    node = OdomTFBroadcaster()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
