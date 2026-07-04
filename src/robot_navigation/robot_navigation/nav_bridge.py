#!/usr/bin/env python3
"""robot_navigation — typed NavigateTo action server that fronts vendor Nav2.

Exposes `robot_interfaces/action/NavigateTo`. In this scaffold it accepts a goal and
completes immediately (stub). To make it real on the Pi, forward the goal to Nav2's
`navigate_to_pose` action (nav2_msgs/action/NavigateToPose) — see the TODO below.

No vendor code is imported; integration is purely via ROS actions/topics.
"""
import rclpy
from rclpy.action import ActionServer
from rclpy.node import Node
from robot_interfaces.action import NavigateTo


class NavBridge(Node):
    def __init__(self):
        super().__init__('nav_bridge')
        self._server = ActionServer(self, NavigateTo, 'navigate_to', self.execute)
        # TODO(Pi): self._nav2 = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self.get_logger().info("robot_navigation up; action 'navigate_to' ready (stub → wire to Nav2)")

    def execute(self, goal_handle):
        target = goal_handle.request.target
        self.get_logger().info(
            f'NavigateTo goal: frame={target.header.frame_id} '
            f'x={target.pose.position.x:.2f} y={target.pose.position.y:.2f}')
        fb = NavigateTo.Feedback()
        fb.distance_remaining = 0.0
        goal_handle.publish_feedback(fb)
        goal_handle.succeed()
        result = NavigateTo.Result()
        result.success = True
        return result


def main(args=None):
    rclpy.init(args=args)
    node = NavBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
