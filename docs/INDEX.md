# Waveshare UGV Beast — System Documentation

Reverse-engineered documentation of the **vendor** ROS 2 stack running on the Raspberry Pi 5
(`ws@10.193.235.119`), produced by read-only static + live analysis. The vendor workspace
`/home/ws/ugv_ws` is **never modified**.

> **Robot:** Waveshare **UGV Beast** (tracked chassis, 2-DOF pan-tilt gimbal) · **SBC:** Raspberry Pi 5,
> Debian 12 (bookworm), aarch64 · **ROS:** Humble (in Docker) · **Sub-controller:** ESP32 over UART.

## Documents

| Doc | Contents |
|-----|----------|
| [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | Big picture, layers, all Mermaid diagrams, **extension points** for your code |
| [PACKAGE_SUMMARY.md](PACKAGE_SUMMARY.md) | All 31 packages, nodes, executables, responsibilities |
| [TOPICS.md](TOPICS.md) | Every topic, type, publisher/subscriber |
| [SERVICES.md](SERVICES.md) | Services and their definitions |
| [ACTIONS.md](ACTIONS.md) | The `behavior` action and its clients |
| [TF_TREE.md](TF_TREE.md) | Full live TF tree + frame origins |
| [HARDWARE.md](HARDWARE.md) | ESP32 serial protocol, sensors, power, buses, devices |
| [NAVIGATION.md](NAVIGATION.md) | Nav2, SLAM, localization, laser odometry, exploration |
| [ARM.md](ARM.md) | Pan-tilt gimbal (the manipulation surface on this robot) |
| [CAMERA.md](CAMERA.md) | usb_cam, depth camera, gimbal camera, vision pipeline |
| [LIDAR.md](LIDAR.md) | LDRobot LD06 driver, scan, rf2o odometry |
| [DOCKER.md](DOCKER.md) | Container image, run command, mounts, networking |
| [DEV_SETUP.md](DEV_SETUP.md) | WSL↔Pi dev environment: SSH, mirrored net, CycloneDDS, RViz/Foxglove, VS Code |

## How this was gathered
- **Static:** read-only copy of source at WSL `~/vendor_ref/` (code only) + direct SSH reads.
- **Live:** launched `ugv_bringup bringup_imu_ekf.launch.py` in the container, captured
  `ros2 node/topic/service/action list`, `/tf`, `/tf_static`, `/odom`, `/voltage`, `ros2 param dump`,
  then torn down (no motor commands issued). Facts marked _(static-derived)_ were not live-confirmed
  because the producing nodes weren't running in the capture.

## Conventions & caveats
- **Two control stacks share one serial port.** The non-ROS `~/ugv_rpi/app.py` (Flask web UI +
  `base_ctrl.py`) and the ROS `ugv_bringup`/`ugv_driver` both open the ESP32 UART. **Only one may
  run at a time.** During analysis `app.py` was not running (only Jupyter autostarts), so the ROS
  stack had the port.
- Vendor launch files require env vars **`UGV_MODEL=ugv_beast`** and **`LDLIDAR_MODEL=ld06`**
  (this robot has an **LD06**, not an STL27L).
- **Hardware verified 2026-07-04:** motors, encoders, LD06 lidar (10 Hz), IMU accel/gyro, and battery
  (11.94 V) all working; OAK-D stereo detected (on USB2); magnetometer reads zeros (suspect).
- ESP32 is on **`/dev/ttyAMA0`** (hardcoded in vendor code), **not** `/dev/serial0`.
- **Gimbal removed** (arm planned) — the `pt_*` TF frames are stale.
