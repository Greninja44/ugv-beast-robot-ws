"""Allowlisted launch manager: runs exactly the vendor launch files below, by
name, as subprocesses — never arbitrary commands. This is what backs the Robot
Controls page's Start/Stop SLAM buttons (docs/DASHBOARD_DESIGN.md §7's "Robot
Controls" table: launch-based actions have no vendor service/action to call, so
we manage the vendor's own `ros2 launch` invocations directly).

Subprocesses inherit this process's environment, which already has ROS sourced
(the dashboard itself only runs after `source .../setup.bash`), so no
re-sourcing is needed here.
"""
from __future__ import annotations

import asyncio
import os
import signal

# name -> (package, launch file). Extend here only — never accept a client-
# supplied command string.
ACTIONS: dict[str, tuple[str, str]] = {
    'slam_cartographer': ('ugv_slam', 'cartographer.launch.py'),
    'slam_gmapping': ('ugv_slam', 'gmapping.launch.py'),
    'nav2': ('ugv_nav', 'nav.launch.py'),
}


class LaunchManager:
    def __init__(self):
        self._procs: dict[str, asyncio.subprocess.Process] = {}

    def status(self) -> dict[str, bool]:
        return {name: self.is_running(name) for name in ACTIONS}

    def is_running(self, name: str) -> bool:
        proc = self._procs.get(name)
        return proc is not None and proc.returncode is None

    async def start(self, name: str) -> None:
        if name not in ACTIONS:
            raise ValueError(f'unknown action: {name}')
        if self.is_running(name):
            return
        pkg, launch_file = ACTIONS[name]
        env = {**os.environ, 'UGV_MODEL': 'ugv_beast', 'LDLIDAR_MODEL': 'ld06'}
        self._procs[name] = await asyncio.create_subprocess_exec(
            'ros2', 'launch', pkg, launch_file,
            env=env, start_new_session=True,  # own process group -> can kill the whole launch tree
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )

    async def stop(self, name: str) -> None:
        proc = self._procs.get(name)
        if proc is None or proc.returncode is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGINT)  # ros2 launch handles SIGINT for clean shutdown
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except (ProcessLookupError, asyncio.TimeoutError):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self._procs.pop(name, None)

    async def stop_all(self) -> None:
        for name in list(self._procs):
            await self.stop(name)
