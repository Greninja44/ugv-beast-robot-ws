"""App wiring: construct everything once at startup, tear down cleanly. No globals —
all shared state hangs off app.state and is reached via the get_* dependencies."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from ..ros.bridge import RosBridge
from ..services.camera import CameraService
from ..services.controls import ControlsService
from ..services.launch_manager import LaunchManager
from ..services.system import SystemStats
from ..services.telemetry import TelemetryService
from ..services.teleop import TeleopService
from ..services.waypoints import WaypointStore
from ..ws.manager import WsManager
from .config import Settings, load_settings


def make_lifespan(settings: Settings):
    """Build the lifespan with settings injected (they're needed at app-creation
    time too, for the static mount — see main.create_app)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bridge = RosBridge(settings)
        bridge.start()
        system = SystemStats()
        telemetry = TelemetryService(settings, bridge, system)
        teleop = TeleopService(settings, bridge)
        camera = CameraService(settings, bridge)
        controls = ControlsService(bridge)
        launch_manager = LaunchManager(vendor_setup=settings.vendor_setup)
        waypoints = WaypointStore(settings.waypoints_file)
        ws_manager = WsManager(settings, bridge, telemetry, teleop)

        def _apply_mode(mode: str) -> None:
            """Fire-and-forget: push a mode change to robot_skills' mode arbiter so
            autonomous nodes (nav_bridge, skill_server) stand down the instant a human
            takes teleop or hits e-stop, and stay down until someone deliberately
            re-engages autonomy. Never blocks the caller — set_mode_blocking runs on a
            worker thread; if mode_server isn't up yet (e.g. nothing launched on the Pi
            during WSL-only dev), this just logs and teleop/e-stop keep working locally."""
            async def _do():
                ok, msg = await asyncio.to_thread(bridge.set_mode_blocking, mode)
                if not ok:
                    print(f"[dashboard] SetMode('{mode}') failed: {msg}")
            asyncio.create_task(_do())

        def _on_lease_change(holder: str | None) -> None:
            ws_manager.broadcast_lease(holder)
            # Human grabbed the joystick -> 'teleop' (revokes autonomous authority
            # immediately). Released (deadman up, watchdog timeout, disconnect) ->
            # 'idle' — deliberately does NOT resume whatever autonomous mode was
            # active before; re-engaging autonomy is a separate, explicit action.
            _apply_mode('teleop' if holder is not None else 'idle')

        def _on_estop_change(active: bool) -> None:
            ws_manager.broadcast_estop(active)
            if active:
                # Unconditional: engage_estop() only fires on_lease_change if a teleop
                # holder existed, but e-stop must stop autonomous motion too (e.g.
                # robot_ai driving in 'explore' mode with nobody on the joystick).
                _apply_mode('idle')

        # TeleopService doesn't know about WebSockets or the mode arbiter; wire its
        # state-change callbacks to the manager's broadcasts plus the mode push above,
        # so all clients see lease/e-stop changes and /robot/mode reflects them too,
        # regardless of who/what triggered the change.
        teleop.on_lease_change = _on_lease_change
        teleop.on_estop_change = _on_estop_change

        app.state.settings = settings
        app.state.bridge = bridge
        app.state.telemetry = telemetry
        app.state.teleop = teleop
        app.state.camera = camera
        app.state.controls = controls
        app.state.launch_manager = launch_manager
        app.state.waypoints = waypoints
        app.state.ws_manager = ws_manager

        teleop_task = asyncio.create_task(teleop.run())

        async def _startup_launches():
            # Clean up anything orphaned by a previous (e.g. crashed) dashboard
            # process BEFORE this instance's own bookkeeping starts — otherwise its
            # status() misreports "not running" for a launch that's actually still
            # alive, and autostart_base would pile a second bringup on top of it.
            # Unconditional: this matters even with autostart_base off.
            await launch_manager.cleanup_stale()
            if settings.autostart_base:
                await launch_manager.start('base')

        # Fire after startup so a slow launch doesn't block the server binding.
        asyncio.create_task(_startup_launches())
        try:
            yield
        finally:
            teleop_task.cancel()
            await launch_manager.stop_all()  # don't leave base/SLAM/Nav2 orphaned on dashboard restart
            bridge.stop()

    return lifespan


# FastAPI dependencies -------------------------------------------------------
def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_telemetry(request: Request) -> TelemetryService:
    return request.app.state.telemetry


def get_bridge(request: Request) -> RosBridge:
    return request.app.state.bridge


def get_teleop(request: Request) -> TeleopService:
    return request.app.state.teleop


def get_camera(request: Request) -> CameraService:
    return request.app.state.camera


def get_controls(request: Request) -> ControlsService:
    return request.app.state.controls


def get_launch_manager(request: Request) -> LaunchManager:
    return request.app.state.launch_manager


def get_waypoints(request: Request) -> WaypointStore:
    return request.app.state.waypoints
