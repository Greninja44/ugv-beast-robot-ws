#!/usr/bin/env python3
"""robot_skills — RunSkill action server (typed replacement for vendor 'behavior').

Registers named skills and executes them, gated by /robot/mode: skills that command
motion only run when the mode grants autonomous authority (robot_skills.mode_server
.AUTONOMOUS_MODES) — this is what stops robot_skills from driving while a human has the
dashboard joystick (mode='teleop'). 'stop' is exempt: commanding zero velocity is always
safe, so it works as a safety override in any mode.

Skills:
- stop         — publish zero /cmd_vel. Always allowed, any mode.
- demo         — logs fake progress. Stand-in motion skill used to exercise the mode gate.
- goto         — thin ActionClient wrapping robot_navigation's NavigateTo action (never
                 talks to Nav2 directly — that stays isolated to robot_navigation).
- rotate360    — direct /cmd_vel angular spin, one full turn in place.
- look_around  — like rotate360 but pauses at 8 headings; placeholder for Stage C, where
                 each pause becomes a percept capture once the camera pipeline exists.
- explore_room — launches the Waveshare-vendored explore_lite (frontier exploration;
                 not reimplemented here — see _skill_explore_room's docstring for why
                 and how completion is detected without a dedicated ROS signal).

Only one skill goal runs at a time (goal_callback rejects a second while one's active),
and cancellation is real (cancel_callback used to default-reject everything — see the
Phase 5 notes). goto's cancellation propagates into the underlying NavigateTo goal, the
same pattern nav_bridge uses one layer down for Nav2.

SAFETY: real motion skills must be tested with the robot wheels-up or in a clear area.
"""
import math
import os
import signal
import subprocess
import time

import rclpy
import tf2_ros
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from rclpy.task import Future
from rclpy.time import Time
from geometry_msgs.msg import PoseStamped, Twist
from rcl_interfaces.msg import Log
from std_msgs.msg import Bool, String
from visualization_msgs.msg import MarkerArray
from robot_interfaces.action import NavigateTo, RunSkill
from robot_skills.mode_server import AUTONOMOUS_MODES

MODE_QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL)

ROTATE_ANGULAR_SPEED = 0.4  # rad/s — gentle, deliberate spin
ROTATE_TICK = 0.1           # s — cmd_vel republish / cancel-check granularity

# explore_lite (ugv_else/explore_lite, vendored, built on the Pi) has no ROS topic or
# service signalling "exploration complete" — verified against its source
# (explore.cpp): it only RCLCPP_WARNs "No frontiers found, stopping." or "All frontiers
# traversed/tried out, stopping." right before stopping itself. Both share this
# substring and there are no other call sites that stop it, so matching on it via
# /rosout is a source-verified deterministic signal, not a heuristic.
EXPLORE_DONE_MARKER = 'stopping'
EXPLORE_MAX_DURATION_S = 600.0
EXPLORE_STOP_GRACE_S = 3.0  # time to let explore_lite exit after SIGINT before SIGKILL
# Cartographer takes ~20-30s to stabilize and publish its first map->odom transform
# after starting (confirmed live) — explore_lite must not start before then (see
# _skill_explore_room). This bounds how long we wait before giving up.
EXPLORE_TF_WAIT_S = 60.0
# explore_lite's "No frontiers found, stopping." WARN (see EXPLORE_DONE_MARKER above)
# turned out to never actually reach /rosout: verified live that it's logged through
# a manually-created rclcpp::get_logger("ExploreNode") object, not the node's own
# this->get_logger() — and only a node's own logger is wired to /rosout by default. So
# EXPLORE_DONE_MARKER is kept as a best-effort primary check (works if a future
# explore_lite release fixes this), but the real signal is /explore/frontiers going
# silent: visualizeFrontiers() only publishes when frontiers.size() > 0, once per
# makePlan() cycle (~planner_frequency, 0.15 Hz = ~6.7s) — so sustained silence well
# past that period means the internal timer was canceled (frontiers.empty() was true),
# not just a lull between goals.
EXPLORE_FRONTIER_SILENCE_S = 20.0


