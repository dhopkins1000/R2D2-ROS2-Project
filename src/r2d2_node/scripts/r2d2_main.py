#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class R2D2Node(Node):
    def __init__(self):
        super().__init__('r2d2_node')
        self.get_logger().info('R2D2 node has been started.')

        self.publisher = self.create_publisher(
            String,
            '/r2d2_status',
            10
        )
        self.timer = self.create_timer(1.0, self.publish_status)
        self.get_logger().info('Status Publisher started and status published.')

        self.subscription = self.create_subscription(
            String,
            '/r2d2_command',
            10,
            self.listen_command
        )

    # R2D2 Status Publisher
    def publish_status(self):
        msg = String()
        msg.data = 'R2D2 is online.'
        self.publisher.publish(msg)
        self.get_logger().info('Published: "%s"' % msg.data)

    # R2D2 Command Subscriber
    def listen_command(self, msg):
        self.get_logger().info('Received command: "%s"' % msg.data)

def main(args=None):
    rclpy.init(args=args)
    node = R2D2Node()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
