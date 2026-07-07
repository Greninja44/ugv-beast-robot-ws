"""WebSocket connection manager.

One pump task per channel runs ONLY while that channel has subscribers; it samples the
bridge's latest-wins buffer at the channel's configured rate and fans out to clients.
Slow clients get frames dropped (bounded send queues), never block the pump.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
import uuid

from fastapi import WebSocket

from ..core.config import Settings
from ..ros.bridge import RosBridge
from ..services.telemetry import TelemetryService
from ..services.teleop import TeleopService
from . import protocol


class Client:
    def __init__(self, ws: WebSocket, authenticated: bool):
        self.ws = ws
        self.id = uuid.uuid4().hex[:8]
        self.authenticated = authenticated
        self.channels: set[str] = set()
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=16)

    def push(self, message: dict) -> None:
        """Enqueue latest-wins: on overflow drop the oldest, keep the stream fresh."""
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait(message)


class WsManager:
    def __init__(self, settings: Settings, bridge: RosBridge, telemetry: TelemetryService,
                 teleop: TeleopService):
        self.s = settings
        self.bridge = bridge
        self.telemetry = telemetry
        self.teleop = teleop
        self.clients: dict[str, Client] = {}
        self._pumps: dict[str, asyncio.Task] = {}
        self._rates = {
            'telemetry': settings.rate_telemetry,
            'odom': settings.rate_odom,
            'imu': settings.rate_imu,
            'scan': settings.rate_scan,
            'tf': settings.rate_tf,
            'log': settings.rate_log,
            'nav': settings.rate_nav,
            'mode': settings.rate_mode,
            'percepts': settings.rate_percepts,
            'skill': settings.rate_nav,  # same cadence as nav; both are goal-status polls
        }

    # ---- client lifecycle --------------------------------------------------
    async def connect(self, ws: WebSocket, authenticated: bool) -> Client:
        await ws.accept()
        client = Client(ws, authenticated)
        self.clients[client.id] = client
        await ws.send_json({
            'op': 'hello', 'id': client.id, 'channels': list(protocol.CHANNELS),
            'authenticated': authenticated,
        })
        # Sync current safety state immediately, don't wait for the next change.
        await ws.send_json(protocol.lease(self.teleop.state.holder))
        await ws.send_json(protocol.estop(self.teleop.state.estop))
        return client

    def disconnect(self, client: Client) -> None:
        for ch in list(client.channels):
            self._unsubscribe(client, ch)
        self.teleop.release(client.id)  # drop the lease if this client held it
        self.clients.pop(client.id, None)

    # ---- broadcasts: called back from TeleopService on state changes ----------
    def broadcast_lease(self, holder: str | None) -> None:
        frame = protocol.lease(holder)
        for c in self.clients.values():
            c.push(frame)

    def broadcast_estop(self, active: bool) -> None:
        frame = protocol.estop(active)
        for c in self.clients.values():
            c.push(frame)

    # ---- channel subscription ------------------------------------------------
    def _subscribe(self, client: Client, channel: str) -> None:
        if channel not in protocol.CHANNELS or channel in client.channels:
            return
        client.channels.add(channel)
        self.bridge.acquire(channel)
        if channel not in self._pumps and channel in self._rates:
            self._pumps[channel] = asyncio.create_task(self._pump(channel))

    def _unsubscribe(self, client: Client, channel: str) -> None:
        if channel not in client.channels:
            return
        client.channels.discard(channel)
        self.bridge.release(channel)
        if not any(channel in c.channels for c in self.clients.values()):
            task = self._pumps.pop(channel, None)
            if task:
                task.cancel()

    # ---- pumps ---------------------------------------------------------------
    async def _pump(self, channel: str) -> None:
        period = 1.0 / self._rates[channel]
        last_stamp = -1.0
        while True:
            await asyncio.sleep(period)
            if channel == 'telemetry':
                data, stamp = self.telemetry.snapshot(), time.monotonic()
            elif channel == 'tf':
                data, stamp = self.bridge.tf_summary(), time.monotonic()
            elif channel == 'nav':
                data, stamp = self.bridge.nav_state.get()
                if data is None or stamp == last_stamp:
                    continue
                last_stamp = stamp
            elif channel == 'skill':
                data, stamp = self.bridge.skill_state.get()
                if data is None or stamp == last_stamp:
                    continue
                last_stamp = stamp
            elif channel == 'log':
                # A stream, not a single latest value — drain everything that
                # arrived since the last tick and send it as one batch.
                entries = self.bridge.log_buffer.drain()
                if not entries:
                    continue
                data, stamp = entries, time.monotonic()
            elif channel == 'percepts':
                entries = self.bridge.percept_buffer.drain()
                if not entries:
                    continue
                data, stamp = entries, time.monotonic()
            else:
                data, stamp = self.bridge.buffers[channel].get()
                if data is None or stamp == last_stamp:
                    continue  # nothing new from ROS — send nothing
                last_stamp = stamp
            frame = protocol.msg(channel, data, round(time.time(), 3))
            for c in self.clients.values():
                if channel in c.channels:
                    c.push(frame)

    # ---- per-client I/O loops (run from the route handler) --------------------
    async def sender(self, client: Client) -> None:
        while True:
            await client.ws.send_json(await client.queue.get())

    async def handle_message(self, client: Client, raw: dict) -> None:
        try:
            m = protocol.ClientMsg(**raw)
        except Exception:
            client.push(protocol.err('BAD_MSG', 'unparseable message'))
            return

        if m.op in protocol.CONTROL_OPS and not client.authenticated:
            client.push(protocol.err('UNAUTHORIZED', 'present a valid token to control the robot'))
            return

        if m.op == 'sub' and m.ch:
            self._subscribe(client, m.ch)
        elif m.op == 'unsub' and m.ch:
            self._unsubscribe(client, m.ch)
        elif m.op == 'ping':
            client.push({'op': 'pong', 't': m.t})
        elif m.op == 'teleop':
            code = self.teleop.on_teleop(client.id, m.lin, m.ang, m.deadman)
            if code:
                client.push(protocol.err(code))
        elif m.op == 'estop':
            self.teleop.engage_estop()
        elif m.op == 'estop_release':
            self.teleop.release_estop()
        elif m.op == 'release_control':
            self.teleop.release(client.id)
        elif m.op == 'set_mode' and m.mode:
            # bridge.set_mode_blocking briefly blocks on a ROS service call —
            # to_thread keeps this coroutine (and the event loop) from stalling,
            # same reasoning as core/lifespan.py's _apply_mode.
            ok, detail = await asyncio.to_thread(self.bridge.set_mode_blocking, m.mode)
            if not ok:
                client.push(protocol.err('SET_MODE_FAILED', detail))
        elif m.op == 'run_skill' and m.skill:
            # send_skill_goal can block briefly too (wait_for_server) — same reasoning.
            await asyncio.to_thread(self.bridge.send_skill_goal, m.skill, m.args)
        elif m.op == 'cancel_skill':
            self.bridge.cancel_skill_goal()
        else:
            client.push(protocol.err('UNSUPPORTED_OP', m.op))
