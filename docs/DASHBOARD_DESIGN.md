# robot_dashboard — Design Proposal (v1, pre-approval)

Status: **PROPOSAL — no code written.** Grounded in the live-verified vendor graph
(see [INDEX.md](INDEX.md), [TOPICS.md](TOPICS.md), [HARDWARE.md](HARDWARE.md)).

---

## 1. Overall architecture

```
┌────────────────────────────── Browser (desktop / tablet / phone) ─────────────────────────────┐
│  React SPA (TypeScript, Vite, Tailwind, shadcn/ui, Zustand, React Query, Framer Motion)        │
│  · REST (React Query)  · 1× WebSocket (telemetry/teleop)  · <img> MJPEG stream (camera)        │
└───────────────▲────────────────────────▲──────────────────────────────▲───────────────────────┘
                │ HTTPS/HTTP REST        │ WS JSON channels             │ HTTP multipart MJPEG
┌───────────────┴────────────────────────┴──────────────────────────────┴───────────────────────┐
│  BACKEND — FastAPI + uvicorn (asyncio)                    [runs where ROS runs]                │
│  api/ (REST routers) · ws/ (connection mgr + channels) · services/ (domain logic)              │
│  ────────────────────────── asyncio ⇄ ROS bridge (thread-safe queues) ───────────────────────  │
│  ros/ — ONE rclpy node "dashboard_node" in a dedicated executor thread                         │
│    subs: /odom /scan /imu/data /voltage /tf /tf_static /rosout /oak/.../compressed             │
│    pubs: /cmd_vel /goal_pose /ugv/led_ctrl      clients: MapSave, Nav2 actions, behavior       │
└───────────────▲────────────────────────────────────────────────────────────────────────────────┘
                │ DDS (CycloneDDS, ROS_DOMAIN_ID=42)
        VENDOR STACK (untouched): ugv_bringup/driver/base_node/Nav2/SLAM/depthai · ESP32 · LD06
```

**Key decisions & why**

| Decision | Why |
|---|---|
| Backend is the *only* ROS process; frontend is pure web | Your requirement; also lets the UI run on any device with zero ROS deps. |
| **One** rclpy node, one executor thread, asyncio main loop | rclpy and asyncio have separate event models. A single node + `MultiThreadedExecutor` in one thread, bridged by thread-safe queues, avoids the classic deadlock/GIL soup of "rclpy inside async handlers". No globals — the node lives in FastAPI `app.state` via lifespan. |
| **Lazy subscriptions** | The backend only subscribes to a ROS topic while ≥1 web client is on that channel. On a Pi 5 sharing CPU with SLAM/Nav2, idle dashboards must cost ~0. |
| Server-side **rate limiting per channel** (scan 5 Hz, odom/imu 10 Hz, tf 2 Hz, latest-wins) | Browsers don't need 100 Hz IMU; the Pi's uplink and the phone's CPU do need protection. Drop-oldest keeps latency bounded. |
| Camera via **HTTP MJPEG** in v1, WebRTC as v2 (§ Camera) | See comparison. MJPEG = 30 lines of code, works in `<img>` on every device. |
| Teleop safety enforced **server-side** (watchdog, clamps, e-stop latch) | Never trust the client: if the tab crashes mid-drive, the backend watchdog zeroes `/cmd_vel` within 300 ms. Vendor stack has no watchdog of its own. |
| Package is `ament_python` in `~/robot_ws/src` | Same conventions as your other 8 packages; installable, launchable via `robot_bringup`. Frontend `dist/` ships as package data. |

**Where it runs**
- **Prod:** backend inside the Pi's ROS container (`ugv_rpi_ros_humble`) — rclpy only exists there; `--network host` exposes port 8080 on the LAN. Frontend is pre-built static files served by FastAPI itself (one process, one port, no CORS pain).
- **Dev:** backend on WSL (same code, DDS over mirrored network), frontend on Vite dev server with proxy → hot reload.

---

## 2. Folder structure

