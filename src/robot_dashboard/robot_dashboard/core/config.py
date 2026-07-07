"""Central configuration. Everything tunable lives here; no magic numbers elsewhere.

Precedence (highest to lowest): env vars prefixed DASH_ (e.g. DASH_PORT=9000) >
config/dashboard.yaml > defaults below. The auth token deliberately has no default:
unset token = read-only mode for everyone.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Type

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# Resolve via the ROS package share directory (correct for both --symlink-install and
# a plain colcon build — __file__-relative paths break under a plain build because the
# installed .py is a copy, not a symlink back to source). Falls back to the source tree
# for `python -m robot_dashboard.main` run straight out of src/ without an install step.
try:
    SHARE_ROOT = Path(get_package_share_directory('robot_dashboard'))
except PackageNotFoundError:
    SHARE_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_YAML = SHARE_ROOT / 'config' / 'dashboard.yaml'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='DASH_')

    host: str = '0.0.0.0'
    port: int = 8080

    # Security: token unset => read-only mode (telemetry visible, all control ops rejected).
    auth_token: str | None = None
    cors_origins: list[str] = ['http://localhost:5173']  # Vite dev server

    # Frontend static files (built SPA). Served if the directory exists.
    frontend_dir: Path = SHARE_ROOT / 'frontend' / 'dist'

    # ROS topic map — matches the live-verified vendor graph (docs/TOPICS.md).
    topic_voltage: str = '/voltage'
    topic_odom: str = '/odom'
    topic_scan: str = '/scan'
    topic_imu: str = '/imu/data'
    topic_cmd_vel: str = '/cmd_vel'
    topic_rosout: str = '/rosout'
    # depthai_ros_driver default (vendor launch: ugv_vision/launch/oak_d_lite.launch.py,
    # name=oak). CompressedImage only — never subscribe the raw Image (see docs/CAMERA.md).
    topic_camera: str = '/oak/rgb/image_raw/compressed'
    topic_led_ctrl: str = '/ugv/led_ctrl'
    # robot_skills.mode_server / robot_perception's shared percept topic (Phases 1-8).
    topic_mode: str = '/robot/mode'
    topic_percepts: str = '/percepts'

    # Robot Controls page (docs/DASHBOARD_DESIGN.md §7). Maps save into the
    # vendor's own maps directory (data, not vendor source) so its Nav2 configs
    # can find them by name, matching how ugv_nav/maps/map.yaml is referenced.
    map_save_dir: str = '/home/ws/ugv_ws/src/ugv_main/ugv_nav/maps'
    # Vendor (Waveshare) overlay setup.bash — sourced before the launch_manager
    # runs any ugv_* launch, so SLAM/Nav2/base buttons work even if the dashboard
    # itself was started without the vendor overlay on its path.
    vendor_setup: str = '/home/ws/ugv_ws/install/setup.bash'
    # Auto-start the base bringup (driver + lidar + sensors) when the dashboard boots,
    # so teleop/lights/telemetry work out of the box without a manual launch.
    autostart_base: bool = True
    # Off by default: reboot/shutdown are OS-level, not ROS — require an
    # explicit opt-in in dashboard.yaml even with a valid control token.
    allow_system_power_actions: bool = False
    # Deliberately NOT under SHARE_ROOT (the colcon install tree) — that gets
    # regenerated on every rebuild; user data belongs somewhere stable.
    waypoints_file: Path = Path.home() / '.config' / 'robot_dashboard' / 'waypoints.json'

    # Per-channel max publish rates to web clients (Hz).
    rate_telemetry: float = 2.0
    rate_odom: float = 10.0
    rate_imu: float = 10.0
    rate_scan: float = 5.0
    rate_log: float = 20.0
    rate_tf: float = 2.0
    rate_nav: float = 2.0
    rate_mode: float = 2.0
    rate_percepts: float = 5.0
    camera_stream_fps: float = 15.0

    # Battery model: 3S LiPo (measured 11.94 V healthy on this robot).
    battery_v_empty: float = 9.6
    battery_v_full: float = 12.6
    battery_v_warn: float = 10.5

    # Teleop safety ceilings (Phase 2 uses these; vendor slow=0.2, max=1.3 m/s).
    max_linear: float = 0.5
    max_angular: float = 1.2
    teleop_watchdog_s: float = 0.3
    teleop_publish_hz: float = 15.0

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Order = priority, highest first. YAML sits BELOW env vars so DASH_* always
        # wins, matching config/dashboard.yaml's own "(env DASH_* wins over this)" note.
        yaml_path = Path(os.environ.get('DASH_CONFIG', DEFAULT_YAML))
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        if yaml_path.is_file():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path))
        return tuple(sources)


def load_settings() -> Settings:
    return Settings()
