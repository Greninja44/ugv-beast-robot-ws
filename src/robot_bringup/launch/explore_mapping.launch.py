"""Autonomous exploration + live mapping: combines the Waveshare stack's own
standalone cartographer SLAM (ugv_slam/cartographer.launch.py — genuine live
mapping, publishes a fresh /map as it goes) with Nav2's generic
navigation_launch.py (pure planning/costmap/controller stack — deliberately no
map_server or localization bundled; it's designed to consume a /map from
whatever SLAM source is already running).

WHY THIS EXISTS: ugv_nav's own nav.launch.py doesn't support this combination.
Read directly from the vendor source: all three of its use_localization modes
(amcl/emcl/cartographer) navigate against a PRE-SAVED map file — the
'cartographer' mode in particular loads a hardcoded
.../ugv_nav/maps/map.pbstream via cartographer's localization.launch.py, not its
mapping.launch.py. None of the three builds a fresh map while exploring.

Composing the Waveshare SLAM launch with Nav2's own generic, unmodified launch
file is the standard way any ROS2 Nav2 setup supports simultaneous mapping and
navigation (SLAM supplies /map + the map->odom TF; Nav2 just consumes it) — this
isn't a workaround, it's the intended use of navigation_launch.py's design.

No Waveshare code is imported or modified — this only INCLUDES two existing
launch files (one Waveshare, one stock nav2_bringup) via their own public,
parameterized launch-argument interfaces.
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # Reuses ugv_nav's own emcl_dwa.yaml: its controller/costmap/planner/behavior
    # sections are localization-agnostic (navigation_launch.py never instantiates
    # the map_server/map_saver nodes the file also happens to configure, so those
    # sections are simply unused here, not a conflict).
    default_params = os.path.join(
        get_package_share_directory('ugv_nav'), 'param', 'emcl_dwa.yaml')

    declare_params_file = DeclareLaunchArgument(
        'params_file', default_value=default_params,
        description='Nav2 controller/costmap/planner params')

    slam_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('ugv_slam'), 'launch', 'cartographer.launch.py')),
        launch_arguments={'use_rviz': 'false'}.items(),
    )

    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('nav2_bringup'), 'launch', 'navigation_launch.py')),
        launch_arguments={
            'params_file': LaunchConfiguration('params_file'),
            'use_composition': 'False',  # standalone nodes, no external container needed
            'autostart': 'true',
        }.items(),
    )

    return LaunchDescription([declare_params_file, slam_launch, nav2_launch])