```
~/robot_ws/src/robot_dashboard/
├── package.xml / setup.py / setup.cfg / resource/     # ament_python plumbing
├── robot_dashboard/                # PYTHON BACKEND (the ROS-visible module)
│   ├── main.py                     # uvicorn entry (console_script: dashboard)
│   ├── core/
│   │   ├── config.py               # pydantic-settings: ports, token, topic map, limits
│   │   └── lifespan.py             # startup/shutdown: spin up ROS thread, DI wiring
│   ├── ros/
│   │   ├── node.py                 # the single rclpy Node + executor thread
│   │   ├── bridge.py               # thread-safe asyncio⇄ROS queues, latest-wins buffers
│   │   ├── topics.py               # subscription registry (lazy sub/unsub, QoS profiles)
│   │   ├── publishers.py           # cmd_vel, goal_pose, led_ctrl
│   │   └── clients.py              # service/action clients (MapSave, Nav2, behavior)
│   ├── services/                   # domain logic (no FastAPI, no raw rclpy imports)
│   │   ├── telemetry.py            # aggregates odom/voltage/imu → dashboard state
│   │   ├── teleop.py               # watchdog, clamps, e-stop latch, deadman
│   │   ├── camera.py               # CompressedImage → MJPEG frames, snapshot, record
│   │   ├── navigation.py           # goals, waypoints, Nav2 lifecycle state
│   │   ├── controls.py             # slam/map/led actions (allowlisted launch mgr)
│   │   ├── system.py               # psutil CPU/mem/temp, DDS/ROS health
│   │   └── logs.py                 # /rosout ring buffer, filters, export
│   ├── ws/
│   │   ├── manager.py              # connection registry, channel fanout, backpressure
│   │   └── protocol.py             # message schema (pydantic), channel names
│   └── api/
│       ├── router.py               # mounts sub-routers + static frontend
│       └── routes_{system,teleop,camera,nav,controls,logs,settings}.py
├── frontend/                       # REACT APP (never imported by Python)
│   ├── index.html / vite.config.ts / tailwind.config.ts / tsconfig.json
│   └── src/
│       ├── app/                    # router, layout shell, providers
│       ├── pages/                  # Dashboard | Camera | Teleop | Sensors | Nav | Controls | Logs | Settings
│       ├── components/             # ui/ (shadcn), charts/, StatusPill, GlassCard...
│       ├── features/               # per-domain: teleop/ (joystick, gamepad), sensors/ (canvas scan), nav/ (map canvas)
│       ├── lib/ws.ts               # typed WS client, auto-reconnect, channel hooks
│       ├── lib/api.ts              # REST client (React Query fns)
│       └── stores/                 # zustand: connection, telemetry, teleop, settings
├── launch/dashboard.launch.py      # backend node (+ optional depthai camera include)
├── config/dashboard.yaml           # default settings (rates, limits, topics, token)
├── docs/ (this file moves here, + API.md, PROTOCOL.md)
├── tests/                          # pytest: protocol, teleop safety, services (ROS mocked)
└── README.md
```

Why: backend layering (api → services → ros) means HTTP routes never touch rclpy directly —
services are testable with a mocked bridge, and the ROS layer is swappable (e.g. multi-robot later).

---

## 3. Backend design

**Threading/async model** (the part that usually goes wrong):
- Main thread: uvicorn's asyncio loop (HTTP + WS).
- ROS thread: `rclpy.init()` → `dashboard_node` → `MultiThreadedExecutor.spin()`.
- ROS→web: subscriber callbacks write into **per-channel latest-wins buffers**; an asyncio task
  per channel drains at the channel's max rate and fans out to subscribed WS clients. Backpressure
  = skip stale frames, never queue unbounded.
- Web→ROS: WS teleop messages go into a queue read by the teleop service, which publishes
  `/cmd_vel` on a fixed 15 Hz timer **only while fresh** (see safety).
- Shutdown: FastAPI lifespan stops the executor, destroys the node cleanly.

**Dependency injection:** config + bridge + services constructed once in lifespan, exposed via
`Depends(get_teleop_service)` etc. No module-level singletons.

