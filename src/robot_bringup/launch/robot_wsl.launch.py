"""Bring up YOUR WSL-side nodes (AI + MCP).

Run this on WSL. These reach the Pi graph via CycloneDDS + a shared ROS_DOMAIN_ID
(see the dev-env setup). Heavy compute (LLM) stays off the Pi.
"""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(package='robot_ai', executable='ai_node',
             name='ai_node', output='screen'),
        Node(package='robot_mcp', executable='mcp_server',
             name='mcp_server', output='screen'),
    ])
