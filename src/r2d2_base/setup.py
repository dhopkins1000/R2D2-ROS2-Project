from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'r2d2_base'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='r2d2',
    maintainer_email='r2d2@localhost',
    description='Basisantriebs-Steuerung für R2D2',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'odom_tf_broadcaster = r2d2_base.odom_tf_broadcaster:main',
        ],
    },
)
