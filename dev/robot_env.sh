#!/usr/bin/env bash
# robot_ws development environment (WSL side).
# Sourced from ~/.bashrc. Safe to source before CycloneDDS is installed: it only switches
# RMW to Cyclone if the package is actually present, so ros2 keeps working either way.

# --- ROS 2 ---
source /opt/ros/humble/setup.bash
[ -f "$HOME/robot_ws/install/setup.bash" ] && source "$HOME/robot_ws/install/setup.bash"

# --- Shared DDS domain (MUST match the Pi) ---
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0

# --- Use CycloneDDS only if installed (prevents "failed to load rmw" before apt install) ---
if [ -d /opt/ros/humble/share/rmw_cyclonedds_cpp ]; then
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  export CYCLONEDDS_URI="file://$HOME/robot_ws/dev/cyclonedds.xml"
fi

# Convenience: quick check that the Pi graph is visible.
alias ros-pi-check='ros2 node list && echo "--- topics ---" && ros2 topic list'
