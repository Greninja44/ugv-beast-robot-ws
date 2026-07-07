"""REST + WebSocket routes and SPA static mount."""
from __future__ import annotations

import asyncio
import os
import time

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse

from ..core.config import Settings
from ..core.lifespan import (
    get_bridge, get_camera, get_controls, get_launch_manager, get_settings, get_teleop, get_telemetry,
    get_waypoints,
)
from ..ros.bridge import RosBridge
from ..services.camera import BOUNDARY, CameraService
from ..services.controls import ControlsService
from ..services.launch_manager import ACTIONS, LaunchManager
from ..services.teleop import TeleopService
from ..services.waypoints import WaypointStore

router = APIRouter(prefix='/api')


def require_token(settings: Settings = Depends(get_settings),
                   authorization: str | None = Header(None)) -> None:
    """Guards control-affecting REST endpoints. Mirrors the WS CONTROL_OPS check:
    no auth_token configured => control permanently disabled (read-only for everyone)."""
    if settings.auth_token is None:
        raise HTTPException(403, 'control disabled: no auth_token configured on the robot')
    if authorization != f'Bearer {settings.auth_token}':
        raise HTTPException(401, 'invalid or missing token')


@router.get('/health')
def health(telemetry=Depends(get_telemetry), settings=Depends(get_settings)):
    graph = telemetry.bridge.graph_summary()
    return {
        'ok': True,
        'ros': graph['connected'],
        'nodes': graph['nodes'],
        'topics': graph['topics'],
        'read_only': settings.auth_token is None,
        'power_actions_enabled': settings.allow_system_power_actions,
    }


@router.get('/system')
def system(telemetry=Depends(get_telemetry)):
    return telemetry.snapshot()


@router.get('/system/ros-info')
def ros_info(settings: Settings = Depends(get_settings)):
    """Read-only connection info for the Settings page."""
    return {
        'ros_domain_id': os.environ.get('ROS_DOMAIN_ID', '0 (default)'),
        'rmw_implementation': os.environ.get('RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp (default)'),
        'camera_topic': settings.topic_camera,
        'read_only': settings.auth_token is None,
    }


@router.get('/topics')
def topics(bridge=Depends(get_bridge)):
    """Visible graph topics + types (diagnostics page)."""
    if not bridge.ok:
        return []
    return [{'name': n, 'types': t} for n, t in bridge._node.get_topic_names_and_types()]


@router.get('/teleop/limits')
def get_limits(teleop: TeleopService = Depends(get_teleop)):
    return teleop.limits()


@router.put('/teleop/limits')
def put_limits(body: dict, teleop: TeleopService = Depends(get_teleop), _=Depends(require_token)):
    teleop.set_limits(body.get('linear'), body.get('angular'))
    return teleop.limits()


@router.post('/teleop/estop')
def post_estop(teleop: TeleopService = Depends(get_teleop), _=Depends(require_token)):
    teleop.engage_estop()
    return {'active': True}


@router.post('/teleop/estop/release')
def post_estop_release(teleop: TeleopService = Depends(get_teleop), _=Depends(require_token)):
    teleop.release_estop()
    return {'active': False}


@router.get('/camera/streams')
def camera_streams(settings: Settings = Depends(get_settings)):
    """Single source today; shape supports adding more (docs/DASHBOARD_DESIGN.md §7)."""
    return [{'id': 'oak_rgb', 'name': 'OAK-D RGB', 'topic': settings.topic_camera}]


@router.get('/camera/stream')
async def camera_stream(camera: CameraService = Depends(get_camera), bridge: RosBridge = Depends(get_bridge)):
    """MJPEG multipart stream. Lazy: the ROS subscription exists only while at
    least one client is actively streaming (acquire on connect, release on
    disconnect — same rule as every WS channel in ros/bridge.py)."""
    bridge.acquire('camera')

    async def gen():
        try:
            async for chunk in camera.mjpeg_stream():
                yield chunk
        finally:
            bridge.release('camera')

    return StreamingResponse(gen(), media_type=f'multipart/x-mixed-replace; boundary={BOUNDARY.decode()}')


@router.get('/camera/snapshot')
def camera_snapshot(camera: CameraService = Depends(get_camera), bridge: RosBridge = Depends(get_bridge)):
    """One-shot JPEG capture. Briefly acquires the camera sub if nothing else is
    already streaming, so a snapshot works even with no active viewers."""
    bridge.acquire('camera')
    try:
        deadline = time.monotonic() + 1.5
        jpeg = camera.snapshot()
        while jpeg is None and time.monotonic() < deadline:
            time.sleep(0.05)
            jpeg = camera.snapshot()
    finally:
        bridge.release('camera')
    if jpeg is None:
        raise HTTPException(404, 'no camera frame available')
    return Response(content=jpeg, media_type='image/jpeg')


@router.get('/controls/led')
def get_led(controls: ControlsService = Depends(get_controls)):
    return {'on': controls.led_on}


@router.put('/controls/led')
def put_led(body: dict, controls: ControlsService = Depends(get_controls), _=Depends(require_token)):
    return {'on': controls.set_led(bool(body.get('on')))}


@router.get('/controls/actions')
def list_actions(lm: LaunchManager = Depends(get_launch_manager)):
    return lm.status()


@router.post('/controls/actions/{name}/start')
async def start_action(name: str, lm: LaunchManager = Depends(get_launch_manager), _=Depends(require_token)):
    if name not in ACTIONS:
        raise HTTPException(404, f'unknown action: {name}')
    await lm.start(name)
    return lm.status()


