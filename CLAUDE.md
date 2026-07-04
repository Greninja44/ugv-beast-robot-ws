# CLAUDE.md — project map for Claude Code

## What this is
Two ROS 2 Humble workspaces for a **Waveshare UGV Beast** (tracked robot, 2-DOF pan-tilt gimbal) on
a **Raspberry Pi 5** (Debian 12, aarch64). Development happens on **WSL2 Ubuntu** (this machine);
GUI tools (RViz2/rqt/Foxglove/MoveIt) run here, the Pi runs drivers only.

- **Vendor (read-only):** `/home/ws/ugv_ws` on the Pi (SSH alias `ugv` → `ws@10.193.235.119`), runs
  in Docker image `dudulrx0601/ugv_rpi_ros_humble` (`--network host --privileged`). A read-only
  source mirror is at WSL `~/vendor_ref/` for reference.
- **Yours:** `~/robot_ws` (this repo). Interfaces with the vendor stack via topics/services/actions/TF
  ONLY.

## Hard rules
1. **Never modify, rename, delete, or refactor anything under `/home/ws/ugv_ws`** — it is vendor code.
2. Do not open `/dev/serial0` directly; drive the robot via `/cmd_vel` or the vendor `behavior` action.
3. Only one owner of the ESP32 serial at a time: vendor `ugv_bringup`/`ugv_driver` **or** the non-ROS
   `~/ugv_rpi/app.py`. They conflict.
4. Any change to Pi runtime state (start/stop containers, crontab) must be explicit and reversible.

## Key vendor seams (build against these)
- Drive: publish `geometry_msgs/Twist` on **`/cmd_vel`**.
- Sense: subscribe **`/scan`** (LD06 lidar), **`/odom`**, **`/voltage`**, **`/imu/data`**, read **TF**; camera = **OAK-D stereo** via depthai_ros (the gimbal `pt_camera`/usb_cam was removed).
- Navigate: Nav2 (`navigate_to_pose`) / publish **`/goal_pose`** in `map`.
- Behaviours: vendor **`behavior`** action (`ugv_interface/action/Behavior`, `string command`).
- TF chain: `map → odom → base_footprint → base_link → {base_imu_link, base_lidar_link, 3d_camera_link, pt_base_link→pt_link1→pt_link2→pt_camera_link, *_wheel_link}`.

## Vendor launch needs these env vars
`export UGV_MODEL=ugv_beast` and `export LDLIDAR_MODEL=ld06`, then
`source /opt/ros/humble/setup.bash && source /home/ws/ugv_ws/install/setup.bash`.
Bring-up: `ros2 launch ugv_bringup bringup_lidar.launch.py` (or `bringup_imu_ekf.launch.py`).

## This workspace (`~/robot_ws`)
- Layout, package split (Pi vs WSL), build/run: see [README.md](README.md).
- Vendor system docs: [docs/INDEX.md](docs/INDEX.md).
- Custom interfaces live in `robot_interfaces` (built on both machines).

## Networking
WSL2 **mirrored** mode + **CycloneDDS** (`RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`) + shared
`ROS_DOMAIN_ID` (42) on both sides. Verify: `ros2 topic list` from WSL shows the Pi topics.

## Build
- WSL: `./build_wsl.sh` (interfaces + robot_ai + robot_mcp).
- Pi: `./build_pi.sh` (interfaces + perception/nav/manip/skills/bringup).
