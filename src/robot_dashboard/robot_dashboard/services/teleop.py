"""Teleop service: the safety-critical path from a browser to /cmd_vel.

Enforces (see docs/DASHBOARD_DESIGN.md §3):
- Clamps every command to a runtime speed limit, itself bounded by the configured ceiling.
- Watchdog: if the lease holder goes silent for teleop_watchdog_s, zero /cmd_vel and
  release the lease so another client can take over.
- Single-driver lease: only the current holder's teleop packets move the robot; others
  get NOT_HOLDER. The lease is acquired by the first authenticated deadman=true packet.
- E-stop latch: while active, every tick publishes zero and all motion input is rejected
  until an explicit release.

One asyncio task (started in core/lifespan.py) ticks at teleop_publish_hz and is the
only thing that calls bridge.publish_cmd_vel — so there is exactly one place that can
put the robot in motion from this service, easy to audit.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable

from ..core.config import Settings
from ..ros.bridge import RosBridge


@dataclass
class _State:
    holder: str | None = None
    last_lin: float = 0.0
    last_ang: float = 0.0
    last_input_ts: float = 0.0
    estop: bool = False


class TeleopService:
    def __init__(self, settings: Settings, bridge: RosBridge):
        self.s = settings
        self.bridge = bridge
        self.state = _State()
        self.limit_linear = settings.max_linear
        self.limit_angular = settings.max_angular
        # Wired by lifespan.py to WsManager.broadcast_lease / broadcast_estop.
        self.on_lease_change: Callable[[str | None], None] | None = None
        self.on_estop_change: Callable[[bool], None] | None = None

    # ---- runtime speed limiter (Settings page / speed limiter sliders) --------
    def set_limits(self, linear: float | None, angular: float | None) -> None:
        if linear is not None:
            self.limit_linear = max(0.0, min(linear, self.s.max_linear))
        if angular is not None:
            self.limit_angular = max(0.0, min(angular, self.s.max_angular))

    def limits(self) -> dict:
        return {
            'max_linear': self.s.max_linear, 'max_angular': self.s.max_angular,
            'limit_linear': self.limit_linear, 'limit_angular': self.limit_angular,
        }

    # ---- teleop input (called from ws/manager.py on every 'teleop' message) ---
    def on_teleop(self, client_id: str, lin: float, ang: float, deadman: bool) -> str | None:
        """Apply one teleop packet. Returns an error code, or None on success."""
        if self.state.estop:
            return 'ESTOP_ACTIVE'
        if not deadman:
            if client_id == self.state.holder:
                self._zero_and_release()
            return None
        if self.state.holder is None:
            self._set_holder(client_id)
        elif self.state.holder != client_id:
            return 'NOT_HOLDER'

        self.state.last_lin = max(-self.limit_linear, min(self.limit_linear, lin))
        self.state.last_ang = max(-self.limit_angular, min(self.limit_angular, ang))
        self.state.last_input_ts = time.monotonic()
        self.bridge.publish_cmd_vel(self.state.last_lin, self.state.last_ang)
        return None

    def release(self, client_id: str) -> None:
        """Client disconnected, or explicitly released control."""
        if self.state.holder == client_id:
            self._zero_and_release()

    # ---- e-stop ----------------------------------------------------------------
    def engage_estop(self) -> None:
        self.state.estop = True
        self._zero_and_release()
        if self.on_estop_change:
            self.on_estop_change(True)

    def release_estop(self) -> None:
        self.state.estop = False
        if self.on_estop_change:
            self.on_estop_change(False)

    # ---- internal ----------------------------------------------------------------
    def _set_holder(self, client_id: str) -> None:
        self.state.holder = client_id
        self.state.last_input_ts = time.monotonic()
        if self.on_lease_change:
            self.on_lease_change(client_id)

    def _zero_and_release(self) -> None:
        had_holder = self.state.holder is not None
        self.state.holder = None
        self.state.last_lin = self.state.last_ang = 0.0
        self.bridge.publish_cmd_vel(0.0, 0.0)
        if had_holder and self.on_lease_change:
            self.on_lease_change(None)

    # ---- background loop: the ONLY place cmd_vel gets published from ------------
    async def run(self) -> None:
        period = 1.0 / self.s.teleop_publish_hz
        while True:
            await asyncio.sleep(period)
            if self.state.estop:
                self.bridge.publish_cmd_vel(0.0, 0.0)
                continue
            if self.state.holder is None:
                continue
            if time.monotonic() - self.state.last_input_ts > self.s.teleop_watchdog_s:
                self._zero_and_release()
            else:
                self.bridge.publish_cmd_vel(self.state.last_lin, self.state.last_ang)
