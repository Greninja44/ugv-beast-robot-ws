#!/usr/bin/env bash
# Build the Pi-side packages (run this ON the Pi / in the ROS container).
set -euo pipefail
cd "$(dirname "$0")"
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select \
  robot_interfaces \
  robot_perception \
  robot_navigation \
  robot_manipulation \
  robot_skills \
  robot_bringup
echo "Done. Source it:  source install/setup.bash"