**Teleop safety (server-side, non-negotiable):**
- Clamp: `|linear| ≤ max_speed` (default 0.5 m/s; vendor slow=0.2, max=1.3), `|angular| ≤ max_yaw`.
- Watchdog: no teleop packet for **300 ms** → publish zero Twist ×3 → stop publishing.
- Deadman: client must set `deadman:true` in every packet (finger on joystick / key held).
- **E-stop latch:** `POST /api/teleop/estop` (or WS op) → zero `/cmd_vel` continuously, reject all
  motion input until explicit release. Overrides everything, including Nav2 goals (also cancels them).
- Single-driver rule: one WS client holds the "control lease"; others are view-only until it's released.

**System stats:** no ROS topic exists for CPU/mem/temp → `psutil` + `/sys/class/thermal` in the
backend (privileged container sees host values). Battery % derived from `/voltage` with a 3S LiPo
curve (9.6 V→0 %, 12.6 V→100 %), plus low-voltage warning at ≤10.5 V.

---

## 4. Frontend design

- **Shell:** left icon sidebar (8 pages) + top status strip (conn ● ROS ● battery ▮ voltage,
  latency ms, e-stop button always visible). Dark theme default, glass cards
  (`bg-white/5 backdrop-blur border-white/10`), Framer Motion page fades ≤150 ms.
- **State:** Zustand stores split by domain: `useConnection` (ws state, latency), `useTelemetry`
  (latest odom/imu/voltage/scan refs), `useTeleop` (input state, lease, e-stop), `useSettings`
  (persisted to localStorage). REST data (settings, waypoints, log export) via React Query.
- **High-rate rendering rule:** LaserScan, map, compass render to **`<canvas>`** via
  `requestAnimationFrame`, reading the latest Zustand ref — React re-renders are *not* driven by
  20 Hz data. This is the difference between 3 % and 60 % CPU on a phone.
- **Teleop inputs:** unified `TeleopSource` interface → virtual joystick (pointer events, touch-first),
  WASD/arrows (keyboard), Gamepad API (Xbox/PS5 — same API, different mapping presets). All feed one
  20 Hz sampler that emits WS teleop packets while deadman held.
- **Responsive:** desktop = grid layout; tablet = 2-col; phone = single column, Teleop page becomes
  fullscreen joystick + video. Camera page supports fullscreen API + screenshot (canvas grab) +
  client-side recording (MediaRecorder on the MJPEG `<canvas>` mirror; server-side recording в v2).

---

## 5. WebSocket protocol

Single endpoint `ws://host:8080/ws?token=…`, JSON text frames (camera is *not* on the WS — see §Camera).

```jsonc
// client → server
{"op":"sub",   "ch":"telemetry"}                    // subscribe channel
{"op":"unsub", "ch":"scan"}
{"op":"teleop","seq":417,"lin":0.32,"ang":-0.4,"deadman":true}
{"op":"estop"}            {"op":"estop_release"}
{"op":"ping","t":1712345} // latency probe

// server → client
{"op":"msg","ch":"telemetry","data":{"voltage":11.94,"pct":72,"lin":0.0,"ang":0.0,
  "cpu":23,"mem":41,"temp":52.1,"ros":true,"loc":"odom_only"},"ts":...}
{"op":"msg","ch":"scan","data":{"amin":-3.14,"ainc":0.0174,"rmax":12.0,
  "ranges":[...360 pts, decimated, mm as uint16...]},"ts":...}
{"op":"msg","ch":"log","data":{"lvl":"WARN","node":"/base_node","msg":"...","ts":...}}
{"op":"lease","holder":"c7f2","you":true}           // control lease changes
{"op":"pong","t":1712345}
{"op":"err","code":"ESTOP_ACTIVE","detail":"motion rejected"}
```

Channels: `telemetry` (2 Hz), `odom` (10 Hz), `imu` (10 Hz), `scan` (5 Hz, decimated ×2),
`tf` (2 Hz, only frames the UI needs), `nav` (2 Hz: state/path/goal), `log` (event-driven,
throttled 20 msg/s). Rates are server-enforced and configurable in `config/dashboard.yaml`.
Multiple clients: fanout with per-client send queues (max 16, drop-oldest); slow phones can't
stall the robot loop.

