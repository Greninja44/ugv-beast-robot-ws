# Topics

Types marked **[live]** were confirmed via `ros2 topic list -t` during the `bringup_imu_ekf` capture.
Vision/teleop topics marked _(static)_ appear only when those nodes run.

## Core driving stack (live-confirmed)

| Topic | Type | Publisher(s) | Subscriber(s) | Notes |
|-------|------|--------------|---------------|-------|
| `/cmd_vel` | `geometry_msgs/msg/Twist` **[live]** | teleop, `behavior_ctrl`, Nav2, **your code** | `ugv_driver` | Primary drive input → ESP32. |
| `/imu/data_raw` | `sensor_msgs/msg/Imu` **[live]** | `ugv_bringup` | `imu_filter_madgwick`, `complementary_filter` | Raw accel+gyro from ESP32. |
| `/imu/mag` | `sensor_msgs/msg/MagneticField` **[live]** | `ugv_bringup` | imu filters | Magnetometer. |
| `/imu/data` | `sensor_msgs/msg/Imu` **[live]** | `imu_filter_madgwick` | `base_node_ekf`, `ekf_node` | Orientation-filtered IMU. |
| `/odom/odom_raw` | `std_msgs/msg/Float32MultiArray` **[live]** | `ugv_bringup` | `base_node` / `base_node_ekf` | Raw wheel odometry `[odl,odr,...]`. |
| `/odom` | `nav_msgs/msg/Odometry` **[live]** | `base_node_ekf` (or `ekf_node`) | Nav2, `behavior_ctrl`, **your code** | Fused odom; frame `odom`→`base_footprint`. |
| `/odom_rf2o` | `nav_msgs/msg/Odometry` **[live]** | `rf2o_laser_odometry` | `ekf_node` | Laser scan-matching odometry. |
| `/scan` | `sensor_msgs/msg/LaserScan` **[live]** | `ldlidar` (LD06) | `rf2o`, SLAM, Nav2 | Frame `base_lidar_link`. ✅ 10 Hz verified (see LIDAR.md). |
| `/voltage` | `std_msgs/msg/Float32` **[live]** | `ugv_bringup` | `ugv_driver` | Battery V (live sample **11.94**). |
| `/ugv/joint_states` | `sensor_msgs/msg/JointState` **[live]** | `ugv/joint_state_publisher` | `robot_state_publisher`, `ugv_driver` | Wheel/gimbal joint states. |
| `/ugv/led_ctrl` | `std_msgs/msg/Float32MultiArray` **[live]** | (web/app/your code) | `ugv_driver` | LED brightness/color → ESP32. |
| `/ugv/robot_description` | `std_msgs/msg/String` **[live]** | `robot_state_publisher` | RViz, tools | URDF string. |
| `/tf` | `tf2_msgs/msg/TFMessage` **[live]** | base_node, rsp, jsp | all | Dynamic transforms. |
| `/tf_static` | `tf2_msgs/msg/TFMessage` **[live]** | rsp (static joints) | all | Static transforms. |

## Vision / interaction _(static-derived — present when ugv_vision / teleop run)_

| Topic | Type | Publisher | Subscriber |
|-------|------|-----------|------------|
| `/image_raw` | `sensor_msgs/msg/Image` | `usb_cam` | all vision nodes, `image_proc` |
| `/image_rect` | `sensor_msgs/msg/Image` | `image_proc::RectifyNode` | apriltag |
| `/color_track/result` | `sensor_msgs/msg/Image` | `color_track` | viz |
| `/gesture_ctrl/result` | `sensor_msgs/msg/Image` | `gesture_ctrl` | viz |
| `/apriltag_ctrl/result` | `sensor_msgs/msg/Image` | `apriltag_ctrl` | viz |
| `/apriltag_track/result` | `sensor_msgs/msg/Image` | `apriltag_track_0` | viz |
| `/apriltag/track` | `std_msgs/msg/Int8` | (control) | `apriltag_track_1` |
| `joy` | `sensor_msgs/msg/Joy` | `joy_node` | `joy_ctrl` |
| `JoyState` | `std_msgs/msg/Bool` | `joy_ctrl` | (arbitration) |
| `/goal_pose` | `geometry_msgs/msg/PoseStamped` | `behavior_ctrl` | Nav2 |
| `/robot_pose` | `geometry_msgs/msg/PoseStamped` | `robot_pose_publisher` | `behavior_ctrl` |

## Notes for integrators
- To **drive**: publish `Twist` on `/cmd_vel`. To **navigate**: use Nav2 goals / `/goal_pose` in
  `map` frame. To **read pose**: prefer TF (`map`→`base_footprint`) or `/odom`.
- Topic names under `/ugv/...` are namespaced; base topics (`/cmd_vel`, `/odom`, `/scan`) are global.