@router.post('/controls/actions/{name}/stop')
async def stop_action(name: str, lm: LaunchManager = Depends(get_launch_manager), _=Depends(require_token)):
    if name not in ACTIONS:
        raise HTTPException(404, f'unknown action: {name}')
    await lm.stop(name)
    return lm.status()


@router.post('/controls/map/save')
async def save_map(body: dict, bridge: RosBridge = Depends(get_bridge),
                    settings: Settings = Depends(get_settings), _=Depends(require_token)):
    name = str(body.get('name', '')).strip()
    if not name or '/' in name or '..' in name:
        raise HTTPException(400, 'invalid map name')
    full_path = os.path.join(settings.map_save_dir, name)
    ok, detail = await asyncio.to_thread(bridge.save_map_blocking, full_path)
    if not ok:
        raise HTTPException(502, detail or 'map save failed')
    return {'saved': True, 'path': full_path}


@router.get('/map')
def get_map(bridge: RosBridge = Depends(get_bridge)):
    """Current occupancy grid as a PNG; metadata (needed to convert a click back
    into map-frame world coordinates) rides along as response headers so the
    frontend gets both in one request."""
    bridge.acquire('map')
    try:
        deadline = time.monotonic() + 1.5
        png, meta, _ = bridge.map_snapshot()
        while png is None and time.monotonic() < deadline:
            time.sleep(0.05)
            png, meta, _ = bridge.map_snapshot()
    finally:
        bridge.release('map')
    if png is None:
        raise HTTPException(404, 'no map available (is SLAM/Nav2 running?)')
    return Response(content=png, media_type='image/png', headers={
        'X-Map-Width': str(meta['width']), 'X-Map-Height': str(meta['height']),
        'X-Map-Resolution': str(meta['resolution']),
        'X-Map-Origin-X': str(meta['origin_x']), 'X-Map-Origin-Y': str(meta['origin_y']),
    })


@router.post('/percepts/ingest')
def ingest_percepts(body: dict, bridge: RosBridge = Depends(get_bridge), _=Depends(require_token)):
    """Accept detections from an external (GPU) detector that can't reach the Pi over
    DDS, and republish them as ROS Percepts. Body: {"detections": [{label, confidence,
    bbox:[x,y,w,h], bearing?}, ...]}. bbox normalised [0,1]. Auth-gated like other
    control endpoints — an unauthenticated client shouldn't be able to inject percepts."""
    detections = body.get('detections', [])
    n = 0
    for d in detections:
        bbox = d.get('bbox', [0.0, 0.0, 0.0, 0.0])
        if len(bbox) != 4:
            continue
        bridge.publish_percept(
            label=str(d.get('label', 'object')),
            confidence=float(d.get('confidence', 0.0)),
            bbox=bbox,
            bearing=float(d.get('bearing', 0.0)),
        )
        n += 1
    return {'ok': True, 'ingested': n}


@router.post('/nav/goal')
def send_nav_goal(body: dict, bridge: RosBridge = Depends(get_bridge), _=Depends(require_token)):
    bridge.send_nav_goal(float(body['x']), float(body['y']), float(body.get('yaw', 0.0)),
                          body.get('frame', 'map'))
    return {'ok': True}


@router.post('/nav/cancel')
def cancel_nav_goal(bridge: RosBridge = Depends(get_bridge), _=Depends(require_token)):
    bridge.cancel_nav_goal()
    return {'ok': True}


@router.get('/nav/waypoints')
def list_waypoints(store: WaypointStore = Depends(get_waypoints)):
    return store.list()


@router.post('/nav/waypoints')
def add_waypoint(body: dict, store: WaypointStore = Depends(get_waypoints), _=Depends(require_token)):
    name = str(body.get('name', '')).strip() or 'waypoint'
    return store.add(name, float(body['x']), float(body['y']), float(body.get('yaw', 0.0)))


@router.delete('/nav/waypoints/{wp_id}')
def delete_waypoint(wp_id: str, store: WaypointStore = Depends(get_waypoints), _=Depends(require_token)):
    if not store.delete(wp_id):
        raise HTTPException(404, 'waypoint not found')
    return {'ok': True}


def require_power_actions(settings: Settings = Depends(get_settings)) -> None:
    if not settings.allow_system_power_actions:
        raise HTTPException(403, 'reboot/shutdown disabled (set allow_system_power_actions in dashboard.yaml)')


@router.post('/system/reboot')
async def system_reboot(_a=Depends(require_token), _b=Depends(require_power_actions)):
    await asyncio.create_subprocess_exec('sudo', 'reboot')
    return {'ok': True}


@router.post('/system/shutdown')
async def system_shutdown(_a=Depends(require_token), _b=Depends(require_power_actions)):
    await asyncio.create_subprocess_exec('sudo', 'shutdown', '-h', 'now')
    return {'ok': True}


def mount(app: FastAPI) -> None:
    app.include_router(router)

    @app.websocket('/ws')
    async def ws_endpoint(ws: WebSocket):
        mgr = ws.app.state.ws_manager
        settings = ws.app.state.settings
        token = ws.query_params.get('token')
        authenticated = settings.auth_token is not None and token == settings.auth_token

        client = await mgr.connect(ws, authenticated)
        send_task = asyncio.create_task(mgr.sender(client))
        try:
            while True:
                raw = await ws.receive_json()
                await mgr.handle_message(client, raw)
        except WebSocketDisconnect:
            pass
        finally:
            send_task.cancel()
            mgr.disconnect(client)

    # SPA static mount happens in main.create_app (needs settings at creation time).
