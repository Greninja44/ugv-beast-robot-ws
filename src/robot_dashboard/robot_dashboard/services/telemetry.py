"""Telemetry service: aggregates ROS buffers + system stats into the dashboard payload."""
from __future__ import annotations

import time

from ..core.config import Settings
from ..ros.bridge import RosBridge
from .system import SystemStats


class TelemetryService:
    def __init__(self, settings: Settings, bridge: RosBridge, system: SystemStats):
        self.s = settings
        self.bridge = bridge
        self.system = system

    def battery_pct(self, voltage: float | None) -> int | None:
        if voltage is None:
            return None
        lo, hi = self.s.battery_v_empty, self.s.battery_v_full
        return round(max(0.0, min(1.0, (voltage - lo) / (hi - lo))) * 100)

    def snapshot(self) -> dict:
        """The `telemetry` channel payload (2 Hz). Stale sensors (>3s) report null."""
        now = time.monotonic()
        voltage, v_ts = self.bridge.buffers['voltage'].get()
        odom, o_ts = self.bridge.buffers['odom'].get()
        v_fresh = voltage is not None and (now - v_ts) < 3.0
        o_fresh = odom is not None and (now - o_ts) < 3.0
        graph = self.bridge.graph_summary()
        sys_stats = self.system.snapshot()

        return {
            'ros': graph['connected'],
            'nodes': graph['nodes'],
            'topics': graph['topics'],
            'voltage': round(voltage, 2) if v_fresh else None,
            'pct': self.battery_pct(voltage) if v_fresh else None,
            'low_batt': bool(v_fresh and voltage <= self.s.battery_v_warn),
            'lin': odom['lin'] if o_fresh else None,
            'ang': odom['ang'] if o_fresh else None,
            'pose': {'x': odom['x'], 'y': odom['y'], 'yaw': odom['yaw']} if o_fresh else None,
            # 'map' when map->odom TF exists (Phase 5); 'odom_only' while only odometry runs.
            'loc': 'odom_only' if o_fresh else 'none',
            **sys_stats,
        }
