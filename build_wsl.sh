#!/usr/bin/env bash
# Build the WSL-side packages (run this on WSL Ubuntu — the dev/compute box).
set -eo pipefail
cd "$(dirname "$0")"
set +u  # ROS's setup.bash references unset vars; incompatible with -u
source /opt/ros/humble/setup.bash
set -u
export ROBOT_WS_SIDE=wsl
colcon build --symlink-install --packages-select \
  robot_interfaces \
  robot_ai \
  robot_mcp \
  robot_perception \
  robot_bringup
echo "Done. Source it:  source install/setup.bash"
echo "Note: robot_perception is built here for detector_node (YOLO, needs this"
echo "machine's GPU) only — its perception_node (LiDAR/camera) still runs on the Pi."
echo "robot_bringup is built here too, for: ros2 launch robot_bringup robot_wsl.launch.py"
