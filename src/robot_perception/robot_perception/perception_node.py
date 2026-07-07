#!/usr/bin/env python3
"""robot_perception — nearest-obstacle percept from LiDAR, plus a camera pipeline.

Subscribes to the Waveshare `/scan` (sensor_msgs/LaserScan) and publishes a
`robot_interfaces/Percept` for the closest return, and separately subscribes to the
OAK-D's compressed RGB stream (`/oak/rgb/image_raw/compressed` — the real, verified
topic robot_dashboard already streams from; QoS must be SENSOR_DATA/BEST_EFFORT, a
RELIABLE subscriber silently gets nothing against depthai_ros_driver's publisher).

Frames are decoded on a slower fixed-rate timer, not in the subscription callback —
the camera streams far faster than any detector should run, so only the newest frame
is kept between ticks (same latest-wins idea as robot_dashboard's LatestBuffer).

Camera plumbing only — no detector attached yet (see Phase 8: object detection). The
Waveshare stack's own AprilTag integration (ugv_vision's apriltag_ctrl/apriltag_track_0)
is wired to /image_raw from the gimbal camera, which is physically removed on this
robot — dead on current hardware, not reusable as-is (see docs/CAMERA.md).

Interfaces ONLY with the Waveshare stack via topics — no Waveshare code is imported.
"""
import math

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSPresetProfiles
from sensor_msgs.msg import CompressedImage, LaserScan
from robot_interfaces.msg import Percept

SENSOR_QOS = QoSPresetProfiles.SENSOR_DATA.value
FPS_LOG_PERIOD_S = 5.0


class PerceptionNode(Node):
    def __init__(self):
        super().__init__('perception_node')
        self.declare_parameter('scan_topic', '/scan')
        self.declare_parameter('camera_topic', '/oak/rgb/image_raw/compressed')
        self.declare_parameter('camera_process_hz', 2.0)
        scan_topic = self.get_parameter('scan_topic').value
        camera_topic = self.get_parameter('camera_topic').value
        process_hz = self.get_parameter('camera_process_hz').value

        self.sub = self.create_subscription(LaserScan, scan_topic, self.on_scan, 10)
        # Shared across all perception sources (this node's LiDAR percept, and
        # detector_node's YOLO percepts) so downstream consumers (future world model)
        # subscribe once rather than per-source.
        self.pub = self.create_publisher(Percept, '/percepts', 10)

        self._latest_jpeg: bytes | None = None
        self._last_frame_shape: tuple[int, int] | None = None
        self._frames_received = 0
        self._frames_processed = 0
        self._last_fps_log = self.get_clock().now()
        self.create_subscription(CompressedImage, camera_topic, self._on_camera, SENSOR_QOS)
        self.create_timer(1.0 / process_hz, self._process_camera_tick)

        self.get_logger().info(
            f'robot_perception up; scan={scan_topic}, camera={camera_topic} '
            f'(processing at {process_hz} Hz)')

    def on_scan(self, msg: LaserScan):
        ranges = [r for r in msg.ranges if math.isfinite(r) and r > 0.0]
        if not ranges:
            return
        idx = min(range(len(msg.ranges)),
                  key=lambda i: msg.ranges[i] if math.isfinite(msg.ranges[i]) and msg.ranges[i] > 0 else math.inf)
        rng = msg.ranges[idx]
        bearing = msg.angle_min + idx * msg.angle_increment

        p = Percept()
        p.header = msg.header
        p.label = 'nearest_obstacle'
        p.confidence = 1.0
        p.position.x = rng * math.cos(bearing)
        p.position.y = rng * math.sin(bearing)
        p.position.z = 0.0
        p.bearing = bearing
        self.pub.publish(p)

    # ---- camera pipeline -------------------------------------------------------
    def _on_camera(self, msg: CompressedImage):
        # Just stash the newest frame — decoding happens on the slower processing
        # timer below, not here, so a fast camera stream doesn't stall this callback.
        self._latest_jpeg = bytes(msg.data)
        self._frames_received += 1

    def _process_camera_tick(self):
        if self._latest_jpeg is not None:
            frame = cv2.imdecode(np.frombuffer(self._latest_jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                self.get_logger().warn('camera: failed to decode a frame (corrupt JPEG?)')
            else:
                self._frames_processed += 1
                self._last_frame_shape = (frame.shape[1], frame.shape[0])
                # Extension point for Phase 8 (YOLO): detections = detect(frame);
                # publish a Percept per detection, the same way on_scan does above.

        self._maybe_log_fps()

    def _maybe_log_fps(self):
        now = self.get_clock().now()
        elapsed = (now - self._last_fps_log).nanoseconds / 1e9
        if elapsed < FPS_LOG_PERIOD_S:
            return
        size = f'{self._last_frame_shape[0]}x{self._last_frame_shape[1]}' if self._last_frame_shape else 'n/a'
        if self._frames_received == 0:
            self.get_logger().warn(f'camera: no frames received in the last {elapsed:.0f}s — '
                                    'is the OAK-D driver running and publishing?')
        else:
            self.get_logger().info(
                f'camera: {self._frames_received} frames received, '
                f'{self._frames_processed} processed in the last {elapsed:.0f}s, last size {size}')
        self._frames_received = 0
        self._frames_processed = 0
        self._last_fps_log = now


def main(args=None):
    rclpy.init(args=args)
    node = PerceptionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
