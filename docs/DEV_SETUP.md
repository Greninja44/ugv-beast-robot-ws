# Development Environment Setup (WSL ↔ Pi)

Goal: Pi runs **only** drivers/robot nodes; WSL runs **all** GUIs (RViz2, rqt, Foxglove, MoveIt) and
your dev tools — **no X11 forwarding**. GUIs talk to the Pi over native DDS.

Status legend: ✅ already applied by tooling · ⬜ you must run.

## 0. SSH (done)
✅ Key-based login configured: `~/.ssh/id_ed25519_ugv`, alias **`ugv`** in `~/.ssh/config`.
Test: `ssh ugv hostname` → `raspberrypi`.

## 1. WSL2 mirrored networking  ⬜ (Windows side)
✅ `.wslconfig` written to `C:\Users\iamdu\.wslconfig` (mirrored mode).
⬜ Apply it — in **Windows PowerShell**:
```powershell
wsl --shutdown
```
Reopen your WSL terminal. Verify the NAT IP is gone (WSL now shares the host LAN):
```bash
ip -4 addr show | grep inet        # should show your LAN IP, not 172.17.x
```
> Requires Windows 11 22H2+. If mirrored mode causes issues, delete `.wslconfig`, `wsl --shutdown`,
> and use the Foxglove-bridge fallback (§6).

## 2. CycloneDDS on WSL  ⬜ (needs sudo)
```bash
sudo apt update && sudo apt install -y ros-humble-rmw-cyclonedds-cpp
```
✅ Env is pre-wired: `~/.bashrc` sources `~/robot_ws/dev/robot_env.sh`, which sets
`ROS_DOMAIN_ID=42` and switches to `rmw_cyclonedds_cpp` **only once the package is installed**
(so nothing breaks before you install it). `CYCLONEDDS_URI` → `~/robot_ws/dev/cyclonedds.xml`.
After install, open a new shell and check:
```bash
echo $RMW_IMPLEMENTATION      # rmw_cyclonedds_cpp
echo $ROS_DOMAIN_ID           # 42
```

## 3. CycloneDDS on the Pi container  ⬜
Run from WSL:
```bash
bash ~/robot_ws/dev/setup_pi_container.sh
```
Installs `ros-humble-rmw-cyclonedds-cpp` in `ugv_rpi_ros_humble` and sets matching env
(`RMW_IMPLEMENTATION`, `ROS_DOMAIN_ID=42`, `UGV_MODEL=ugv_beast`, `LDLIDAR_MODEL=ld06`).
Re-run if you ever recreate the container with `docker run`.

## 4. Verify the link  ⬜
Terminal A (Pi) — bring up the vendor stack:
```bash
ssh ugv
docker exec -it ugv_rpi_ros_humble bash
source /opt/ros/humble/setup.bash && source /home/ws/ugv_ws/install/setup.bash
ros2 launch ugv_bringup bringup_imu_ekf.launch.py
```
Terminal B (WSL):
```bash
ros2 topic list           # should list /odom, /scan, /imu/data, /voltage, /tf ...
ros2 topic echo /odom --once
rviz2                     # Fixed Frame: base_footprint; add TF, LaserScan(/scan), Odometry(/odom)
rqt_graph
```

## 5. GUI tools on WSL  ⬜ (needs sudo, one-time)
```bash
sudo apt install -y ros-humble-rviz2 ros-humble-rqt* ros-humble-foxglove-bridge
# MoveIt (optional, heavy): sudo apt install -y ros-humble-moveit
```
Launch natively on WSL (WSLg gives them a window — no X11 forwarding, no MobaXterm).

## 6. Foxglove path (optional, robust fallback)
On the Pi container: `ros2 run foxglove_bridge foxglove_bridge` (port 8765). On WSL, open
**Foxglove Studio** → connect to `ws://<pi-lan-ip>:8765`. Works even without mirrored networking.

## 7. VS Code Remote-SSH  ⬜
- Install the **Remote - SSH** extension.
- `Ctrl+Shift+P` → *Remote-SSH: Connect to Host* → **`ugv`** (uses `~/.ssh/config`).
- Open `/home/ws` to browse vendor source (read-only habit), or `~/robot_ws` once it's cloned to the Pi.
- The vendor ROS runs **inside the container**; to build/run there, use a terminal:
  `docker exec -it ugv_rpi_ros_humble bash`. (For in-container editing, the *Dev Containers* extension
  can attach to `ugv_rpi_ros_humble`.)
- Edit **this** workspace (`~/robot_ws`) either on WSL (then sync/clone to the Pi) or open it via
  Remote-SSH on the Pi.

## 8. Serial ownership (already OK)
✅ `app.py` is **not** in the Pi crontab (only Jupyter autostarts), so the ESP32 serial is free for the
ROS bringup. Nothing to disable. If you ever add it back via `ugv_rpi/autorun.sh`, remove that
`@reboot ... app.py` crontab line so the ROS driver can own `/dev/ttyAMA0`:
```bash
ssh ugv 'crontab -l | grep -v "app.py" | crontab -'   # reversible
```

## Deploying your code to the Pi
Sync `~/robot_ws` to the Pi (excluding build artifacts) and build in the container:
```bash
rsync -az --exclude build --exclude install --exclude log ~/robot_ws/ ugv:~/robot_ws/
ssh ugv 'docker exec -it ugv_rpi_ros_humble bash -lc "cd ~/robot_ws && ./build_pi.sh"'
```
