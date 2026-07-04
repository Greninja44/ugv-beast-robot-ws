# System Architecture — UGV Beast

## 1. Layered overview

The robot has **three stacked control layers**. The bottom two are vendor; the top layer is where
**your** `~/robot_ws` code lives.

```
┌──────────────────────────────────────────────────────────────────────┐
│  YOUR CODE  (~/robot_ws — hybrid: Pi + WSL)                            │
│  robot_ai · robot_mcp · robot_perception · robot_navigation ·         │
│  robot_manipulation · robot_skills · robot_bringup · robot_interfaces  │
│  → interfaces ONLY via topics / services / actions / TF               │
└───────────────▲────────────────────────────────────────────▲─────────┘
                │ cmd_vel, goal_pose, behavior action,        │ /image_raw,
                │ Nav2 goals                                  │ /scan, /odom, /tf
┌───────────────┴────────────────────────────────────────────┴─────────┐
│  VENDOR ROS 2 STACK  (Docker: dudulrx0601/ugv_rpi_ros_humble)         │
│  ugv_bringup ─ ugv_driver ─ ugv_base_node ─ ugv_vision ─ ugv_nav ─    │
│  ugv_slam ─ ugv_tools ─ ugv_chat_ai ─ ugv_web_app  + ugv_else deps    │
└───────────────▲───────────────────────────────────────────────────────┘
                │ JSON over UART  /dev/ttyAMA0 @115200
┌───────────────┴───────────────────────────────────────────────────────┐
│  ESP32 SUB-CONTROLLER ("lower computer")                              │
│  motors · IMU · magnetometer · wheel encoders · gimbal servos · LED   │
└───────────────────────────────────────────────────────────────────────┘

   Parallel NON-ROS layer (mutually exclusive on the serial port):
   ~/ugv_rpi/app.py  (Flask web UI + base_ctrl.py)  ── same UART ──┘
```

## 2. Hardware architecture

```mermaid
flowchart TB
  subgraph Host["Raspberry Pi 5 · Debian 12 · aarch64"]
    subgraph Docker["Docker container (--network host --privileged)"]
      ROS["ROS 2 Humble stack<br/>ugv_bringup / ugv_driver / base_node ..."]
    end
    APP["ugv_rpi/app.py<br/>(Flask + base_ctrl.py, non-ROS)"]
    JUP["Jupyter (autostart)"]
  end
  ESP["ESP32 sub-controller"]
  MOT["Track motors L/R"]
  IMU["IMU + magnetometer"]
  ENC["Wheel encoders"]
  GIM["Pan-tilt gimbal servos"]
  LED["WS2812 LED"]
  LIDAR["LDRobot LD06 LiDAR"]
  CAMU["USB / CSI camera"]
  CAM3["Depth camera (3d_camera)"]
  BATT["3S LiPo (~11.9V)"]

  ROS <-->|"UART /dev/ttyAMA0 @115200 JSON"| ESP
  APP <-.->|"same UART (exclusive)"| ESP
  ESP --> MOT & IMU & ENC & GIM & LED
  BATT --> ESP
  ROS <-->|"/dev/ttyACM0 @230400"| LIDAR
  ROS <-->|"/dev/video* (usb_cam)"| CAMU
  ROS <-->|"USB (depthai)"| CAM3
```

## 3. Node graph (core driving stack — live-confirmed)

```mermaid
flowchart LR
  ESP["ESP32 (serial)"]
  bringup["ugv_bringup"]
  driver["ugv_driver"]
  imufilt["imu_filter_madgwick"]
  base["base_node_ekf"]
  ekf["robot_localization/ekf_node"]
  rsp["ugv/robot_state_publisher"]
  jsp["ugv/joint_state_publisher"]
  rf2o["rf2o_laser_odometry"]
  ldlidar["ldlidar LD06"]

  ESP -->|reads| bringup
  bringup -->|/imu/data_raw, /imu/mag| imufilt
  bringup -->|/odom/odom_raw| base
  bringup -->|/voltage| driver
  imufilt -->|/imu/data| base
  base -->|/odom + TF odom→base_footprint| ekf
  driver -->|cmd → serial| ESP
  jsp -->|/ugv/joint_states| rsp
  rsp -->|/ugv/robot_description + TF| base
  ldlidar -->|/scan| rf2o
  rf2o -->|/odom_rf2o| ekf
  CMDVEL["/cmd_vel (teleop / nav / your code)"] --> driver
```

