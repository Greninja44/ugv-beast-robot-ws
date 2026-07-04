"""Camera service: re-mux OAK-D CompressedImage (already JPEG) into MJPEG.

Zero re-encode cost — depthai_ros_driver publishes JPEG bytes on the compressed
topic, so this just wraps each frame in a multipart boundary (docs/DASHBOARD_DESIGN.md
§7's "MJPEG v1" decision). The ROS subscription is lazy: acquired for the lifetime
of one HTTP streaming response, released when the client disconnects — mirrors the
WS channel lazy-subscribe pattern in ros/bridge.py.
"""
from __future__ import annotations

import asyncio

from ..core.config import Settings
from ..ros.bridge import RosBridge

BOUNDARY = b'dashboardframe'


class CameraService:
    def __init__(self, settings: Settings, bridge: RosBridge):
        self.s = settings
        self.bridge = bridge

    async def mjpeg_stream(self):
        """Async generator of multipart/x-mixed-replace chunks. Caller is
        responsible for acquiring/releasing the 'camera' channel around this."""
        period = 1.0 / self.s.camera_stream_fps
        last_stamp = -1.0
        while True:
            await asyncio.sleep(period)
            jpeg, stamp = self.bridge.latest_jpeg()
            if jpeg is None or stamp == last_stamp:
                continue  # no new frame since last tick — don't resend a stale one
            last_stamp = stamp
            yield (
                b'--' + BOUNDARY + b'\r\n'
                b'Content-Type: image/jpeg\r\n'
                b'Content-Length: ' + str(len(jpeg)).encode() + b'\r\n\r\n'
                + jpeg + b'\r\n'
            )

    def snapshot(self) -> bytes | None:
        jpeg, _ = self.bridge.latest_jpeg()
        return jpeg
