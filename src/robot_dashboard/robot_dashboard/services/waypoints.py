"""Waypoint list — simple JSON-file persistence, no ROS involved."""
from __future__ import annotations

import json
import uuid
from pathlib import Path


class WaypointStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, items: list[dict]) -> None:
        self.path.write_text(json.dumps(items, indent=2))

    def list(self) -> list[dict]:
        return self._read()

    def add(self, name: str, x: float, y: float, yaw: float) -> dict:
        items = self._read()
        wp = {'id': uuid.uuid4().hex[:8], 'name': name, 'x': x, 'y': y, 'yaw': yaw}
        items.append(wp)
        self._write(items)
        return wp

    def delete(self, wp_id: str) -> bool:
        items = self._read()
        remaining = [w for w in items if w['id'] != wp_id]
        if len(remaining) == len(items):
            return False
        self._write(remaining)
        return True
