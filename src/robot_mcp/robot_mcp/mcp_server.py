#!/usr/bin/env python3
"""robot_mcp — expose the ROS graph as MCP tools (runs on WSL).

Skeleton bridge: a ROS node that also runs an MCP server, exposing tools like
`drive`, `navigate_to`, `run_skill`, `get_state` that map onto ROS topics/actions.
An MCP client (e.g. Claude) can then call these tools to operate the robot.

This scaffold defines the tool surface and a ROS publisher for /cmd_vel; wire the
actual MCP transport (stdio/websocket) using the `mcp` pip package. Kept import-light so
it builds without the mcp package installed.
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


# Declarative tool surface this server intends to expose over MCP.
TOOLS = {
    'drive':       'Publish a Twist on /cmd_vel (linear, angular).',
    'run_skill':   'Send a RunSkill goal to robot_skills.',
    'navigate_to': 'Send a NavigateTo goal to robot_navigation.',
    'get_state':   'Return latest /odom, /voltage and percepts.',
}


class McpServer(Node):
    def __init__(self):
        super().__init__('mcp_server')
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.get_logger().info(f'robot_mcp up; tool surface: {list(TOOLS)}')
        self.get_logger().info('TODO: attach MCP transport (mcp pip pkg) and bind tools -> ROS.')

    def tool_drive(self, linear=0.0, angular=0.0):
        t = Twist()
        t.linear.x = float(linear)
        t.angular.z = float(angular)
        self.cmd_pub.publish(t)
        return {'ok': True, 'linear': linear, 'angular': angular}


def main(args=None):
    rclpy.init(args=args)
    node = McpServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
