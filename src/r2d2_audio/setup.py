from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'r2d2_audio'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='r2d2',
    maintainer_email='r2d2@localhost',
    description='R2D2 Audio: ReSpeaker, Wake Word, Whisper STT, Voice Output',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'respeaker_node  = r2d2_audio.respeaker_node:main',
            'wake_word_node  = r2d2_audio.wake_word_node:main',
            'whisper_node    = r2d2_audio.whisper_node:main',
            'voice_node      = r2d2_audio.voice_node:main',
        ],
    },
)
