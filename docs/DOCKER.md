# Docker & Runtime

The vendor ROS 2 stack runs **inside a Docker container** on the Pi. The workspace is **bind-mounted
from the host**, so source is editable on the host and readable over SSH without entering the container.

## Image & containers
- **Image:** `dudulrx0601/ugv_rpi_ros_humble:ugv_rpi_ros_humble`
- **Containers present:** `ugv_rpi_ros_humble` (primary), `beast_ros_gui`, `heuristic_brattain`
  (all normally **Exited**; the stack is started manually).

## Run command (from Pi history — reference, do not re-run blindly)
```bash
docker run -dit \
  --name ugv_rpi_ros_humble \
  --network host \
  --privileged \
  -v ~/ugv_ws:/home/ws/ugv_ws \
  dudulrx0601/ugv_rpi_ros_humble:ugv_rpi_ros_humble \
  bash
```
Key flags:
| Flag | Effect | Implication for you |
|------|--------|---------------------|
| `--network host` | container shares the Pi's network stack | DDS traffic is on the Pi LAN IP directly — good for WSL↔Pi discovery |
| `--privileged` | full device access | serial/video/i2c/gpio reachable inside |
| `-v ~/ugv_ws:/home/ws/ugv_ws` | bind-mount workspace | edit on host, build in container; **treat read-only** |
| (X11 variants in history) | `-e DISPLAY -v /tmp/.X11-unix` | legacy X11 GUI — **being retired** in favor of WSL-native GUIs |

## Entry helper — `~/ugv_ws/ros2_humble.sh`
Starts the container and opens a shell (and `service ssh start` inside):
```bash
docker start ugv_rpi_ros_humble
docker exec -it ugv_rpi_ros_humble /bin/bash -c "service ssh start"
```

## Runtime environment (inside container)
- `ROS_DISTRO=humble`; **no** `RMW_IMPLEMENTATION` set → defaults to **Fast DDS**; `ROS_DOMAIN_ID` unset (0).
- Launches require: `export UGV_MODEL=ugv_beast` and `export LDLIDAR_MODEL=ld06`.
- Sourcing: `source /opt/ros/humble/setup.bash && source /home/ws/ugv_ws/install/setup.bash`.

## Bring the stack up (reference)
```bash
ssh ugv
docker start ugv_rpi_ros_humble
docker exec -it ugv_rpi_ros_humble bash
#   inside:
source /opt/ros/humble/setup.bash
source /home/ws/ugv_ws/install/setup.bash
export UGV_MODEL=ugv_beast LDLIDAR_MODEL=ld06
ros2 launch ugv_bringup bringup_lidar.launch.py     # or bringup_imu_ekf.launch.py
```

## Host autostart (systemd/cron)
- `crontab -l` on the host currently autostarts **only Jupyter** (`start_jupyter.sh`, port 8888).
- `ugv_rpi/autorun.sh` *can* add an `@reboot` entry for `app.py` (web base control) — **not active now**,
  so the ESP32 serial is free for the ROS stack.

## Networking for YOUR GUI tools (WSL → Pi)
Because the container is `--network host`, the ROS graph is on the Pi's LAN IP (`10.193.235.119`).
To reach it from WSL with native DDS (chosen approach):
1. **WSL2 mirrored networking** (Windows `.wslconfig`: `networkingMode=mirrored`) so WSL shares the
   host LAN.
2. **CycloneDDS on both ends** (`RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`) + a shared `ROS_DOMAIN_ID`
   (e.g. 42) set in the WSL shell **and** in the container/launch environment.
3. Verify: `ros2 topic list` from WSL shows the Pi topics; then RViz2/rqt/Foxglove.

Full step-by-step is in the dev-environment setup (Phase D of the project plan / `robot_ws/README.md`).

> The container currently uses Fast DDS with no domain set. For cross-machine work you'll standardize
> on CycloneDDS + domain 42 on **both** sides (documented in the dev-env setup). A Foxglove-bridge
> fallback over a single WebSocket is also available if you prefer not to depend on DDS discovery.
