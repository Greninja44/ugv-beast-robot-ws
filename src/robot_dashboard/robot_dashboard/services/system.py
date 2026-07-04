"""Host system stats via psutil (no ROS topic exists for these).

In the privileged Pi container /proc and /sys/class/thermal reflect the host,
so CPU/mem/temp are the real Pi values.
"""
from __future__ import annotations

import glob

import psutil


class SystemStats:
    def __init__(self):
        psutil.cpu_percent(interval=None)  # prime the counter

    @staticmethod
    def _temperature() -> float | None:
        for zone in sorted(glob.glob('/sys/class/thermal/thermal_zone*/temp')):
            try:
                with open(zone) as f:
                    milli = int(f.read().strip())
                if milli > 1000:  # sanity: some zones report 0
                    return round(milli / 1000.0, 1)
            except (OSError, ValueError):
                continue
        return None

    def snapshot(self) -> dict:
        vm = psutil.virtual_memory()
        return {
            'cpu': round(psutil.cpu_percent(interval=None)),
            'mem': round(vm.percent),
            'temp': self._temperature(),
        }
