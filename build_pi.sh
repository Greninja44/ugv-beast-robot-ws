#!/usr/bin/env bash
# Build the Pi-side packages (run this ON the Pi / in the ROS container).
set -eo pipefail
cd "$(dirname "$0")"
set +u  # ROS's setup.bash references unset vars; incompatible with -u
source /opt/ros/humble/setup.bash
set -u
export ROBOT_WS_SIDE=pi
colcon build --symlink-install --packages-select \
  robot_interfaces \
  robot_perception \
  robot_navigation \
  robot_manipulation \
  robot_skills \
  robot_bringup \
  robot_dashboard
echo "Done. Source it:  source install/setup.bash"
