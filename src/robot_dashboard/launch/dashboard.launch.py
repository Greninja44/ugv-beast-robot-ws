"""Launch the dashboard backend. Run where ROS runs (Pi container in prod)."""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='robot_dashboard',
            executable='dashboard',
            name='dashboard',
            output='screen',
        ),
    ])
