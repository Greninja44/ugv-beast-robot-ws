#!/usr/bin/env bash
# Bring up the whole robot stack on the Pi, cleanly, in one command.
# Run INSIDE the ugv_rpi_ros_humble container:
#   docker exec -d ugv_rpi_ros_humble bash /home/ws/robot_ws/dev/start_pi_stack.sh
#
# Starts: OAK-D camera, the dashboard (which auto-starts the base bringup via its
# launch_manager), and the robot_ws core nodes (mode arbiter, skills, nav bridge,
# perception). SLAM / Nav2 / autonomous exploration are started from the dashboard
# ("Explore this room" button), not here.
#
# The YOLO detector is deliberately NOT started here: on the Pi's CPU it competes
# with SLAM/Nav2 for cores (load spiked to 12+ when co-scheduled). Run it on the
# GPU box instead (see dev/start_gpu_detector.sh), or start it here by hand at a low
# rate if you really want on-Pi detection.
set -u

ROS_SETUP=/opt/ros/humble/setup.bash
VENDOR_SETUP=/home/ws/ugv_ws/install/setup.bash
WS_SETUP=/home/ws/robot_ws/install/setup.bash

# This script runs via `docker exec -d ... bash script.sh` (see header) — a
# non-interactive, non-login shell that never sources /root/.bashrc, so none of the
# DDS/model env vars normally set there reach anything started below. Without this,
# the whole stack silently runs on default RMW (FastRTPS) + domain 0, invisible to
# WSL, no matter what dev/setup_pi_container.sh or robot_env.sh do on the other end.
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0
export UGV_MODEL=ugv_beast
export LDLIDAR_MODEL=ld19

log() { echo "[start_pi_stack] $*"; }

# --- 0. clean any previous instances so we never stack duplicates -------------
# IMPORTANT: this must kill the actual vendor node executables, not just the
# `ros2 launch` wrapper processes. SIGKILL-ing only the wrapper (e.g. matching
# "bringup_lidar" hits just the `ros2 launch ugv_bringup bringup_lidar.launch.py`
# process) doesn't cascade to its children — ros2 launch normally shuts children
# down on SIGINT, but SIGKILL gives it no chance to. The children (base_node,
# ugv_driver, rf2o_laser_odometry, joint_state_publisher, robot_state_publisher,
# ldlidar_node, oak's component_container) then survive as orphans still holding
# the serial port / lidar / camera, and the next start piles a second full set on
# top — this actually happened (three stacked generations of the vendor bringup
# fighting over the same ESP32 serial + camera, only found by manually inspecting
# `ps aux`). List every child executable explicitly so all generations actually die.
log "stopping any previous stack..."
for pat in oak_d_lite component_container "robot_dashboard/lib" mode_server skill_server \
           nav_bridge perception_node bringup_lidar cartographer nav.launch explore_lite \
           ldlidar_node base_node ugv_driver rf2o_laser_odometry joint_state_publisher \
           robot_state_publisher; do
  pkill -9 -f "$pat" 2>/dev/null
done
sleep 3

# --- 1. lidar serial: the LD06 re-enumerates as ttyACM1 after some replugs/reboots,
#        but the vendor launch hardcodes ttyACM0. Point ttyACM0 at whatever's there.
if [ ! -e /dev/ttyACM0 ] && [ -e /dev/ttyACM1 ]; then
  log "ttyACM0 missing, symlinking to ttyACM1"
  ln -sf /dev/ttyACM1 /dev/ttyACM0
fi

start() {  # name, "commands..."
  local name="$1"; shift
  log "starting $name"
  bash -lc "$*" > "/tmp/${name}.log" 2>&1 &
}

# --- 2. camera ----------------------------------------------------------------
start oak "source $ROS_SETUP && source $VENDOR_SETUP && \
  ros2 launch ugv_vision oak_d_lite.launch.py"

# --- 3. dashboard (auto-starts base bringup: driver + lidar + sensors) --------
start dashboard "source $ROS_SETUP && source $WS_SETUP && \
  ros2 run robot_dashboard dashboard"
sleep 8   # let the dashboard bind + kick off the base bringup before the rest

# --- 4. robot_ws core nodes ---------------------------------------------------
for node in mode_server skill_server; do
  start "$node" "source $ROS_SETUP && source $WS_SETUP && ros2 run robot_skills $node"
done
start nav_bridge "source $ROS_SETUP && source $WS_SETUP && ros2 run robot_navigation nav_bridge"
start perception_node "source $ROS_SETUP && source $WS_SETUP && ros2 run robot_perception perception_node"

sleep 3
log "done. Dashboard: http://<pi-ip>:8080  (logs in /tmp/*.log)"