---

## 6. REST API (summary)

| Method & path | Purpose |
|---|---|
| `GET /api/health` | backend+ROS+DDS status (also used for conn indicator) |
| `GET /api/system` | CPU, mem, temp, disk, uptime, ros distro/domain |
| `GET /api/topics` | live `ros2 topic list`-equivalent w/ types + Hz (diagnostics) |
| `POST /api/teleop/estop` · `/estop/release` | e-stop latch (also via WS) |
| `PUT /api/teleop/limits` | max linear/angular (clamped to config ceiling) |
| `GET /api/camera/streams` | available cameras + active transport |
| `GET /api/camera/stream/{id}` | **multipart/x-mixed-replace MJPEG** |
| `POST /api/camera/snapshot` | server-side JPEG capture → download |
| `POST /api/nav/goal` `{x,y,yaw,frame}` | send NavigateToPose (Nav2 up) or `/goal_pose` |
| `POST /api/nav/cancel` | cancel current Nav2 goal |
| `GET/POST/DELETE /api/nav/waypoints` | CRUD, persisted to config dir |
| `GET /api/map` | current OccupancyGrid as PNG + metadata (for canvas) |
| `POST /api/controls/{action}` | allowlisted actions, see §7 table |
| `GET /api/logs?level=&node=&q=&limit=` | ring-buffer query · `GET /api/logs/export` |
| `GET/PUT /api/settings` | persisted dashboard settings |

Errors: RFC-7807-style JSON (`{type,title,status,detail}`); destructive endpoints require the
auth token **and** `{"confirm":true}`.

---

## 7. ROS integration layer — mapped to what actually exists

**Verified-live topics** (from our capture): `/cmd_vel`, `/odom`, `/scan` (10 Hz), `/imu/data`,
`/voltage`, `/tf`, `/tf_static`, `/ugv/joint_states`, `/ugv/led_ctrl`, `/rosout`. QoS: sensors
subscribed `BEST_EFFORT/VOLATILE` to match vendor publishers; `/cmd_vel` published `RELIABLE`.

**Camera reality:** `/image_raw` is **dead** (vendor usb_cam targets the removed gimbal cam).
Source of truth = **OAK-D** via `depthai_ros_driver` → `.../image_raw/compressed` (JPEG). Backend
subscribes **CompressedImage only** (no raw 640×480×3 @30 Hz over DDS) and re-muxes to MJPEG.
`launch/dashboard.launch.py` optionally includes the depthai camera launch.

**Robot Controls page — honest mapping:**

| Button | Backing interface | Status |
|---|---|---|
| Start/Stop SLAM | *(none — launch-based)* | via **allowlisted launch manager**: backend runs/kills exactly `ros2 launch ugv_slam cartographer.launch.py` etc. from a fixed table. No arbitrary commands. |
| Save Map | `MapSave` srv (when SLAM tooling up) / `nav2 map_saver_cli` fallback | ✅ |
| Load Map | launch manager: nav with `map:=<file>` | ✅ (allowlisted) |
| LED control | pub `/ugv/led_ctrl` Float32MultiArray | ✅ verified topic |
| Center Gimbal | *(gimbal physically removed)* | **hidden/disabled**, slot kept for future arm |
| Reset Odometry | *(no vendor service exists)* | **shown disabled** with tooltip; doing it "somehow" would mean killing vendor nodes — not acceptable |
| Reboot/Shutdown robot | *(OS-level, not ROS)* | `systemd-run`/`shutdown` from backend — **disabled by default**, enable in config + token + confirm |
| Manual/Autonomous mode | e-stop/lease state + Nav2 goal gating in backend | ✅ (dashboard-level concept; also exposed for your `robot_interfaces/SetMode` later) |

**Nav2:** action clients for `navigate_to_pose` + lifecycle state polling; when Nav2 isn't
running the page shows "Navigation stack offline" instead of pretending. `behavior` action client
included for vendor behaviors.

**Camera transport comparison (requested):**

