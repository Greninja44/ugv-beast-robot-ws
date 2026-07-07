#!/usr/bin/env python3
"""robot_navigation — typed NavigateTo action server that fronts Nav2.

Exposes robot_interfaces/action/NavigateTo, forwarding accepted goals to Nav2's standard
navigate_to_pose action (nav2_msgs/action/NavigateToPose) and relaying feedback/cancel.
No Waveshare code is imported; integration is purely via the standard Nav2 action.

Gated by /robot/mode: goals are only forwarded to Nav2 while an autonomous mode
(explore/track/ai) holds motion authority. AUTONOMOUS_MODES mirrors
robot_skills.mode_server.AUTONOMOUS_MODES by convention rather than by import —
robot_navigation must not depend on robot_skills, which sits above it in the stack (skills
call navigation, never the reverse). If authority is revoked mid-goal (mode changes away
from an autonomous mode while navigating), the in-flight Nav2 goal is canceled immediately.

Only one NavigateTo goal is accepted at a time — a mobile base only has one place to be.
"""
import threading

import rclpy
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from action_msgs.msg import GoalStatus
from std_msgs.msg import String
from nav2_msgs.action import NavigateToPose
from robot_interfaces.action import NavigateTo

# Mirrors robot_skills.mode_server.AUTONOMOUS_MODES — kept in sync by convention, not
# import (see module docstring).
AUTONOMOUS_MODES = {'explore', 'track', 'ai'}

MODE_QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL)


class NavBridge(Node):
    def __init__(self):
        super().__init__('nav_bridge')
        self._mode = 'idle'
        self._lock = threading.Lock()
        self._active_nav2_goal = None  # ClientGoalHandle of the in-flight Nav2 goal, if any

        self.create_subscription(String, '/robot/mode', self._on_mode, MODE_QOS)
        self._nav2 = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._server = ActionServer(
            self, NavigateTo, 'navigate_to', self.execute,
            goal_callback=self._on_goal_request,
            cancel_callback=self._on_cancel_request)
        self.get_logger().info(
            "robot_navigation up; action 'navigate_to' forwards to Nav2's navigate_to_pose")

    def _on_mode(self, msg: String):
        self._mode = msg.data
        if msg.data not in AUTONOMOUS_MODES:
            with self._lock:
                nav2_goal = self._active_nav2_goal
            if nav2_goal is not None:
                self.get_logger().warn(
                    f"mode changed to '{msg.data}' mid-goal; canceling active Nav2 goal")
                nav2_goal.cancel_goal_async()

    def _on_goal_request(self, goal_request):
        with self._lock:
            busy = self._active_nav2_goal is not None
        if busy:
            self.get_logger().warn('rejecting NavigateTo: a goal is already in progress')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _on_cancel_request(self, goal_handle):
        return CancelResponse.ACCEPT

    async def execute(self, goal_handle):
        target = goal_handle.request.target
        result = NavigateTo.Result()

        if self._mode not in AUTONOMOUS_MODES:
            self.get_logger().warn(
                f"rejecting NavigateTo: requires an autonomous mode {sorted(AUTONOMOUS_MODES)}, "
                f"current mode is '{self._mode}'")
            goal_handle.abort()
            result.success = False
            return result

        if not self._nav2.server_is_ready():
            self.get_logger().error("Nav2 'navigate_to_pose' action server not available")
            goal_handle.abort()
            result.success = False
            return result

        self.get_logger().info(
            f'NavigateTo -> Nav2: frame={target.header.frame_id} '
            f'x={target.pose.position.x:.2f} y={target.pose.position.y:.2f}')

        nav2_goal = NavigateToPose.Goal()
        nav2_goal.pose = target

        def on_feedback(fb_msg):
            fb = NavigateTo.Feedback()
            fb.distance_remaining = fb_msg.feedback.distance_remaining
            goal_handle.publish_feedback(fb)

        nav2_goal_handle = await self._nav2.send_goal_async(nav2_goal, feedback_callback=on_feedback)

        if not nav2_goal_handle.accepted:
            self.get_logger().warn('Nav2 rejected the goal')
            goal_handle.abort()
            result.success = False
            return result

        with self._lock:
            self._active_nav2_goal = nav2_goal_handle

        nav2_result = await nav2_goal_handle.get_result_async()

        with self._lock:
            self._active_nav2_goal = None

        status = nav2_result.status
        if status == GoalStatus.STATUS_SUCCEEDED:
            goal_handle.succeed()
            result.success = True
        elif goal_handle.is_cancel_requested:
            goal_handle.canceled()
            result.success = False
        else:
            goal_handle.abort()
            result.success = False
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
