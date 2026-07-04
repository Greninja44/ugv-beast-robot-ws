from setuptools import find_packages, setup

package_name = 'robot_mcp'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='shinchan',
    maintainer_email='greninja220324@gmail.com',
    description='MCP server bridging AI tools to the ROS graph (topics/services/actions).',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mcp_server = robot_mcp.mcp_server:main',
        ],
    },
)
