"""ROS bridge: ONE rclpy node in a dedicated executor thread.

Design (see docs/DASHBOARD_DESIGN.md §3):
- Subscriber callbacks (ROS thread) write into latest-wins buffers — no unbounded queues.
- The asyncio side polls buffers at each channel's configured rate (ws/manager.py).
- Subscriptions are LAZY: created when the first web client subscribes to a channel,
  destroyed when the last one leaves. Idle dashboard ≈ zero robot CPU.
- No other module touches rclpy. Services depend on this bridge only.
"""
from __future__ import annotations

import io
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import rclpy
import tf2_ros
from PIL import Image
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSPresetProfiles, QoSProfile, ReliabilityPolicy
from rclpy.time import Time

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Twist
from nav2_msgs.action import NavigateToPose
from nav2_msgs.srv import SaveMap
from nav_msgs.msg import OccupancyGrid, Odometry
from rcl_interfaces.msg import Log
from robot_interfaces.action import RunSkill
from robot_interfaces.msg import Percept
from robot_interfaces.srv import SetMode
from sensor_msgs.msg import CompressedImage, Imu, LaserScan
from std_msgs.msg import Float32, Float32MultiArray, String

from ..core.config import Settings

SENSOR_QOS = QoSPresetProfiles.SENSOR_DATA.value
# /map publishers (Nav2 map_server, SLAM toolboxes) use RELIABLE+TRANSIENT_LOCAL
# so late subscribers still get the last map — matching this is required, a
# VOLATILE subscriber against a TRANSIENT_LOCAL publisher silently gets nothing.
MAP_QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                      durability=DurabilityPolicy.TRANSIENT_LOCAL)
# robot_skills.mode_server publishes /robot/mode the same way — must match or a
# VOLATILE subscriber here gets nothing (same pitfall as MAP_QOS above).
MODE_QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL)

# Frame pairs whose health/age is reported on the 'tf' channel (see docs/TF_TREE.md).
# 'map'->'odom' only exists once SLAM/AMCL is running — its absence is expected, not an error.
TF_PAIRS = (
    ('map', 'odom'),
    ('odom', 'base_footprint'),
    ('base_footprint', 'base_link'),
    ('base_link', 'base_lidar_link'),
    ('base_link', 'base_imu_link'),
)


def quat_to_yaw(w: float, x: float, y: float, z: float) -> float:
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


@dataclass
class LatestBuffer:
    """Thread-safe latest-wins slot."""
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _data: Any = None
    _stamp: float = 0.0

    def put(self, data: Any) -> None:
        with self._lock:
            self._data = data
            self._stamp = time.monotonic()

    def get(self) -> tuple[Any, float]:
        with self._lock:
            return self._data, self._stamp


class LogBuffer:
    """Thread-safe bounded queue of log entries. Unlike LatestBuffer (one value,
    overwritten), logs are a stream — every entry between polls matters, so the
    asyncio-side pump (ws/manager.py) drains all of them each tick rather than
    just reading the newest. Kept on the same safe pattern as everything else:
    the ROS thread only ever touches this via a plain lock, never asyncio APIs."""

    def __init__(self, maxlen: int = 500):
        self._lock = threading.Lock()
        self._entries: deque[dict] = deque(maxlen=maxlen)

    def push(self, entry: dict) -> None:
        with self._lock:
            self._entries.append(entry)

    def drain(self) -> list[dict]:
        with self._lock:
            out = list(self._entries)
            self._entries.clear()
            return out


