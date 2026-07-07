#!/usr/bin/env python3
"""robot_perception — YOLO object/person detector (runs on WSL/RTX4050, not the Pi).

Subscribes to the OAK-D's compressed RGB stream (the same real topic as
perception_node's camera plumbing, /oak/rgb/image_raw/compressed) over the WSL<->Pi DDS
link, runs YOLO inference on a rate-limited timer, and publishes one
robot_interfaces/Percept per detection to the shared /percepts topic — the same topic
perception_node's LiDAR percept uses, so downstream consumers subscribe once regardless
of which node produced a given percept.

Deliberately WSL-side: real-time inference needs a GPU-class machine (docs/CAMERA.md:
"Heavy models can run on WSL... lightweight/low-latency detection on the Pi").
perception_node (LiDAR + camera diagnostics) stays on the Pi; this doesn't — same
package, because the project spec lists YOLO as a robot_perception responsibility
regardless of where it physically runs. That's a launch/deployment choice
(build_wsl.sh), not a package boundary.

HONESTY NOTE on geometry: YOLO alone gives a 2D image-plane bounding box, not a 3D
position — there is no depth fusion here (the OAK-D's depth/point-cloud output isn't
subscribed). So each Percept gets a `bearing` computed from the box's center pixel and a
configurable horizontal-FOV parameter (default 69 deg — OAK-D-Lite's published RGB
HFOV), but `position` is left at zero rather than fabricate a distance that was never
measured. Depth fusion is a natural follow-up once actually needed.

RUNTIME SETUP — this needs its own virtualenv, not a plain `pip install --user`:
`ultralytics` pulls in a modern NumPy (2.x) + its own OpenCV build. Installing that at
user/system level breaks every other node — system `cv2`/`matplotlib` here are compiled
against NumPy 1.x, and mixing that ABI with a shadowing NumPy 2.x segfaults/raises on
import (hit this directly: `perception_node`'s camera decode started silently failing
after a `--user` install). Fix: an isolated venv with `--system-site-packages` (so
`rclpy`/message packages stay visible) and *its own* copy of every compiled dependency:

    virtualenv --system-site-packages .venv-detector   # NOT `python3 -m venv` if
                                                        # python3-venv isn't installed
                                                        # and you have no sudo — plain
                                                        # `virtualenv` (pip --user
                                                        # installable) works without it
    .venv-detector/bin/pip install ultralytics
    .venv-detector/bin/pip install --ignore-installed matplotlib  # system matplotlib
        # leaks in via --system-site-packages and crashes the same way unless a
        # NumPy-2.x-compatible copy is forced into the venv specifically

Run it with the venv's interpreter directly (source ROS setup.bash first so
PYTHONPATH picks up the built robot_perception/robot_interfaces packages), not
`ros2 run` — the installed console-script's shebang is whatever Python built the
package, not whatever venv happens to be active:

    source /opt/ros/humble/setup.bash && source install/setup.bash
    .venv-detector/bin/python3 -m robot_perception.detector_node
"""
import math

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSPresetProfiles
from sensor_msgs.msg import CompressedImage
from robot_interfaces.msg import Percept

SENSOR_QOS = QoSPresetProfiles.SENSOR_DATA.value
FPS_LOG_PERIOD_S = 5.0


class DetectorNode(Node):
    def __init__(self):
        super().__init__('detector_node')
        self.declare_parameter('camera_topic', '/oak/rgb/image_raw/compressed')
        self.declare_parameter('camera_frame_id', '3d_camera_link')
        self.declare_parameter('detect_hz', 5.0)
        self.declare_parameter('confidence_threshold', 0.5)
        self.declare_parameter('model_path', 'yolov8n.pt')
        # OAK-D-Lite's published RGB sensor HFOV (Luxonis spec) — used only to turn a
        # detection's pixel position into a bearing. Not a measured value for this
        # specific unit; override via this parameter if yours differs.
        self.declare_parameter('camera_hfov_deg', 69.0)

        camera_topic = self.get_parameter('camera_topic').value
        self.frame_id = self.get_parameter('camera_frame_id').value
        detect_hz = self.get_parameter('detect_hz').value
        self.confidence_threshold = self.get_parameter('confidence_threshold').value
        model_path = self.get_parameter('model_path').value
        self.hfov_rad = math.radians(self.get_parameter('camera_hfov_deg').value)

        self.get_logger().info(f"loading YOLO model '{model_path}' (first run downloads weights)...")
        from ultralytics import YOLO
        self._model = YOLO(model_path)
        self.get_logger().info('model loaded')

        self.pub = self.create_publisher(Percept, '/percepts', 10)
        self._latest_jpeg: bytes | None = None
        self._frames_received = 0
        self._frames_processed = 0
        self._last_fps_log = self.get_clock().now()
        self.create_subscription(CompressedImage, camera_topic, self._on_camera, SENSOR_QOS)
        self.create_timer(1.0 / detect_hz, self._detect_tick)

        self.get_logger().info(
            f'detector_node up; camera={camera_topic}, detecting at {detect_hz} Hz, '
            f'confidence>={self.confidence_threshold}')

    def _on_camera(self, msg: CompressedImage):
        self._latest_jpeg = bytes(msg.data)
        self._frames_received += 1

    def _detect_tick(self):
        if self._latest_jpeg is None:
            self._maybe_log_fps()
            return
        frame = cv2.imdecode(np.frombuffer(self._latest_jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            self.get_logger().warn('detector: failed to decode a frame')
            self._maybe_log_fps()
            return
        self._frames_processed += 1

        results = self._model(frame, verbose=False)[0]
        height, width = frame.shape[0], frame.shape[1]
        stamp = self.get_clock().now().to_msg()

        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < self.confidence_threshold:
                continue
            cls_id = int(box.cls[0])
            label = self._model.names[cls_id]
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            center_x = (x1 + x2) / 2.0

            # Pixel offset from image center -> bearing, assuming the declared HFOV.
            # + = left of center, matching perception_node's LiDAR bearing convention.
            normalized = (width / 2.0 - center_x) / (width / 2.0)  # -1..1, + = left
            bearing = normalized * (self.hfov_rad / 2.0)

            p = Percept()
            p.header.frame_id = self.frame_id
            p.header.stamp = stamp
            p.label = label
            p.confidence = conf
            p.bearing = bearing
            # position left at zero: no depth fusion yet (see module docstring).
            # bbox normalised to [0,1] so the dashboard can overlay it at any size.
            p.bbox_x = x1 / width
            p.bbox_y = y1 / height
            p.bbox_w = (x2 - x1) / width
            p.bbox_h = (y2 - y1) / height
            self.pub.publish(p)

        self._maybe_log_fps()

    def _maybe_log_fps(self):
        now = self.get_clock().now()
        elapsed = (now - self._last_fps_log).nanoseconds / 1e9
        if elapsed < FPS_LOG_PERIOD_S:
            return
        if self._frames_received == 0:
            self.get_logger().warn(f'detector: no camera frames received in the last {elapsed:.0f}s')
        else:
            self.get_logger().info(
                f'detector: {self._frames_received} frames received, '
                f'{self._frames_processed} inferred in the last {elapsed:.0f}s')
        self._frames_received = 0
        self._frames_processed = 0
        self._last_fps_log = now


def main(args=None):
    rclpy.init(args=args)
    node = DetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