| | image_transport (ROS) | MJPEG over HTTP | WebRTC (aiortc) |
|---|---|---|---|
| Browser-consumable | ❌ (ROS-internal only — it's the *source*, not a delivery tech) | ✅ `<img>` everywhere | ✅ `<video>` |
| Latency | — | ~150–400 ms | **<100 ms** |
| CPU on Pi | — | **~0** if source is already JPEG (OAK-D/compressed) | high for SW H.264; ~0 if we use **OAK-D's onboard H.264 encoder** |
| Complexity | — | trivial | high (signaling, ICE, aiortc) |
| Multi-client | — | cheap (fan out same JPEGs) | per-peer encode unless SFU |

**Recommendation:** **v1 = MJPEG** (re-mux vendor JPEGs, zero encode cost, works on phone/tablet
instantly). **v2 = WebRTC fed by the OAK-D's on-camera H.264 encoder** — that's the only path to
<100 ms glass-to-glass without cooking the Pi. The camera service is transport-abstracted so v2
slots in without touching pages.

---

## 8. Security

Threat model: hobby robot on a trusted LAN — but with motion + shutdown capability, so:
- **Bearer token** (single shared token in `config/dashboard.yaml`, not in git): required for WS
  connect and all non-GET endpoints. UI stores it after a one-time entry screen.
- **Read-only mode without token:** telemetry/camera viewable, all control ops 403.
- Control lease (one driver at a time) + server-side clamps + e-stop latch (see §3).
- Destructive ops (reboot/shutdown, launch manager) individually **disabled by default** in config;
  enabling is an explicit config edit on the robot.
- CORS locked to configured origins; WS checks `Origin`; rate limit on control endpoints.
- No TLS in v1 (LAN); doc how to front with caddy/traefik if ever exposed. Never expose to WAN as-is.

## 9. Deployment

- **Prod (Pi):** frontend built on WSL (`npm run build`) → `dist/` synced with the package via the
  existing `rsync` deploy flow → backend serves it. Backend runs in the ROS container:
  `docker exec -d ugv_rpi_ros_humble ... ros2 launch robot_dashboard dashboard.launch.py`
  (piggybacks CycloneDDS/domain-42 env from Phase D). Port **8080** on the LAN via `--network host`.
  Autostart later = one `@reboot` cron/systemd line (your call, off by default).
- **Dev (WSL):** `uvicorn robot_dashboard.main:app --reload` + `npm run dev` (Vite proxies
  `/api` + `/ws` to :8080). Same DDS domain reaches the real robot; or run against `ros2 bag play`.
- **Budget:** backend idle <2 % Pi CPU (lazy subs), streaming 1 camera + full telemetry ≈ 8–12 %.

## 10. Step-by-step implementation plan (approval gates)

| Phase | Deliverable | Acceptance test |
|---|---|---|
| **0. Toolchain** | node LTS + npm on WSL; pip deps (fastapi, uvicorn, psutil, pydantic-settings) on WSL + Pi container | versions print |
| **1. Skeleton + WS core** | package builds; backend runs; WS connect/sub/ping; frontend shell with sidebar, status strip, dark theme; Dashboard page shows live voltage/odom from the real robot | phone + desktop both show live telemetry |
| **2. Teleop + safety** | joystick/WASD/gamepad → `/cmd_vel`; watchdog, clamps, deadman, e-stop, lease | robot drives; killing the tab stops it <300 ms; e-stop latches |
| **3. Sensors page** | canvas LaserScan, IMU/compass, odom plots, TF health | scan renders 5 Hz smooth on phone |
| **4. Camera** | depthai include, MJPEG stream, fullscreen/snapshot/switch | live OAK-D video on all devices |
| **5. Navigation** | map PNG endpoint, goal send/cancel, pose/path overlay, waypoints | click-to-goal round trip works with Nav2 up |
| **6. Controls + Logs + Settings** | allowlisted launch mgr (SLAM/map), LED, log viewer w/ filter+export, settings persistence | each button verified against real stack |
| **7. Hardening** | tests (protocol, teleop safety), docs (API.md, PROTOCOL.md), deploy script, autostart option | pytest green; fresh-device install doc walkthrough |

Each phase ends with a demo against the real robot and your go/no-go for the next.
