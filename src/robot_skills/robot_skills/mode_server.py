#!/usr/bin/env python3
"""robot_skills — mode arbiter: hosts SetMode, publishes the active mode as latched state.

Single source of truth for "who is allowed to drive right now." skill_server (and, from
Phase 3, robot_navigation's nav_bridge) subscribe to /robot/mode and refuse to command
motion unless the mode grants them authority. This is what stops the dashboard's manual
teleop and autonomous motion (Nav2 / skills) from writing to /cmd_vel at the same time.

Modes: idle (default, nothing drives) | teleop (dashboard has authority) |
explore | track | ai (autonomous nodes have authority).
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from std_msgs.msg import String
from robot_interfaces.srv import SetMode

VALID_MODES = {'idle', 'teleop', 'explore', 'track', 'ai'}
# Modes in which autonomous nodes (skill_server, nav_bridge) are allowed to command motion.
# 'idle' and 'teleop' are deliberately excluded: 'idle' means nothing drives, 'teleop' means
# the dashboard's joystick has sole authority over /cmd_vel.
AUTONOMOUS_MODES = {'explore', 'track', 'ai'}

MODE_QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL)


class ModeServer(Node):
    def __init__(self):
        super().__init__('mode_server')
        self._mode = 'idle'
        self._pub = self.create_publisher(String, '/robot/mode', MODE_QOS)
        self._srv = self.create_service(SetMode, 'set_mode', self._on_set_mode)
        self._publish()
        self.get_logger().info(f"mode_server up; mode='{self._mode}'")

    def _publish(self):
        self._pub.publish(String(data=self._mode))

    def _on_set_mode(self, request, response):
        mode = request.mode
        if mode not in VALID_MODES:
            response.success = False
            response.message = f"invalid mode '{mode}'; valid: {sorted(VALID_MODES)}"
            return response
        prev = self._mode
        self._mode = mode
        self._publish()
        response.success = True
        response.message = f'mode changed: {prev} -> {mode}'
        self.get_logger().info(response.message)
        return response


def main(args=None):
    rclpy.init(args=args)
    node = ModeServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
