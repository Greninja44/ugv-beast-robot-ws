# robot_ws — your code for the Waveshare UGV Beast

A **separate, clean** ROS 2 (Humble) workspace that layers your own software on top of the vendor
Waveshare stack (`/home/ws/ugv_ws` on the Pi) **without modifying it**. All integration is via ROS
topics / services / actions / TF.

See [`docs/`](docs/INDEX.md) for full reverse-engineered documentation of the vendor system.

## Packages (hybrid: Pi runtime vs WSL compute)

| Package | Where | Role |
|---------|-------|------|
| `robot_interfaces` | **both** | Shared msg/srv/action (`Percept`, `SetMode`, `RunSkill`, `NavigateTo`). |
| `robot_perception` | Pi | Consumes vendor `/image_raw`, `/scan` → `Percept`. |
| `robot_navigation` | Pi | `NavigateTo` action fronting vendor Nav2. |
| `robot_manipulation` | Pi | Aims the 2-DOF pan-tilt gimbal at targets. |
| `robot_skills` | Pi | `RunSkill` action library (behaviours). |
| `robot_bringup` | Pi + WSL | Launch files: `robot_pi.launch.py`, `robot_wsl.launch.py`. |
| `robot_ai` | WSL | LLM decision layer → sends `RunSkill` goals. |
| `robot_mcp` | WSL | MCP server exposing the ROS graph as AI tools. |

## Build

```bash
# On WSL (dev box):
./build_wsl.sh          # robot_interfaces + robot_ai + robot_mcp
# On the Pi (in the ROS container, workspace synced/cloned there):
./build_pi.sh           # robot_interfaces + perception/nav/manip/skills/bringup
source install/setup.bash
```

`robot_interfaces` is built on **both** machines so message types match across the DDS link.

## Run

```bash
# Pi (alongside the vendor bringup):
ros2 launch robot_bringup robot_pi.launch.py
# WSL:
ros2 launch robot_bringup robot_wsl.launch.py
```

## Networking (WSL ↔ Pi)
Native DDS across WSL2 and the Pi uses **WSL2 mirrored networking + CycloneDDS + a shared
`ROS_DOMAIN_ID`**. Setup steps live in the dev-env notes (Phase D). Quick check from WSL once the Pi
stack runs: `ros2 topic list` should show the Pi's `/odom`, `/scan`, etc.

## Golden rules
- **Never** edit `/home/ws/ugv_ws` (vendor). Consume it through ROS interfaces only.
- **Never** open `/dev/serial0` yourself — drive via `/cmd_vel` / the vendor driver.
- Only one base-serial owner at a time (vendor `ugv_bringup` **or** `ugv_rpi/app.py`).
