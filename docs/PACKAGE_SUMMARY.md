# Package Summary — 31 packages

Workspace: `/home/ws/ugv_ws/src` → two groups: **`ugv_main`** (11 Waveshare packages) and
**`ugv_else`** (20 vendored third-party packages).

## ugv_main — Waveshare packages

| Package | Build | Executables / nodes | Responsibility |
|---------|-------|---------------------|----------------|
| **ugv_base_node** | ament_cmake (C++) | `base_node`, `base_node_ekf` | Fuses `/imu/data` + `/odom/odom_raw` → `/odom` (`nav_msgs/Odometry`) and broadcasts `odom→base_footprint` TF. `_ekf` variant pairs with `robot_localization`. Params: `odom_frame`, `base_footprint_frame`, `pub_odom_tf`. |
| **ugv_bringup** | ament_python | `ugv_bringup`, `ugv_driver` | `ugv_bringup` = serial reader: parses ESP32 JSON → `/imu/data_raw`, `/imu/mag`, `/odom/odom_raw`, `/voltage`. `ugv_driver` = serial writer: `/cmd_vel`→motion, `/ugv/led_ctrl`→LED, `/ugv/joint_states`, `/voltage`→low-battery alert. Launches: `bringup_lidar`, `bringup_imu_ekf`, `bringup_imu_origin`. |
| **ugv_description** | ament (URDF) | (launch: `display.launch.py`) | URDFs `ugv_beast.urdf` / `ugv_rover.urdf` / `rasp_rover.urdf` (selected by `UGV_MODEL`); robot_state_publisher + joint_state_publisher; RViz config. |
| **ugv_interface** | ament_cmake (rosidl) | — | Custom interfaces: `action/Behavior.action`, `srv/MapSave.srv`. |
| **ugv_tools** | ament_python | `keyboard_ctrl`, `joy_ctrl`, `behavior_ctrl` | Teleop (keyboard/joystick → `/cmd_vel`) and the **`behavior` ActionServer** that arbitrates motion/goals. |
| **ugv_vision** | ament_python | `color_track`, `kcf_track`, `gesture_ctrl`, `apriltag_ctrl`, `apriltag_track_0/1/2` | OpenCV/AprilTag/MediaPipe perception on `/image_raw`; each is a `behavior` action **client**. Launches: `camera`, `apriltag_track`, `oak_d_lite`. |
| **ugv_nav** | ament_cmake | (Nav2 launch + params) | Nav2 bringup + param sets (AMCL/EMCL/RTAB-Map × DWB/TEB), maps, map_server. |
| **ugv_slam** | ament_cmake | (SLAM launch) | Cartographer / gmapping / rtabmap_rgbd launch + config. |
| **ugv_chat_ai** | ament_python | `app` | Flask web app + `rclpy` **`behavior` action client**; LLM via local **Ollama `qwen2:latest`** (streaming HTTP). |
| **ugv_gazebo** | ament (sim) | (sim launch) | Gazebo simulation of the UGV (bringup, spawn, nav, slam in sim). |
| **ugv_web_app** | ament_python | (launch) | Web UI via **`vizanti_server`** (browser-based RViz-like viz + teleop). |

## ugv_else — vendored third-party

| Package(s) | Purpose |
|------------|---------|
| `ldlidar` | LDRobot LiDAR driver (LD06/LD19/**STL27L**) → `/scan`. |
| `rf2o_laser_odometry` | Laser scan-matching odometry → `/odom_rf2o`. |
| `cartographer` | Google Cartographer 2D/3D SLAM. |
| `gmapping` (`openslam_gmapping`, `slam_gmapping`) | Particle-filter 2D SLAM. |
| `emcl2_ros2` | MCL localization (alternative to AMCL). |
| `teb_local_planner` (+ `teb_msgs`) | Timed-Elastic-Band local planner for Nav2. |
| `costmap_converter` (+ `_msgs`) | Converts costmap to geometric obstacles for TEB. |
| `explore_lite` | Frontier-based autonomous exploration. |
| `apriltag_ros` (`apriltag`, `apriltag_msgs`, `apriltag_ros`) | AprilTag detection (docking, tracking). |
| `robot_pose_publisher` | Publishes robot pose (`/robot_pose`) from TF. |
| `vizanti` (`vizanti`, `vizanti_server`, `vizanti_cpp`, `vizanti_demos`, `vizanti_msgs`) | Web-based visualization/teleop dashboard. |

## Node ↔ package quick map

```
base_node, base_node_ekf     → ugv_base_node
ugv_bringup, ugv_driver      → ugv_bringup
keyboard_ctrl, joy_ctrl,
  behavior_ctrl              → ugv_tools
color_track, kcf_track,
  gesture_ctrl, apriltag_*   → ugv_vision
app (chat)                   → ugv_chat_ai
ldlidar (LD06)             → ldlidar
rf2o_laser_odometry          → rf2o_laser_odometry
robot/joint_state_publisher  → ugv_description (via robot_state_publisher/joint_state_publisher)
imu_filter_madgwick,
  complementary_filter       → (deps: imu_filter_madgwick, imu_complementary_filter)
ekf_node                     → (dep: robot_localization)
```
