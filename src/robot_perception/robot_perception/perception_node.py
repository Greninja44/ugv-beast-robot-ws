#!/usr/bin/env python3
"""robot_perception — nearest-obstacle percept from the vendor LiDAR.

Subscribes to the vendor `/scan` (sensor_msgs/LaserScan) and publishes a
`robot_interfaces/Percept` for the closest return. This is a minimal, dependency-light
starting point — extend with camera/CV (`/image_raw`) or depth for real perception.

Interfaces ONLY with the vendor stack via topics — no vendor code is imported.
"""
import math

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from robot_interfaces.msg import Percept


class PerceptionNode(Node):
    def __init__(self):
        super().__init__('perception_node')
        self.declare_parameter('scan_topic', '/scan')
        scan_topic = self.get_parameter('scan_topic').value
        self.sub = self.create_subscription(LaserScan, scan_topic, self.on_scan, 10)
        self.pub = self.create_publisher(Percept, '~/percepts', 10)
        self.get_logger().info(f'robot_perception up; listening on {scan_topic}')

    def on_scan(self, msg: LaserScan):
        ranges = [r for r in msg.ranges if math.isfinite(r) and r > 0.0]
        if not ranges:
            return
        idx = min(range(len(msg.ranges)),
                  key=lambda i: msg.ranges[i] if math.isfinite(msg.ranges[i]) and msg.ranges[i] > 0 else math.inf)
        rng = msg.ranges[idx]
        bearing = msg.angle_min + idx * msg.angle_increment

        p = Percept()
        p.header = msg.header
        p.label = 'nearest_obstacle'
        p.confidence = 1.0
        p.position.x = rng * math.cos(bearing)
        p.position.y = rng * math.sin(bearing)
        p.position.z = 0.0
        p.bearing = bearing
        self.pub.publish(p)


def main(args=None):
    rclpy.init(args=args)
    node = PerceptionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
