"""Bring up YOUR Pi-side nodes (mode arbiter, perception, skills, navigation).

Run this on the Raspberry Pi alongside the (separately launched) Waveshare stack.
Waveshare's drivers own the hardware; these nodes consume Waveshare topics/TF only.

mode_server must come up alongside skill_server/nav_bridge: both refuse to command
motion until told they hold authority (see robot_skills.mode_server), so without it
every skill/nav goal is rejected forever, not just left un-arbitrated.

robot_manipulation (gimbal) is intentionally not launched here — no manipulation
hardware in scope right now (gimbal removed, no arm fitted). Add it back once that
changes.
"""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(package='robot_skills', executable='mode_server',
             name='mode_server', output='screen'),
        Node(package='robot_perception', executable='perception_node',
             name='perception_node', output='screen'),
        Node(package='robot_skills', executable='skill_server',
             name='skill_server', output='screen'),
        Node(package='robot_navigation', executable='nav_bridge',
             name='nav_bridge', output='screen'),
    ])
