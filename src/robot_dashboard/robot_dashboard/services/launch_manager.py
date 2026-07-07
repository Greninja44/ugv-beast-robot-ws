"""Allowlisted launch manager: runs exactly the vendor launch files below, by
name, as subprocesses — never arbitrary commands. This is what backs the Robot
Controls page's Start/Stop buttons (docs/DASHBOARD_DESIGN.md §7's "Robot
Controls" table: launch-based actions have no vendor service/action to call, so
we manage the vendor's own `ros2 launch` invocations directly).

SERIAL EXCLUSION: the base bringup, the standalone SLAM launches, AND ugv_nav's
nav.launch.py (it bundles its own bringup_lidar too — verified by reading it, not
assumed) each start a ugv_bringup that opens the ESP32 UART — only ONE may hold it
at a time (a second gets "multiple access on port" and both corrupt). Actions that
grab the serial are tagged `serial=True`; starting one first stops any other serial
owner.

NAV2 MODE: ugv_nav's own nav.launch.py has no live-mapping mode — all three of its
use_localization options (amcl/emcl/cartographer) navigate against a PRE-SAVED map
file (verified by reading the vendor source: even 'cartographer' mode loads a
hardcoded map.pbstream via cartographer's localization.launch.py, not its
mapping.launch.py). So 'nav2' here is for navigating a room you've already mapped
(via the SLAM actions + Map-save below) — it needs a saved map to be useful.
Autonomous exploration of a NEW room needs 'explore' instead, which composes the
Waveshare SLAM launch with Nav2's own generic navigation_launch.py (see
explore_mapping.launch.py). Never run 'nav2' and 'explore' (or 'slam_cartographer')
together — all bundle their own bringup+cartographer and would collide exactly like
two 'base' instances would.

use_rviz is referenced via LaunchConfiguration('use_rviz') in nav.launch.py but
never given a DeclareLaunchArgument default (checked the vendor source directly) —
omitting it isn't a config choice, the launch hard-fails with "launch configuration
'use_rviz' does not exist" if it's not passed.

VENDOR SOURCING: these launch files live in the vendor overlay (ugv_ws). The
dashboard may be started without that overlay sourced, so each launch is run
through a bash shell that sources it first — otherwise `ros2 launch ugv_slam ...`
fails with "package not found". The overlay path is configurable (Settings).
"""
from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass, field


@dataclass(frozen=True)
class _Action:
    package: str
    launch_file: str
    serial: bool  # True if this launch opens the ESP32 UART (mutually exclusive)
    extra_args: tuple[str, ...] = field(default_factory=tuple)  # "key:=value" ros2 launch args


# name -> action. Extend here only — never accept a client-supplied command string.
ACTIONS: dict[str, _Action] = {
    # Base driver + lidar + sensors. The default serial owner (teleop/lights/telemetry).
    'base': _Action('ugv_bringup', 'bringup_lidar.launch.py', serial=True),
    # Standalone SLAM — bundles its own bringup. For building+saving a map to later
    # navigate against with 'nav2' below (amcl mode). Cartographer only: the vendor
    # overlay also ships gmapping.launch.py as an alternative algorithm for the same
    # job, but exposing both as separate buttons was confusing (two ways to do the
    # same thing with no clear reason to pick one) — Cartographer is strictly better
    # here anyway since it's also what the autonomous 'explore' flow below uses, so
    # a manually-built map and an auto-built one now come from the same algorithm.
    'slam_cartographer': _Action('ugv_slam', 'cartographer.launch.py', serial=True),
    # Nav2 against a PRE-SAVED map (vendor default: amcl + ugv_nav/maps/map.yaml).
    # use_rviz is unconditionally required (see nav.launch.py's own bringup_lidar
    # include) even though we never want rviz on the Pi.
    'nav2': _Action('ugv_nav', 'nav.launch.py', serial=True, extra_args=('use_rviz:=false',)),
    # Autonomous exploration: live SLAM + Nav2 together, no saved map needed — see
    # explore_mapping.launch.py's docstring for why this isn't just 'nav2' with a
    # different flag (ugv_nav's own launch has no live-mapping mode at all).
    'explore': _Action('robot_bringup', 'explore_mapping.launch.py', serial=True),
}


