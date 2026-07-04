import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'robot_dashboard'


def frontend_data_files():
    """Recursively install frontend/dist (the built SPA) preserving its tree, so
    ament_index_python.get_package_share_directory(...) / 'frontend' / 'dist' finds it
    regardless of whether this was a --symlink-install or a plain colcon build."""
    entries = []
    dist_root = 'frontend/dist'
    for dirpath, _dirnames, filenames in os.walk(dist_root):
        if not filenames:
            continue
        rel = os.path.relpath(dirpath, dist_root)
        dest = os.path.join('share', package_name, 'frontend', 'dist', rel) if rel != '.' \
            else os.path.join('share', package_name, 'frontend', 'dist')
        entries.append((dest, [os.path.join(dirpath, f) for f in filenames]))
    return entries


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test', 'frontend']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        *frontend_data_files(),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='shinchan',
    maintainer_email='greninja220324@gmail.com',
    description='Web dashboard backend (FastAPI + rclpy) and frontend for the UGV Beast.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'dashboard = robot_dashboard.main:main',
        ],
    },
)
