# Hardware

## Compute
| Item | Value |
|------|-------|
| SBC | Raspberry Pi 5 (`raspberrypi`) |
| OS | Debian 12 (bookworm), aarch64 |
| ROS | Humble, **inside Docker** (`dudulrx0601/ugv_rpi_ros_humble`) |
| Sub-controller | **ESP32** ("lower computer") over UART |
| Battery (live) | **3S LiPo, 11.94 V** measured on `/voltage` |

## Two-tier control architecture
The Pi is the "upper computer"; an **ESP32** is the "lower computer" handling real-time motor/servo/
sensor I/O. They talk **JSON over UART**. Two mutually-exclusive Pi-side programs can own that UART:
- **ROS:** `ugv_bringup` (reads) + `ugv_driver` (writes).
- **Non-ROS:** `ugv_rpi/app.py` + `base_ctrl.py` (Flask web control).

## Serial / bus device map (host `/dev`)
| Device | Symlink | Baud | Used by | Purpose |
|--------|---------|------|---------|---------|
| `/dev/ttyAMA0` | — | 115200 | `ugv_bringup`/`ugv_driver` | **ESP32 sub-controller** (motors, IMU, LED). Vendor code **hardcodes `/dev/ttyAMA0`** (verified: clean 20 Hz telemetry here; `/dev/serial0`→ttyAMA10 returns no data). |
| `/dev/ttyACM0` | — | 230400 | `ldlidar` | **LD06 LiDAR** (see [LIDAR.md](LIDAR.md)). |
| `/dev/ttyAMA10` | `/dev/serial0` | — | (unused) | Pi-5 primary UART alias; **no ESP32 here** (returns no data). |
| `/dev/video19…37` | — | — | `usb_cam` / libcamera | Cameras (see [CAMERA.md](CAMERA.md)). |
| `/dev/i2c-11`, `/dev/i2c-12` | — | — | OLED / sensors | OSD display (`add_osd`), INA219-style monitoring. |
| `/dev/spidev10.0` | — | — | LED / peripherals | SPI bus. |
| `/dev/gpiochip0…4` | — | — | GPIO | General I/O. |

## ESP32 UART protocol (JSON, live-observed)
Telemetry line pushed by the ESP32 (captured live):
```json
{"T":1001,"L":0,"R":0,"ax":-1,"ay":-1,"az":-11564,"gx":-32754,"gy":8704,"gz":16379,
 "mx":0,"my":20416,"mz":16380,"odl":0,"odr":0,"v":1194}
```
| Key | Meaning |
|-----|---------|
| `T` | message type id (1001 = base feedback) |
| `L`,`R` | left/right track speed feedback |
| `ax,ay,az` | accelerometer (raw) → `/imu/data_raw` |
| `gx,gy,gz` | gyroscope (raw) → `/imu/data_raw` |
| `mx,my,mz` | magnetometer (raw) → `/imu/mag` |
| `odl,odr` | left/right wheel odometry counts → `/odom/odom_raw` |
| `v` | battery voltage (centivolts; `1194` ≈ 11.94 V) → `/voltage` |

Command frames are JSON with a `T` type field. Type codes (from `ugv_rpi/config.yaml`):
| Code | Command |
|------|---------|
| `1` | `cmd_movition_ctrl` — velocity/motion |
| `11` | `cmd_pwm_ctrl` — direct PWM |
| `133` | `cmd_gimbal_ctrl` — pan/tilt angle |
| `141` | `cmd_gimbal_base_ctrl` |
| `137` | `cmd_gimbal_steady` — stabilization |
| `144` | `cmd_arm_ctrl_ui` |
| `210` | `cmd_servo_torque` |
| `501`/`502` | `cmd_set_servo_id` / `cmd_set_servo_mid` |

> In the ROS stack you never craft these directly — publish `/cmd_vel` and let `ugv_driver` encode
> them. `ugv_driver` sends **`{"T":"13","X":<linear m/s>,"Z":<angular rad/s>}`** (ROS-twist mode);
> the web app's `base_ctrl.py` uses **`{"T":1,"L":<left>,"R":<right>}`** (direct differential).

## ⚠ Vendor bug: dual serial open (frame corruption)
`ugv_bringup.py` (reader) **and** `ugv_driver.py` (writer, line 13 `ser = serial.Serial('/dev/ttyAMA0', 115200)`)
each open `/dev/ttyAMA0` independently. Two opens on one UART steal bytes from each other, producing
partial JSON and the crash `KeyError: 'T'` in `ugv_bringup.feedback_loop`. With only one reader the
stream is clean (verified 121/121 good frames). **Do not add a third reader** (e.g. your own node) —
consume `/imu/*`, `/odom*`, `/voltage` topics instead of the serial.

## Hardware status (live-tested 2026-07-04)
| Component | Result |
|-----------|--------|
| Left/Right motors | ✅ spin symmetrically (`L=R≈0.15` m/s under `X=0.10`) |
| Left/Right encoders | ✅ `odl`/`odr` count under motion |
| IMU accel + gyro | ✅ responding (`az≈gravity`) |
| Magnetometer | ⚠️ reads `0,0,0` (intermittent — check I²C/init) |
| Battery | ✅ 11.94 V |
| LD06 LiDAR | ✅ 10 Hz `/scan` |
| OAK-D stereo | ✅ detected, ⚠️ USB2 link (480 Mbps) |

## Sensors & actuators
- **IMU** (accel+gyro) + **magnetometer**, on the ESP32 → filtered by `imu_filter_madgwick` /
  `imu_complementary_filter` → `/imu/data`.
- **Wheel/track encoders** → `/odom/odom_raw` → fused in `base_node_ekf` (+`robot_localization`).
- **LiDAR** LDRobot LD06 → `/scan`.
- **Camera:** **OAK-D stereo** (`3d_camera_link`, depthai). The gimbal `pt_camera` and plain `usb_cam`
  are **not present** (gimbal removed). See [CAMERA.md](CAMERA.md).
- **Pan-tilt gimbal:** **removed** (robotic arm planned — see [ARM.md](ARM.md)).
- **LED:** addressable, via `/ugv/led_ctrl`.
- **Audio:** speaker (`audio_ctrl.py`, `sounds/`), low-battery `low_battery.wav`.

## Config snapshot (`ugv_rpi/config.yaml → base_config`)
`robot_name: UGV Beast` · `main_type: 3` · `module_type: 0` · `use_lidar: false` · `sbc_version: 0.93`.
> `module_type: 0` / `use_lidar: false` reflect the **base web-app config**, not the ROS URDF. The
> URDF still defines gimbal (`pt_*`) frames, but the **gimbal hardware was removed** — so here the
> config's "no module" happens to match reality. The **LD06 lidar is present and working** despite
> `use_lidar: false`. Treat live hardware (this doc's status table) as authoritative.

## Safety
- **Motion:** publishing `/cmd_vel` moves the tracks. Keep the robot wheels-up or in clear space when
  testing. Analysis in this repo issued **no** `/cmd_vel`.
- **Power:** watch `/voltage`; `ugv_driver` raises a low-battery alert. 3S cutoff ≈ 9.6 V.
- **Serial contention:** never run `app.py` and the ROS driver simultaneously.