class LaunchManager:
    def __init__(self, vendor_setup: str | None = None):
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        self._vendor_setup = vendor_setup

    async def cleanup_stale(self) -> None:
        """Kill any vendor launch matching ACTIONS that's still running from a
        previous dashboard process — e.g. the dashboard crashed/restarted without
        going through stop_all(), leaving start_new_session=True subprocesses
        orphaned but alive. This node's own _procs dict starts empty on every
        construction, so without this it has no way to know they exist: is_running()
        would say False while the vendor stack is actually still there, and the next
        start() (including the autostart_base one) piles a second instance on top —
        exactly the "9 duplicate driver processes" failure this was written after.
        Call once, before anything else touches ACTIONS.
        Kills by PROCESS GROUP, not just the matched PID: `start()` launches each
        action via `start_new_session=True`, making the `ros2 launch` process a
        session/process-group leader, so pkill-by-pattern on just that one PID
        (the old approach) leaves every child it spawned — base_node, ugv_driver,
        rf2o_laser_odometry, joint_state_publisher, ldlidar_node, camera component
        containers — as surviving orphans still holding the serial/lidar/camera.
        The next start() then piles a whole second generation on top of those
        orphans rather than actually replacing them (found by hand in `ps aux`:
        three stacked generations of the vendor bringup fighting over one ESP32
        serial port). Killing the whole group takes every descendant down at once.
        """
        for action in ACTIONS.values():
            pattern = f'ros2 launch {action.package} {action.launch_file}'
            proc = await asyncio.create_subprocess_exec(
                'pgrep', '-f', pattern, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await proc.communicate()
            for pid_str in stdout.decode().split():
                try:
                    os.killpg(int(pid_str), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass

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
        action = ACTIONS[name]

        # Serial exclusion: stop every other running serial owner before opening the UART.
        if action.serial:
            for other, other_action in ACTIONS.items():
                if other != name and other_action.serial and self.is_running(other):
                    await self.stop(other)

        # Fallbacks only (setdefault): when the dashboard is started via `docker exec -d`
        # (see dev/start_pi_stack.sh) its env never went through the container's
        # .bashrc, which is where the vendor image actually sets these correctly for
        # this unit's real hardware (LDLIDAR_MODEL=ld19, not the ld06 some earlier
        # vendor SKUs use) — inheriting os.environ as-is if it's already there, rather
        # than clobbering a correct value with a stale hardcoded one.
        env = {**os.environ}
        env.setdefault('UGV_MODEL', 'ugv_beast')
        env.setdefault('LDLIDAR_MODEL', 'ld19')
        args = ' '.join(action.extra_args)
        launch_cmd = f'ros2 launch {action.package} {action.launch_file} {args}'.strip()
        if self._vendor_setup:
            # exec so SIGINT reaches ros2 launch (not a wrapping bash) for clean shutdown.
            cmd = ['bash', '-lc', f'source {self._vendor_setup} && exec {launch_cmd}']
        else:
            cmd = ['bash', '-lc', f'exec {launch_cmd}']
        self._procs[name] = await asyncio.create_subprocess_exec(
            *cmd,
            env=env, start_new_session=True,  # own process group -> can kill the whole launch tree
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )

    async def stop(self, name: str) -> None:
        proc = self._procs.get(name)
        if proc is None or proc.returncode is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGINT)  # ros2 launch handles SIGINT for clean shutdown
            await asyncio.wait_for(proc.wait(), timeout=8.0)
        except (ProcessLookupError, asyncio.TimeoutError):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self._procs.pop(name, None)

    async def stop_all(self) -> None:
        for name in list(self._procs):
            await self.stop(name)
