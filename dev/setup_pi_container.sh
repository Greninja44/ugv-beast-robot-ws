#!/usr/bin/env bash
# Configure the Pi's vendor ROS container to use CycloneDDS + shared ROS_DOMAIN_ID.
# Run this FROM WSL (it SSHes into the Pi). Safe & reversible; does NOT touch /home/ws/ugv_ws.
#
# NOTE: container package installs do not persist if the container is recreated with
# `docker run`. If you rebuild the container, re-run this script.
set -euo pipefail

PI=ugv                       # ssh alias
C=ugv_rpi_ros_humble         # container name
DOMAIN=42

echo ">> starting container $C on $PI"
ssh "$PI" "docker start $C >/dev/null"

echo ">> installing rmw_cyclonedds in container (apt)"
ssh "$PI" "docker exec -u root $C bash -lc 'apt-get update -qq && apt-get install -y -qq ros-humble-rmw-cyclonedds-cpp'"

echo ">> appending DDS env to container /root/.bashrc (idempotent)"
ssh "$PI" "docker exec -u root $C bash -lc '
  grep -q RMW_IMPLEMENTATION /root/.bashrc || cat >> /root/.bashrc <<EOF

# --- robot_ws DDS config (WSL<->Pi) ---
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=$DOMAIN
export ROS_LOCALHOST_ONLY=0
export UGV_MODEL=ugv_beast
export LDLIDAR_MODEL=ld06
EOF'"

echo ">> done. Bring the vendor stack up with, e.g.:"
echo "   ssh $PI"
echo "   docker exec -it $C bash"
echo "   source /opt/ros/humble/setup.bash && source /home/ws/ugv_ws/install/setup.bash"
echo "   ros2 launch ugv_bringup bringup_lidar.launch.py"