class SkillServer(Node):
    def __init__(self):
        super().__init__('skill_server')
        # explore_lite lives in the Waveshare overlay, not this workspace — sourcing
        # only /opt/ros/humble + robot_ws's own install (this node's own environment)
        # leaves `ros2 launch explore_lite ...` unable to find the package. Empty
        # string disables sourcing (e.g. if the overlay is already on this process's
        # own environment some other way).
        self.declare_parameter('vendor_setup', '/home/ws/ugv_ws/install/setup.bash')
        self._vendor_setup = self.get_parameter('vendor_setup').value
        self._mode = 'idle'
        self._active_skill: str | None = None  # name of the in-flight skill, if any
        self._active_nav_goal = None  # NavigateTo ClientGoalHandle, only set during goto

        self.create_subscription(String, '/robot/mode', self._on_mode, MODE_QOS)
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self._explore_resume_pub = self.create_publisher(Bool, 'explore/resume', 10)
        # explore_lite's own costmap client checks for the map->base_link transform
        # with a hardcoded ~100ms timeout in ITS constructor, before anything else
        # runs — if cartographer hasn't published its first transform yet (takes
        # ~20-30s to stabilize after SLAM starts, confirmed live), that check loses
        # the race and explore_lite ends up in a silently-degraded state (no
        # frontiers ever found, no error, just does nothing forever). So
        # _skill_explore_room waits for this transform itself before ever starting
        # the explore_lite subprocess, rather than assuming 'explore' mode being
        # active means the SLAM+Nav2 foundation it depends on is already ready.
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)
        self._nav_client = ActionClient(self, NavigateTo, 'navigate_to')
        self._server = ActionServer(
            self, RunSkill, 'run_skill', self.execute,
            goal_callback=self._on_goal_request,
            cancel_callback=self._on_cancel_request)

        # skill name -> (handler, requires_motion_authority)
        self.skills = {
            'stop': (self._skill_stop, False),
            'demo': (self._skill_demo, True),
            'goto': (self._skill_goto, True),
            'rotate360': (self._skill_rotate360, True),
            'look_around': (self._skill_look_around, True),
            'explore_room': (self._skill_explore_room, True),
        }
        self.get_logger().info(f'robot_skills up; skills={list(self.skills)}')

    def _on_mode(self, msg: String):
        self._mode = msg.data

    def _on_goal_request(self, goal_request):
        # Marked busy here, at acceptance time, not inside execute() — execute() only
        # starts as a task scheduled *after* this returns ACCEPT, so checking there
        # would leave a window where a second goal could slip in as still-not-busy.
        if self._active_skill is not None:
            self.get_logger().warn(
                f"rejecting '{goal_request.skill}': '{self._active_skill}' is already in progress")
            return GoalResponse.REJECT
        self._active_skill = goal_request.skill
        return GoalResponse.ACCEPT

    def _on_cancel_request(self, goal_handle):
        if self._active_nav_goal is not None:
            self.get_logger().info('cancel requested; forwarding cancel to active NavigateTo goal')
            self._active_nav_goal.cancel_goal_async()
        return CancelResponse.ACCEPT

    def _sleep(self, seconds: float) -> Future:
        """Executor-cooperative sleep for async skill handlers. A plain time.sleep()
        would freeze the whole node; asyncio.sleep() wouldn't actually wake up — rclpy's
        coroutine driver only resumes on rclpy Futures, not real asyncio timers (same
        finding as robot_navigation.nav_bridge in Phase 3)."""
        fut = Future()

        def _fire():
            self.destroy_timer(timer)
            if not fut.done():
                fut.set_result(None)

        timer = self.create_timer(seconds, _fire)
        return fut

    async def _wait_for_transform(self, target: str, source: str, timeout_s: float) -> bool:
        """Poll (not a single blocking lookup) for a transform to become available,
        cooperating with the executor via _sleep — used so callers can start a
        downstream process (explore_lite) only once the transform it silently
        assumes already exists is actually real, instead of racing it."""
        elapsed = 0.0
        interval = 0.5
        while elapsed < timeout_s:
            if self._tf_buffer.can_transform(target, source, Time()):
                return True
            await self._sleep(interval)
            elapsed += interval
        return False

    async def execute(self, goal_handle):
        # _active_skill was already set to this goal's name by _on_goal_request at
        # acceptance time; always clear it here, however execute() exits, so a stuck
        # skill can never permanently wedge the single-in-flight guard.
        try:
            name = goal_handle.request.skill
            entry = self.skills.get(name)
            result = RunSkill.Result()
            if entry is None:
                self.get_logger().warn(f'unknown skill: {name}')
                goal_handle.abort()
                result.success = False
                result.result_detail = f'unknown skill: {name}'
                return result

            fn, requires_authority = entry
            if requires_authority and self._mode not in AUTONOMOUS_MODES:
                self.get_logger().warn(
                    f"rejecting '{name}': requires an autonomous mode {sorted(AUTONOMOUS_MODES)}, "
                    f"current mode is '{self._mode}'")
                goal_handle.abort()
                result.success = False
                result.result_detail = (
                    f"mode '{self._mode}' does not grant motion authority "
                    f"(need one of {sorted(AUTONOMOUS_MODES)})")
                return result

            args = dict(a.split('=', 1) for a in goal_handle.request.args if '=' in a)
            maybe_coro = fn(goal_handle, args)
            if hasattr(maybe_coro, '__await__'):
                success, detail = await maybe_coro
            else:
                success, detail = maybe_coro

            if success:
                goal_handle.succeed()
            elif goal_handle.is_cancel_requested:
                goal_handle.canceled()
            else:
                goal_handle.abort()
            result.success = success
            result.result_detail = detail
            return result
        finally:
            self._active_skill = None

    # ---- skills --------------------------------------------------------------
    def _skill_stop(self, goal_handle, args):
        self.cmd_pub.publish(Twist())  # zero velocity
        return True, 'commanded stop (zero /cmd_vel)'

    def _skill_demo(self, goal_handle, args):
        for i in range(3):
            fb = RunSkill.Feedback()
            fb.status = f'demo step {i + 1}/3'
            fb.progress = (i + 1) / 3.0
            goal_handle.publish_feedback(fb)
            time.sleep(0.3)
        return True, 'demo complete'

    async def _skill_goto(self, goal_handle, args):
        try:
            x = float(args['x'])
            y = float(args['y'])
        except (KeyError, ValueError):
            return False, "goto requires numeric 'x' and 'y' args"
        yaw = float(args.get('yaw', 0.0))
        frame = args.get('frame', 'map')

        if not self._nav_client.server_is_ready():
            return False, "robot_navigation's 'navigate_to' action not available"

        target = PoseStamped()
        target.header.frame_id = frame
        target.pose.position.x = x
        target.pose.position.y = y
        target.pose.orientation.z = math.sin(yaw / 2.0)
        target.pose.orientation.w = math.cos(yaw / 2.0)

        nav_goal = NavigateTo.Goal()
        nav_goal.target = target
        nav_goal.tolerance = 0.15

        initial_distance = {}

        def on_feedback(fb_msg):
            d = fb_msg.feedback.distance_remaining
            initial_distance.setdefault('value', d if d > 0 else 1.0)
            fb = RunSkill.Feedback()
            fb.status = f'distance remaining: {d:.2f} m'
            fb.progress = max(0.0, min(1.0, 1.0 - (d / initial_distance['value'])))
            goal_handle.publish_feedback(fb)

        nav_goal_handle = await self._nav_client.send_goal_async(nav_goal, feedback_callback=on_feedback)
        if not nav_goal_handle.accepted:
            return False, 'navigate_to goal rejected (wrong mode, or a nav goal already in progress)'

        self._active_nav_goal = nav_goal_handle
        nav_result = await nav_goal_handle.get_result_async()
        self._active_nav_goal = None

        success = bool(nav_result.result.success)
        return success, ('goto complete' if success else 'navigate_to did not succeed')

    async def _skill_rotate360(self, goal_handle, args):
        return await self._rotate(goal_handle, total_angle=2 * math.pi, pause_every=None)

    async def _skill_look_around(self, goal_handle, args):
        return await self._rotate(goal_handle, total_angle=2 * math.pi, pause_every=math.pi / 4,
                                   pause_s=1.0)

    async def _rotate(self, goal_handle, total_angle: float, pause_every: float | None,
                       pause_s: float = 1.0):
        duration = total_angle / ROTATE_ANGULAR_SPEED
        twist = Twist()
        twist.angular.z = ROTATE_ANGULAR_SPEED
        elapsed = 0.0
        next_pause = pause_every

        while elapsed < duration:
            if goal_handle.is_cancel_requested:
                self.cmd_pub.publish(Twist())
                return False, 'rotation canceled'
            if self._mode not in AUTONOMOUS_MODES:
                self.cmd_pub.publish(Twist())
                return False, f"mode changed to '{self._mode}' mid-rotation; stopped"

            angle_so_far = ROTATE_ANGULAR_SPEED * elapsed
            if pause_every is not None and next_pause is not None and angle_so_far >= next_pause:
                self.cmd_pub.publish(Twist())  # stop to "look" — Stage C: capture a percept here
                fb = RunSkill.Feedback()
                fb.status = f'paused at {math.degrees(angle_so_far):.0f} deg'
                fb.progress = min(1.0, elapsed / duration)
                goal_handle.publish_feedback(fb)
                await self._sleep(pause_s)
                elapsed += pause_s
                next_pause += pause_every
                continue

            self.cmd_pub.publish(twist)
            fb = RunSkill.Feedback()
            fb.status = f'rotating: {math.degrees(angle_so_far):.0f}/{math.degrees(total_angle):.0f} deg'
            fb.progress = min(1.0, elapsed / duration)
            goal_handle.publish_feedback(fb)
            await self._sleep(ROTATE_TICK)
            elapsed += ROTATE_TICK

        self.cmd_pub.publish(Twist())
        return True, 'rotation complete'

    async def _skill_explore_room(self, goal_handle, args):
        """Frontier exploration via the vendored explore_lite — not reimplemented here.

        explore_lite talks to Nav2 directly (its own internal ActionClient, action name
        'navigate_to_pose' — confirmed from its source), bypassing robot_navigation's
        mode-gated NavigateTo entirely. That means losing motion authority mid-exploration
        (mode leaving AUTONOMOUS_MODES) won't get caught by nav_bridge the way goto's
        cancellation does — this handler has to watch /robot/mode itself and stop
        explore_lite the same way a human would: publish False on explore/resume (its own
        graceful stop — cancels its active Nav2 goal, confirmed from source) before
        terminating the process.
        """
        max_duration = float(args.get('max_duration_s', EXPLORE_MAX_DURATION_S))

        fb = RunSkill.Feedback()
        fb.status = 'waiting for map->base_link transform (SLAM still stabilizing)...'
        fb.progress = 0.0
        goal_handle.publish_feedback(fb)
        if not await self._wait_for_transform('map', 'base_link', EXPLORE_TF_WAIT_S):
            return False, (f"'map'->'base_link' transform never became available after "
                            f"{EXPLORE_TF_WAIT_S:.0f}s — is SLAM (the 'explore' or "
                            f"'slam_cartographer' action) actually running?")

        # use_sim_time:=false is required, not optional: explore_lite's own launch
        # file defaults it to true (for Gazebo), and on real hardware nothing
        # publishes /clock — its ROS-time-based planning timer then silently never
        # fires (no error, no log, just never explores) since the clock never
        # advances. Verified live: /explore_node subscribed to /clock with zero
        # /cmd_vel or log output until this was set.
        launch_cmd = 'ros2 launch explore_lite explore.launch.py use_sim_time:=false'
        cmd = (['bash', '-lc', f'source {self._vendor_setup} && exec {launch_cmd}']
               if self._vendor_setup else ['bash', '-lc', f'exec {launch_cmd}'])
        try:
            # Was DEVNULL: made every "no frontiers" outcome undiagnosable — no way
            # to tell a genuinely empty room apart from explore_lite erroring out or
            # still starting up. A plain file, not PIPE: PIPE's fixed OS buffer fills
            # and deadlocks the child if nothing here drains it (this loop doesn't).
            # Fixed path, not per-goal: the single-flight guard means only one
            # explore_room run is ever active at a time, so the last run is enough.
            log_f = open('/tmp/explore_lite_last.log', 'wb')
            proc = subprocess.Popen(
                cmd, start_new_session=True,
                stdout=log_f, stderr=subprocess.STDOUT)
        except OSError as e:
            return False, f'failed to launch explore_lite: {e}'

        done_fut = Future()

        def on_rosout(msg: Log):
            if msg.name == 'explore_node' and EXPLORE_DONE_MARKER in msg.msg:
                if not done_fut.done():
                    done_fut.set_result(None)

        # started_at, not None, as the baseline: if frontiers.empty() on the very
        # first (immediate) makePlan() call, nothing is ever published at all, and
        # that silence-since-start must still trip the timeout below.
        last_frontier_time = self.get_clock().now()

        def on_frontiers(msg: MarkerArray):
            nonlocal last_frontier_time
            last_frontier_time = self.get_clock().now()

        rosout_sub = self.create_subscription(Log, '/rosout', on_rosout, 10)
        frontiers_sub = self.create_subscription(MarkerArray, 'explore/frontiers', on_frontiers, 10)
        try:
            elapsed = 0.0
            while elapsed < max_duration:
                if goal_handle.is_cancel_requested:
                    await self._stop_explore(proc)
                    return False, 'exploration canceled'
                if self._mode not in AUTONOMOUS_MODES:
                    await self._stop_explore(proc)
                    return False, f"mode changed to '{self._mode}' mid-exploration; stopped"
                if proc.poll() is not None:
                    return False, f'explore_lite exited unexpectedly (code {proc.returncode})'

                silence_s = (self.get_clock().now() - last_frontier_time).nanoseconds / 1e9
                if done_fut.done() or silence_s > EXPLORE_FRONTIER_SILENCE_S:
                    await self._stop_explore(proc)
                    fb = RunSkill.Feedback()
                    fb.status = 'no more frontiers'
                    fb.progress = 1.0
                    goal_handle.publish_feedback(fb)
                    return True, 'exploration complete: no frontiers remaining'

                fb = RunSkill.Feedback()
                fb.status = f'exploring... ({elapsed:.0f}s elapsed)'
                fb.progress = 0.0
                goal_handle.publish_feedback(fb)
                await self._sleep(1.0)
                elapsed += 1.0

            await self._stop_explore(proc)
            return False, f'exploration timed out after {max_duration:.0f}s'
        finally:
            self.destroy_subscription(rosout_sub)
            self.destroy_subscription(frontiers_sub)

    async def _stop_explore(self, proc: subprocess.Popen) -> None:
        self._explore_resume_pub.publish(Bool(data=False))
        await self._sleep(0.3)  # let the graceful Nav2-goal-cancel take effect
        await self._terminate_explore(proc)

    async def _terminate_explore(self, proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGINT)
        except ProcessLookupError:
            return
        ticks = int(EXPLORE_STOP_GRACE_S / 0.1)
        for _ in range(ticks):
            if proc.poll() is not None:
                return
            await self._sleep(0.1)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main(args=None):
    rclpy.init(args=args)
    node = SkillServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
