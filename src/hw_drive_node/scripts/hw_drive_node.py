import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from hw_drive_node.lib.MD25 import MD25

class HWDriveNode(Node):
    def __init__(self):
        super().__init__('hw_drive_node')
        self.md25 = MD25(address=0x58, mode=1, debug=True)
        
        # Subscription for receiving control commands
        self.subscription = self.create_subscription(
            Twist,
            'cmd_vel',
            self.cmd_vel_callback,
            10
        )
        
        # Publisher for sending odometry data
        self.publisher = self.create_publisher(
            Odometry,
            'odom',
            10
        )

    def cmd_vel_callback(self, msg):
        linear_speed = msg.linear.x
        angular_speed = msg.angular.z
        # Convert Twist commands to motor commands and send to MD25
        left_speed, right_speed = self.twist_to_motors(linear_speed, angular_speed)
        self.md25.set_speeds(left_speed, right_speed)
        
        # Publish odometry data (this is just a placeholder)
        odom_msg = Odometry()
        self.publisher.publish(odom_msg)

    def twist_to_motors(self, linear_speed, angular_speed):
        # Convert Twist speeds to left and right wheel speeds
        # This is a simple example; you may need a more complex conversion
        left_speed = linear_speed - angular_speed
        right_speed = linear_speed + angular_speed
        return left_speed, right_speed

def main(args=None):
    rclpy.init(args=args)
    hw_drive_node = HWDriveNode()
    rclpy.spin(hw_drive_node)
    hw_drive_node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
