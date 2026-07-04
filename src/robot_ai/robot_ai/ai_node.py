#!/usr/bin/env python3
"""robot_ai — LLM decision layer (runs on WSL, talks to the Pi graph over DDS).

Skeleton: on a timer it "decides" (stubbed) and sends a RunSkill goal to robot_skills
on the Pi. Replace `decide()` with a real call to a local Ollama model (the vendor
ugv_chat_ai uses qwen2) or the Anthropic API (Claude). Keep the LLM client as a plain
pip dependency — it is not a ROS dependency.

Because this runs on WSL, it reaches robot_skills on the Pi via CycloneDDS + a shared
ROS_DOMAIN_ID (see the dev-env setup).
"""
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from robot_interfaces.action import RunSkill


class AiNode(Node):
    def __init__(self):
        super().__init__('ai_node')
        self._client = ActionClient(self, RunSkill, 'run_skill')
        self.timer = self.create_timer(5.0, self.tick)
        self.get_logger().info('robot_ai up; will send RunSkill goals to robot_skills (Pi)')

    def decide(self) -> str:
        # TODO: replace with a real LLM call (Ollama qwen2 / Anthropic Claude).
        return 'demo'

    def tick(self):
        if not self._client.server_is_ready():
            self._client.wait_for_server(timeout_sec=0.0)
            self.get_logger().info('waiting for robot_skills action server...')
            return
        skill = self.decide()
        goal = RunSkill.Goal()
        goal.skill = skill
        self.get_logger().info(f'AI decided skill: {skill}')
        self._client.send_goal_async(goal)


def main(args=None):
    rclpy.init(args=args)
    node = AiNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
