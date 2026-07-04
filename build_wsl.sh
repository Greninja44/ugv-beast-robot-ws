#!/usr/bin/env bash
# Build the WSL-side packages (run this on WSL Ubuntu — the dev/compute box).
set -euo pipefail
cd "$(dirname "$0")"
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select \
  robot_interfaces \
  robot_ai \
  robot_mcp
echo "Done. Source it:  source install/setup.bash"
