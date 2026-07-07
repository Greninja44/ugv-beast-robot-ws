#!/usr/bin/env python3
"""GPU YOLO detector that feeds the dashboard over HTTP — no ROS/DDS needed.

WSL<->Pi DDS discovery doesn't work here (needs mirrored networking, a Windows-side
change), so instead of a ROS node this pulls the dashboard's MJPEG camera stream over
plain HTTP, runs YOLO on the local GPU (fast), and POSTs detections back to the
dashboard's /api/percepts/ingest endpoint. The dashboard republishes them as ROS
Percepts, so the live-detection overlay and any ROS consumer both see them.

Run on the RTX4050 box, using the same venv the on-Pi detector uses:

    ~/robot_ws/.venv-detector/bin/python3 dev/gpu_detector.py \
        --url http://<pi-ip>:8080 --token <control-token>

The default HFOV (69 deg, OAK-D-Lite RGB spec) only affects the reported bearing; it's
not a measured value for a specific unit — override with --hfov-deg if needed.
"""
import argparse
import json
import math
import time
import urllib.request

import cv2
import numpy as np
from ultralytics import YOLO


def mjpeg_frames(stream_url: str):
    """Yield decoded frames from a multipart/x-mixed-replace MJPEG stream. Finds JPEG
    SOI/EOI markers directly, so the multipart boundary headers are just skipped."""
    with urllib.request.urlopen(stream_url, timeout=10) as stream:
        buf = b''
        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            buf += chunk
            start = buf.find(b'\xff\xd8')            # JPEG start-of-image
            end = buf.find(b'\xff\xd9', start + 2)   # JPEG end-of-image, after start
            if start != -1 and end != -1:
                jpg = buf[start:end + 2]
                buf = buf[end + 2:]
                frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    yield frame


def post_detections(base_url: str, token: str, detections: list) -> None:
    data = json.dumps({'detections': detections}).encode()
    req = urllib.request.Request(
        base_url + '/api/percepts/ingest', data=data, method='POST',
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'})
    try:
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        print('[gpu_detector] POST failed:', e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', required=True, help='dashboard base URL, e.g. http://10.0.0.5:8080')
    ap.add_argument('--token', required=True, help='dashboard control token')
    ap.add_argument('--model', default='yolov8n.pt')
    ap.add_argument('--conf', type=float, default=0.5)
    ap.add_argument('--hfov-deg', type=float, default=69.0)
    ap.add_argument('--max-fps', type=float, default=15.0, help='cap inference rate')
    args = ap.parse_args()

    print(f'[gpu_detector] loading {args.model} ...')
    model = YOLO(args.model)
    print(f'[gpu_detector] streaming from {args.url}/api/camera/stream, '
          f'posting to {args.url}/api/percepts/ingest')

    hfov = math.radians(args.hfov_deg)
    min_dt = 1.0 / args.max_fps
    last = 0.0
    n_frames = 0
    n_posted = 0
    t0 = time.monotonic()

    while True:
        try:
            for frame in mjpeg_frames(args.url + '/api/camera/stream'):
                now = time.monotonic()
                if now - last < min_dt:
                    continue
                last = now
                h, w = frame.shape[:2]
                results = model(frame, verbose=False)[0]
                dets = []
                for box in results.boxes:
                    conf = float(box.conf[0])
                    if conf < args.conf:
                        continue
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cx = (x1 + x2) / 2.0
                    bearing = (w / 2.0 - cx) / (w / 2.0) * (hfov / 2.0)  # + = left
                    dets.append({
                        'label': model.names[int(box.cls[0])],
                        'confidence': round(conf, 3),
                        'bbox': [x1 / w, y1 / h, (x2 - x1) / w, (y2 - y1) / h],
                        'bearing': round(bearing, 3),
                    })
                post_detections(args.url, args.token, dets)
                n_frames += 1
                n_posted += len(dets)
                if now - t0 >= 5.0:
                    print(f'[gpu_detector] {n_frames / (now - t0):.1f} fps, '
                          f'{n_posted} detections in last {now - t0:.0f}s')
                    n_frames = n_posted = 0
                    t0 = now
        except Exception as e:
            print('[gpu_detector] stream error, reconnecting in 2s:', e)
            time.sleep(2.0)


if __name__ == '__main__':
    main()
