from setuptools import find_packages, setup

package_name = 'robot_manipulation'

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
    description='Pan-tilt gimbal control (the manipulation surface on UGV Beast).',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'gimbal_node = robot_manipulation.gimbal_node:main',
        ],
    },
)
