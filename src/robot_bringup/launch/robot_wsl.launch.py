"""Bring up YOUR WSL-side nodes (AI + MCP + YOLO detection).

Run this on WSL. These reach the Pi graph via CycloneDDS + a shared ROS_DOMAIN_ID
(see the dev-env setup). Heavy compute (LLM, YOLO) stays off the Pi.

detector_node needs its own venv (torch/ultralytics — see detector_node.py's docstring
for why a plain `pip install --user` breaks every other node's cv2/numpy). Since its
console-script shebang points at whatever Python built robot_perception (not this venv),
it's launched here via ExecuteProcess against the venv's interpreter directly, not
launch_ros.actions.Node like the other two — Node has no way to override the
interpreter. Path assumes the venv lives at <workspace root>/.venv-detector, per its
.gitignore entry and creation instructions.
"""
import os

from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node

# realpath, not abspath: with --symlink-install this file is loaded through a chain of
# symlinks (install/ -> build/ -> src/) — abspath would resolve relative to wherever
# ros2 launch found the symlink, not the true source location this math assumes.
# .../robot_ws/src/robot_bringup/launch/robot_wsl.launch.py -> .../robot_ws
_THIS_FILE = os.path.realpath(__file__)
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE))))
DETECTOR_VENV_PYTHON = os.path.join(WORKSPACE_ROOT, '.venv-detector', 'bin', 'python3')


def generate_launch_description():
    return LaunchDescription([
        Node(package='robot_ai', executable='ai_node',
             name='ai_node', output='screen'),
        Node(package='robot_mcp', executable='mcp_server',
             name='mcp_server', output='screen'),
        ExecuteProcess(
            cmd=[DETECTOR_VENV_PYTHON, '-m', 'robot_perception.detector_node'],
            name='detector_node', output='screen'),
    ])
