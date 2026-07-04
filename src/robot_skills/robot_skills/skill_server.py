#!/usr/bin/env python3
"""robot_skills — RunSkill action server (typed replacement for vendor 'behavior').

Registers named skills and executes them. This scaffold ships a 'stop' skill (publishes a
zero /cmd_vel — safe) and a 'demo' skill (logs progress). Add real skills that call
robot_navigation actions, drive /cmd_vel, or aim the gimbal.

SAFETY: only publishes zero-velocity Twist here. Real motion skills must be tested with
the robot wheels-up or in a clear area.
"""
import time

import rclpy
from rclpy.action import ActionServer
from rclpy.node import Node
from geometry_msgs.msg import Twist
from robot_interfaces.action import RunSkill


class SkillServer(Node):
    def __init__(self):
        super().__init__('skill_server')
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self._server = ActionServer(self, RunSkill, 'run_skill', self.execute)
        self.skills = {'stop': self._skill_stop, 'demo': self._skill_demo}
        self.get_logger().info(f'robot_skills up; skills={list(self.skills)}')

    def execute(self, goal_handle):
        name = goal_handle.request.skill
        fn = self.skills.get(name)
        result = RunSkill.Result()
        if fn is None:
            self.get_logger().warn(f'unknown skill: {name}')
            goal_handle.abort()
            result.success = False
            result.result_detail = f'unknown skill: {name}'
            return result
        detail = fn(goal_handle)
        goal_handle.succeed()
        result.success = True
        result.result_detail = detail
        return result

    def _skill_stop(self, goal_handle):
        self.cmd_pub.publish(Twist())  # zero velocity
        return 'commanded stop (zero /cmd_vel)'

    def _skill_demo(self, goal_handle):
        for i in range(3):
            fb = RunSkill.Feedback()
            fb.status = f'demo step {i + 1}/3'
            fb.progress = (i + 1) / 3.0
            goal_handle.publish_feedback(fb)
            time.sleep(0.3)
        return 'demo complete'


def main(args=None):
    rclpy.init(args=args)
    node = SkillServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