class RosBridge:
    """Owns the rclpy node + executor thread and all ROS I/O."""

    def __init__(self, settings: Settings):
        self.s = settings
        self.buffers: dict[str, LatestBuffer] = {
            k: LatestBuffer() for k in ('voltage', 'odom', 'imu', 'scan', 'camera', 'map', 'mode')
        }
        self.log_buffer = LogBuffer()
        # Percepts are a stream (possibly several detections per frame from
        # detector_node), not a single latest value — same drain-batch shape as logs.
        self.percept_buffer = LogBuffer()
        self._subs: dict[str, Any] = {}          # channel -> rclpy subscription
        self._refcounts: dict[str, int] = {}      # channel -> active web clients
        self._lock = threading.Lock()
        self._node: Node | None = None
        self._executor: SingleThreadedExecutor | None = None
        self._thread: threading.Thread | None = None
        self._cmd_vel_pub = None
        self._led_pub = None
        self._percept_pub = None
        self._save_map_client = None
        self._mode_client = None
        self._nav_client: ActionClient | None = None
        self._nav_goal_handle = None
        self.nav_state = LatestBuffer()
        self.nav_state.put({'status': 'idle', 'distance_remaining': None})
        self._skill_client: ActionClient | None = None
        self._skill_goal_handle = None
        self.skill_state = LatestBuffer()
        self.skill_state.put({'skill': None, 'status': 'idle', 'feedback': None,
                               'progress': None, 'result_detail': None})

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        rclpy.init()
        self._node = rclpy.create_node('dashboard_node')
        self._cmd_vel_pub = self._node.create_publisher(Twist, self.s.topic_cmd_vel, 10)
        self._led_pub = self._node.create_publisher(Float32MultiArray, self.s.topic_led_ctrl, 10)
        # Percepts ingested over HTTP (from the GPU detector on the dev box, which
        # can't reach the Pi over DDS) get republished onto the ROS /percepts topic
        # so they're first-class alongside on-Pi perception. The bridge's own lazy
        # /percepts subscription then feeds the dashboard overlay — single source of
        # truth, no separate HTTP-only path to keep in sync.
        self._percept_pub = self._node.create_publisher(Percept, self.s.topic_percepts, 10)
        self._save_map_client = self._node.create_client(SaveMap, '/map_saver/save_map')
        self._mode_client = self._node.create_client(SetMode, 'set_mode')
        self._nav_client = ActionClient(self._node, NavigateToPose, 'navigate_to_pose')
        self._skill_client = ActionClient(self._node, RunSkill, 'run_skill')
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)

        def _spin():
            try:
                self._executor.spin()
            except (ExternalShutdownException, RuntimeError):
                pass  # normal on Ctrl-C: rclpy's signal handler wins the race

        self._thread = threading.Thread(target=_spin, name='ros-executor', daemon=True)
        self._thread.start()

    def stop(self) -> None:
        try:
            if self._executor:
                self._executor.shutdown(timeout_sec=2.0)
            if self._node:
                self._node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass  # already torn down by rclpy's own signal handler

    @property
    def ok(self) -> bool:
        return self._node is not None and rclpy.ok()

    def graph_summary(self) -> dict:
        """Cheap ROS-health probe: counts of visible nodes/topics."""
        if not self.ok:
            return {'connected': False, 'nodes': 0, 'topics': 0}
        try:
            names = self._node.get_node_names()
            topics = self._node.get_topic_names_and_types()
            return {'connected': True, 'nodes': len(names), 'topics': len(topics)}
        except Exception:
            return {'connected': False, 'nodes': 0, 'topics': 0}

    # ---- lazy channel subscriptions ---------------------------------------
    def acquire(self, channel: str) -> None:
        """A web client subscribed to `channel`; create the ROS sub if first."""
        with self._lock:
            self._refcounts[channel] = self._refcounts.get(channel, 0) + 1
            if self._refcounts[channel] == 1 and channel not in self._subs:
                maker = getattr(self, f'_sub_{channel}', None)
                if maker:
                    self._subs[channel] = maker()

    def release(self, channel: str) -> None:
        """A web client left `channel`; drop the ROS sub if last."""
        with self._lock:
            n = self._refcounts.get(channel, 0) - 1
            self._refcounts[channel] = max(n, 0)
            if n <= 0 and channel in self._subs:
                handle = self._subs.pop(channel)
                if isinstance(handle, _TfHandle):
                    handle.destroy(self._node)
                elif isinstance(handle, _MultiSub):
                    for sub in handle.subs:
                        self._node.destroy_subscription(sub)
                else:
                    self._node.destroy_subscription(handle)

    # telemetry channel needs voltage+odom; map channels -> underlying subs
    def _sub_telemetry(self):
        subs = [
            self._node.create_subscription(
                Float32, self.s.topic_voltage,
                lambda m: self.buffers['voltage'].put(m.data), SENSOR_QOS),
            self._node.create_subscription(
                Odometry, self.s.topic_odom, self._on_odom, SENSOR_QOS),
        ]
        return _MultiSub(self._node, subs)

    def _sub_odom(self):
        return self._node.create_subscription(Odometry, self.s.topic_odom, self._on_odom, SENSOR_QOS)

    def _sub_imu(self):
        return self._node.create_subscription(Imu, self.s.topic_imu, self._on_imu, SENSOR_QOS)

    def _sub_scan(self):
        return self._node.create_subscription(LaserScan, self.s.topic_scan, self._on_scan, SENSOR_QOS)

    def _sub_log(self):
        return self._node.create_subscription(Log, self.s.topic_rosout, self._on_log, 50)

    def _sub_mode(self):
        return self._node.create_subscription(String, self.s.topic_mode, self._on_mode, MODE_QOS)

    def _sub_percepts(self):
        return self._node.create_subscription(
            Percept, self.s.topic_percepts, self._on_percept, SENSOR_QOS)

    def _sub_tf(self):
        return _TfHandle(self._node)

    def _sub_camera(self):
        # BEST_EFFORT/VOLATILE matches typical camera driver publisher QoS
        # (depthai_ros_driver); a strict RELIABLE subscriber QoS would fail to
        # match and silently receive nothing.
        return self._node.create_subscription(
            CompressedImage, self.s.topic_camera, self._on_camera, SENSOR_QOS)

    def latest_jpeg(self) -> tuple[bytes | None, float]:
        """Raw JPEG bytes as last received on the camera topic, and a monotonic
        stamp used to detect "is this a new frame" without re-encoding anything."""
        return self.buffers['camera'].get()

    def _sub_map(self):
        return self._node.create_subscription(OccupancyGrid, '/map', self._on_map, MAP_QOS)

    def map_snapshot(self) -> tuple[bytes | None, dict | None, float]:
        """(PNG bytes, metadata, stamp) — metadata lets the frontend convert a
        click on the image back into map-frame world coordinates."""
        data, stamp = self.buffers['map'].get()
        if data is None:
            return None, None, stamp
        return data['png'], data['meta'], stamp

    def tf_summary(self) -> dict:
        """Health/age of the key frame pairs (docs/TF_TREE.md). Only meaningful
        while the 'tf' channel is active (lazy — see acquire/release above)."""
        handle: _TfHandle | None = self._subs.get('tf')
        if handle is None:
            return {}
        now = self._node.get_clock().now()
        out = {}
        for parent, child in TF_PAIRS:
            key = f'{parent}->{child}'
            try:
                t = handle.buffer.lookup_transform(parent, child, Time())
                # Static transforms (/tf_static) publish with stamp=0 by convention —
                # they never expire, so "age" is meaningless; report None for those.
                if t.header.stamp.sec == 0 and t.header.stamp.nanosec == 0:
                    out[key] = {'ok': True, 'age': None}
                else:
                    age = (now - Time.from_msg(t.header.stamp)).nanoseconds / 1e9
                    out[key] = {'ok': True, 'age': round(max(age, 0.0), 2)}
            except Exception:
                out[key] = {'ok': False, 'age': None}
        return out

    # ---- message converters (run in ROS thread; keep them cheap) ----------
    def _on_odom(self, m: Odometry) -> None:
        q = m.pose.pose.orientation
        yaw = quat_to_yaw(q.w, q.x, q.y, q.z)
        self.buffers['odom'].put({
            'x': round(m.pose.pose.position.x, 3),
            'y': round(m.pose.pose.position.y, 3),
            'yaw': round(yaw, 4),
            'lin': round(m.twist.twist.linear.x, 3),
            'ang': round(m.twist.twist.angular.z, 3),
        })

    def _on_imu(self, m: Imu) -> None:
        q = m.orientation
        self.buffers['imu'].put({
            'ax': round(m.linear_acceleration.x, 3),
            'ay': round(m.linear_acceleration.y, 3),
            'az': round(m.linear_acceleration.z, 3),
            'gx': round(m.angular_velocity.x, 3),
            'gy': round(m.angular_velocity.y, 3),
            'gz': round(m.angular_velocity.z, 3),
            'qw': round(q.w, 4), 'qx': round(q.x, 4), 'qy': round(q.y, 4), 'qz': round(q.z, 4),
            'yaw': round(quat_to_yaw(q.w, q.x, q.y, q.z), 4),
        })

    def _on_scan(self, m: LaserScan) -> None:
        # Decimate ×2 and pack ranges as mm ints: ~75% smaller JSON.
        ranges = [
            0 if (r != r or r == float('inf')) else int(r * 1000)
            for r in m.ranges[::2]
        ]
        self.buffers['scan'].put({
            'amin': round(m.angle_min, 4),
            'ainc': round(m.angle_increment * 2, 6),
            'rmax': m.range_max,
            'ranges': ranges,
        })

    def _on_camera(self, m: CompressedImage) -> None:
        # m.data is already a JPEG byte stream (depthai_ros_driver's compressed
        # transport) — store as-is, no decode/re-encode needed for MJPEG re-mux.
        self.buffers['camera'].put(bytes(m.data))

    def _on_map(self, m: OccupancyGrid) -> None:
        # Standard occupancy-grid grayscale convention (matches map_server's
        # saved .pgm): free≈white(254), occupied≈black(0), unknown(-1)→205 gray.
        pixels = bytearray(m.info.width * m.info.height)
        for i, v in enumerate(m.data):
            pixels[i] = 205 if v < 0 else max(0, 255 - round(v * 2.55))
        img = Image.frombytes('L', (m.info.width, m.info.height), bytes(pixels))
        # Grid row 0 = smallest Y (world "down"); image row 0 is "top" on
        # screen. Flip so displaying it normally matches our other views'
        # "up = +Y" convention (LaserScanCanvas, OdomTrailCanvas).
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        self.buffers['map'].put({
            'png': buf.getvalue(),
            'meta': {
                'width': m.info.width, 'height': m.info.height,
                'resolution': m.info.resolution,
                'origin_x': m.info.origin.position.x,
                'origin_y': m.info.origin.position.y,
            },
        })

    def _on_log(self, m: Log) -> None:
        self.log_buffer.push({
            'lvl': {10: 'DEBUG', 20: 'INFO', 30: 'WARN', 40: 'ERROR', 50: 'FATAL'}.get(m.level, str(m.level)),
            'node': m.name, 'msg': m.msg, 'ts': m.stamp.sec,
        })

    def _on_mode(self, m: String) -> None:
        self.buffers['mode'].put(m.data)

    def _on_percept(self, m: Percept) -> None:
        # Stream, not latest-wins: detector_node/perception_node can each publish
        # several percepts per tick, and a scrolling feed wants all of them, same
        # reasoning as _on_log above.
        self.percept_buffer.push({
            'label': m.label,
            'confidence': round(m.confidence, 3),
            'bearing': round(m.bearing, 3),
            'frame_id': m.header.frame_id,
            'ts': m.header.stamp.sec + m.header.stamp.nanosec / 1e9,
            # normalised [0,1] image-plane box; all-zero means no box (e.g. LiDAR percept).
            'bbox': [round(m.bbox_x, 4), round(m.bbox_y, 4), round(m.bbox_w, 4), round(m.bbox_h, 4)],
        })

    # ---- publishers (Phase 2 wires teleop service to this) ----------------
    def publish_cmd_vel(self, linear: float, angular: float) -> None:
        t = Twist()
        t.linear.x = float(linear)
        t.angular.z = float(angular)
        self._cmd_vel_pub.publish(t)

    def publish_led(self, pwm_a: float, pwm_b: float) -> None:
        """[IO4, IO5] PWM 0-255 — matches ugv_rpi/base_ctrl.py's lights_ctrl
        (base light, head light), consumed by the vendor ugv_driver (T:132)."""
        m = Float32MultiArray()
        m.data = [float(pwm_a), float(pwm_b)]
        self._led_pub.publish(m)

    def publish_percept(self, label: str, confidence: float, bbox: list[float],
                         bearing: float = 0.0, frame_id: str = '3d_camera_link') -> None:
        """Republish an externally-sourced detection (the GPU detector, over HTTP) as
        a ROS Percept — see _percept_pub's note in start(). bbox is [x, y, w, h]
        normalised to [0,1]. Thread-safe: called from the asyncio route handler, but
        rclpy publishers are safe to call from any thread."""
        p = Percept()
        p.header.frame_id = frame_id
        p.header.stamp = self._node.get_clock().now().to_msg()
        p.label = label
        p.confidence = float(confidence)
        p.bearing = float(bearing)
        p.bbox_x, p.bbox_y, p.bbox_w, p.bbox_h = (float(v) for v in bbox)
        self._percept_pub.publish(p)

    def save_map_blocking(self, name: str, timeout: float = 8.0) -> tuple[bool, str]:
        """Calls Nav2's standard map_saver_server (SaveMap). BLOCKING — run this
        via `await asyncio.to_thread(...)` from a route handler, never directly
        in an async function, and never on the ROS executor thread itself.

        Thread-safety: call_async's done-callback fires on the ROS executor
        thread (already spinning this node); it only touches a threading.Event
        and a plain dict, never asyncio APIs, matching the rest of this file's
        rule about not crossing into asyncio from the ROS thread."""
        if not self._save_map_client.service_is_ready():
            if not self._save_map_client.wait_for_service(timeout_sec=2.0):
                return False, 'map_saver service not available (is SLAM/Nav2 running?)'

        req = SaveMap.Request()
        req.map_topic = 'map'
        req.map_url = name
        req.image_format = 'pgm'
        req.map_mode = 'trinary'
        req.free_thresh = 0.25
        req.occupied_thresh = 0.65

        done = threading.Event()
        outcome: dict[str, Any] = {}

        def _on_done(fut):
            try:
                outcome['result'] = fut.result()
            except Exception as e:
                outcome['error'] = str(e)
            done.set()

        future = self._save_map_client.call_async(req)
        future.add_done_callback(_on_done)
        if not done.wait(timeout):
            return False, 'map save timed out'
        if 'error' in outcome:
            return False, outcome['error']
        return bool(outcome['result'].result), ''

    def set_mode_blocking(self, mode: str, timeout: float = 3.0) -> tuple[bool, str]:
        """Calls robot_skills' mode arbiter (robot_interfaces/srv/SetMode) so the
        dashboard's own authority (teleop lease, e-stop) is reflected on /robot/mode —
        this is what makes autonomous nodes (nav_bridge, skill_server) stand down the
        instant a human takes the joystick, and stay down when they let go.

        BLOCKING — same rule as save_map_blocking: run via `await
        asyncio.to_thread(...)`, never directly in an async function.

        If mode_server isn't running (e.g. a WSL-only dev setup with nothing launched
        on the Pi yet), this fails soft: teleop/e-stop still work locally, there's just
        no autonomous stack around to arbitrate with yet."""
        if not self._mode_client.service_is_ready():
            if not self._mode_client.wait_for_service(timeout_sec=1.0):
                return False, 'mode_server not available (is robot_skills running?)'

        req = SetMode.Request()
        req.mode = mode

        done = threading.Event()
        outcome: dict[str, Any] = {}

        def _on_done(fut):
            try:
                outcome['result'] = fut.result()
            except Exception as e:
                outcome['error'] = str(e)
            done.set()

        future = self._mode_client.call_async(req)
        future.add_done_callback(_on_done)
        if not done.wait(timeout):
            return False, 'set_mode call timed out'
        if 'error' in outcome:
            return False, outcome['error']
        resp = outcome['result']
        return bool(resp.success), resp.message

    # ---- Nav2 navigate_to_pose action ------------------------------------------
    # All callbacks below fire on the ROS executor thread (rclpy's normal
    # behaviour for action clients) — they only ever touch nav_state's lock,
    # same rule as everywhere else in this file: never call asyncio APIs here.
    def send_nav_goal(self, x: float, y: float, yaw: float, frame: str = 'map') -> None:
        if not self._nav_client.wait_for_server(timeout_sec=1.0):
            self.nav_state.put({'status': 'error', 'distance_remaining': None,
                                 'detail': 'navigate_to_pose action server not available (is Nav2 running?)'})
            return

        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = frame
        goal.pose.header.stamp = self._node.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)

        self.nav_state.put({'status': 'navigating', 'distance_remaining': None})
        send_future = self._nav_client.send_goal_async(goal, feedback_callback=self._on_nav_feedback)
        send_future.add_done_callback(self._on_nav_goal_response)

    def cancel_nav_goal(self) -> None:
        if self._nav_goal_handle is not None:
            self._nav_goal_handle.cancel_goal_async()

    def _on_nav_goal_response(self, future) -> None:
        handle = future.result()
        if not handle.accepted:
            self.nav_state.put({'status': 'rejected', 'distance_remaining': None})
            return
        self._nav_goal_handle = handle
        result_future = handle.get_result_async()
        result_future.add_done_callback(self._on_nav_result)

    def _on_nav_feedback(self, feedback_msg) -> None:
        fb = feedback_msg.feedback
        self.nav_state.put({'status': 'navigating', 'distance_remaining': round(fb.distance_remaining, 3)})

    def _on_nav_result(self, future) -> None:
        status = future.result().status
        label = {
            GoalStatus.STATUS_SUCCEEDED: 'succeeded',
            GoalStatus.STATUS_CANCELED: 'canceled',
            GoalStatus.STATUS_ABORTED: 'aborted',
        }.get(status, 'unknown')
        self.nav_state.put({'status': label, 'distance_remaining': 0.0 if label == 'succeeded' else None})
        self._nav_goal_handle = None

    # ---- robot_skills RunSkill action -------------------------------------------
    # Same shape as the nav goal section above: callbacks fire on the ROS executor
    # thread and only ever touch skill_state's lock.
    def send_skill_goal(self, skill: str, args: list[str]) -> None:
        if not self._skill_client.wait_for_server(timeout_sec=1.0):
            self.skill_state.put({'skill': skill, 'status': 'error', 'feedback': None,
                                   'progress': None,
                                   'result_detail': 'run_skill action server not available '
                                                     '(is robot_skills running?)'})
            return

        goal = RunSkill.Goal()
        goal.skill = skill
        goal.args = args

        self.skill_state.put({'skill': skill, 'status': 'running', 'feedback': None,
                               'progress': None, 'result_detail': None})
        send_future = self._skill_client.send_goal_async(goal, feedback_callback=self._on_skill_feedback)
        send_future.add_done_callback(self._on_skill_goal_response)

    def cancel_skill_goal(self) -> None:
        if self._skill_goal_handle is not None:
            self._skill_goal_handle.cancel_goal_async()

    def _on_skill_goal_response(self, future) -> None:
        handle = future.result()
        if not handle.accepted:
            prev, _ = self.skill_state.get()
            skill = prev['skill'] if prev else None
            self.skill_state.put({'skill': skill, 'status': 'rejected', 'feedback': None,
                                   'progress': None, 'result_detail': 'goal rejected'})
            return
        self._skill_goal_handle = handle
        result_future = handle.get_result_async()
        result_future.add_done_callback(self._on_skill_result)

    def _on_skill_feedback(self, feedback_msg) -> None:
        fb = feedback_msg.feedback
        prev, _ = self.skill_state.get()
        skill = prev['skill'] if prev else None
        self.skill_state.put({'skill': skill, 'status': 'running', 'feedback': fb.status,
                               'progress': round(fb.progress, 3), 'result_detail': None})

    def _on_skill_result(self, future) -> None:
        status = future.result().status
        result = future.result().result
        label = {
            GoalStatus.STATUS_SUCCEEDED: 'succeeded',
            GoalStatus.STATUS_CANCELED: 'canceled',
            GoalStatus.STATUS_ABORTED: 'aborted',
        }.get(status, 'unknown')
        prev, _ = self.skill_state.get()
        skill = prev['skill'] if prev else None
        self.skill_state.put({'skill': skill, 'status': label, 'feedback': None,
                               'progress': 1.0 if label == 'succeeded' else None,
                               'result_detail': result.result_detail})
        self._skill_goal_handle = None


class _MultiSub:
    """Groups several subscriptions behind one handle so release() drops them all."""

    def __init__(self, node: Node, subs: list):
        self.subs = subs


class _TfHandle:
    """Lazy tf2 buffer + listener. TransformListener subscribes /tf and /tf_static
    itself; we destroy those two subscriptions on release() (via .destroy()) so an
    idle dashboard doesn't keep a standing TF subscription — same lazy rule as
    every other channel."""

    def __init__(self, node: Node):
        self.buffer = tf2_ros.Buffer()
        self.listener = tf2_ros.TransformListener(self.buffer, node, spin_thread=False)

    def destroy(self, node: Node) -> None:
        node.destroy_subscription(self.listener.tf_sub)
        node.destroy_subscription(self.listener.tf_static_sub)
