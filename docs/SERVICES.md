# Services

The vendor stack defines **one custom service**; everything else is the standard per-node parameter
service set (`get/set/list/describe_parameters`, `get_parameter_types`), which is omitted here.

## Custom service

### `ugv_interface/srv/MapSave`
```
string mapname
---
string response
```
- **Purpose:** save the current SLAM map under `mapname`.
- **Server:** provided by the SLAM/map tooling in `ugv_slam` / `ugv_nav` (map-save helper), active only
  when a SLAM session is running.
- **Client:** the web app / tools invoke it to persist maps into `ugv_nav/maps/`.

> During the live capture no SLAM session was running, so `ros2 service list` showed only parameter
> services. Bring up `ugv_slam` (cartographer/gmapping) to see the map-save service.

## Standard services you will still see
Each node exposes:
`/<node>/describe_parameters`, `/get_parameter_types`, `/get_parameters`, `/list_parameters`,
`/set_parameters`, `/set_parameters_atomically`. Use `ros2 param` rather than calling these directly.

## Integration note
For your own request/response needs, define services in **`robot_interfaces`** and keep them separate
from vendor interfaces. Nav2 and SLAM lifecycle is managed via **actions + lifecycle**, not custom
services — prefer those seams (see [ACTIONS.md](ACTIONS.md), [NAVIGATION.md](NAVIGATION.md)).
