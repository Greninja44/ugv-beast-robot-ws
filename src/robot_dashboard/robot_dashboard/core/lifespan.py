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
        launch_manager = LaunchManager()
        waypoints = WaypointStore(settings.waypoints_file)
        ws_manager = WsManager(settings, bridge, telemetry, teleop)
        # TeleopService doesn't know about WebSockets; wire its state-change
        # callbacks to the manager's broadcast methods so all clients see
        # lease/e-stop changes regardless of who triggered them.
        teleop.on_lease_change = ws_manager.broadcast_lease
        teleop.on_estop_change = ws_manager.broadcast_estop

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
        try:
            yield
        finally:
            teleop_task.cancel()
            await launch_manager.stop_all()  # don't leave SLAM/Nav2 orphaned on dashboard restart
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