## 4. Behavior / vision / AI graph _(static-derived)_

```mermaid
flowchart LR
  cam["usb_cam"] -->|/image_raw| rect["image_proc RectifyNode"]
  cam -->|/image_raw| ct["color_track"]
  cam -->|/image_raw| gc["gesture_ctrl"]
  cam -->|/image_raw| at["apriltag_ctrl / apriltag_track_*"]
  ct & gc & at -->|behavior action| bctrl["behavior_ctrl<br/>(ActionServer)"]
  chat["ugv_chat_ai (Flask + Ollama qwen2)"] -->|behavior action| bctrl
  bctrl -->|/cmd_vel| driver["ugv_driver"]
  bctrl -->|/goal_pose| nav["Nav2"]
```

## 5. Package dependency graph (ugv_main → key deps)

```mermaid
flowchart TD
  base_node --> geometry_msgs & nav_msgs & tf2_ros & rclcpp
  bringup["ugv_bringup"] --> rclcpp & std_msgs
  interface["ugv_interface"] --> rosidl & action_msgs & sensor_msgs & tf2_ros
  vision["ugv_vision"] --> interface & usb_cam & image_proc & apriltag_ros
  tools["ugv_tools"] --> interface
  chat["ugv_chat_ai"] --> interface
  nav["ugv_nav"] --> nav2_bringup & teb_local_planner & emcl2 & rf2o
  slam["ugv_slam"] --> cartographer & slam_gmapping & rtabmap
  description["ugv_description"] --> robot_state_publisher & rviz2
  web["ugv_web_app"] --> vizanti_server
```

## 6. Extension points — where YOUR code attaches

Build against these **stable seams**; never edit vendor packages.

| Your package | Consumes (sub) | Produces (pub / calls) | Vendor seam |
|--------------|----------------|------------------------|-------------|
| `robot_perception` | `/image_raw`, `/scan`, `/odom`, TF | your detection/percept topics | camera + lidar drivers |
| `robot_navigation` | `/odom`, `/scan`, `/tf`, costmaps | `/goal_pose`, Nav2 action goals | `ugv_nav` (Nav2) |
| `robot_manipulation` | `/tf` (`pt_*` frames) | gimbal commands (via ESP32 cmd or a bridge) | pan-tilt gimbal |
| `robot_skills` | `/odom`, percepts | `/cmd_vel`, **`behavior` action** | `ugv_driver`, `behavior_ctrl` |
| `robot_ai` | percepts, state | intents → `robot_skills` | (top of stack) |
| `robot_mcp` | any topic/service/action | tool calls into the graph | whole graph |
| `robot_bringup` | — | launches your nodes | composes, references vendor launch |
| `robot_interfaces` | — | your msg/srv/action | shared types |

**Primary control seams**
- **Drive:** publish `geometry_msgs/Twist` on **`/cmd_vel`** → `ugv_driver` → ESP32.
- **Navigate:** send Nav2 goals / publish **`/goal_pose`** (PoseStamped, `map` frame).
- **Behaviors:** call the **`behavior`** action (`ugv_interface/action/Behavior`, `string command`).
- **Perceive:** subscribe **`/image_raw`**, **`/scan`**, **`/odom`**, and read **TF**.
- **Localize:** consume the **`map → odom → base_footprint`** TF chain.

**Hard caveats**
- Do not run your own base-serial driver — the vendor `ugv_bringup`/`ugv_driver` (or `app.py`) owns
  `/dev/ttyAMA0`. Drive through `/cmd_vel`.
- Match DDS settings across machines (see [DOCKER.md](DOCKER.md) and the dev-env setup): CycloneDDS +
  shared `ROS_DOMAIN_ID`.
