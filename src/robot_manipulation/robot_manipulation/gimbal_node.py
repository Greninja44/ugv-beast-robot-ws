#!/usr/bin/env python3
"""robot_manipulation — aim the 2-DOF pan-tilt gimbal at a perception target.

Subscribes to robot_perception `Percept` and computes the pan/tilt (rad) needed to
point `pt_camera_link` at the target. This scaffold logs the solution; on the Pi, send
it to the vendor gimbal command path (via ugv_driver / the `behavior` action) — do NOT
open /dev/serial0 directly.
"""
import math

import rclpy
from rclpy.node import Node
from robot_interfaces.msg import Percept


class GimbalNode(Node):
    def __init__(self):
        super().__init__('gimbal_node')
        self.declare_parameter('percept_topic', '/perception_node/percepts')
        topic = self.get_parameter('percept_topic').value
        self.sub = self.create_subscription(Percept, topic, self.on_percept, 10)
        self.get_logger().info(f'robot_manipulation up; aiming gimbal from {topic}')

    def on_percept(self, p: Percept):
        pan = math.atan2(p.position.y, p.position.x)
        dist_xy = math.hypot(p.position.x, p.position.y)
        tilt = math.atan2(p.position.z, dist_xy) if dist_xy > 1e-3 else 0.0
        self.get_logger().info(
            f"aim '{p.label}': pan={math.degrees(pan):+.1f}deg tilt={math.degrees(tilt):+.1f}deg")
        # TODO(Pi): forward pan/tilt to vendor gimbal (ugv_driver encode / behavior action).


def main(args=None):
    rclpy.init(args=args)
    node = GimbalNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
