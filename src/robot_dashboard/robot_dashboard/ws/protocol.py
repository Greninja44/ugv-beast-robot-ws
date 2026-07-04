"""WebSocket message schema (docs/DASHBOARD_DESIGN.md §5).

Client → server ops: sub, unsub, ping, teleop, estop, estop_release, release_control
Server → client ops: msg, pong, err, hello, lease, estop
"""
from __future__ import annotations

from pydantic import BaseModel

# Channels available. Each maps to a bridge subscription + a rate.
CHANNELS = ('telemetry', 'odom', 'imu', 'scan', 'log', 'tf', 'nav')

# Ops that move the robot or change its safety state — require client.authenticated.
CONTROL_OPS = ('teleop', 'estop', 'estop_release', 'release_control')


class ClientMsg(BaseModel):
    op: str
    ch: str | None = None
    t: float | None = None       # ping echo payload
    lin: float = 0.0             # teleop: linear m/s (pre-clamp)
    ang: float = 0.0             # teleop: angular rad/s (pre-clamp)
    deadman: bool = False        # teleop: must be true while actively driving


def msg(channel: str, data: dict, ts: float) -> dict:
    return {'op': 'msg', 'ch': channel, 'data': data, 'ts': ts}


def err(code: str, detail: str = '') -> dict:
    return {'op': 'err', 'code': code, 'detail': detail}


def lease(holder: str | None) -> dict:
    return {'op': 'lease', 'holder': holder}


def estop(active: bool) -> dict:
    return {'op': 'estop', 'active': active}
