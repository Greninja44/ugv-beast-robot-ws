"""Bring up YOUR Pi-side nodes (perception, manipulation, skills, navigation).

Run this on the Raspberry Pi alongside the (separately launched) vendor stack.
The vendor drivers own the hardware; these nodes consume vendor topics/TF only.
"""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(package='robot_perception', executable='perception_node',
             name='perception_node', output='screen'),
        Node(package='robot_manipulation', executable='gimbal_node',
             name='gimbal_node', output='screen'),
        Node(package='robot_skills', executable='skill_server',
             name='skill_server', output='screen'),
        Node(package='robot_navigation', executable='nav_bridge',
             name='nav_bridge', output='screen'),
    ])
