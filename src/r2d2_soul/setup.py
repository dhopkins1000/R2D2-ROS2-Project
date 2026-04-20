from setuptools import find_packages, setup

package_name = 'r2d2_soul'

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
    maintainer='Daniel Hopkins',
    maintainer_email='daniel@hopkins-family.net',
    description='Soul and autonomy layer for R2D2',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'llm_latency_test = r2d2_soul.llm_latency_test_node:main',
            'llm_node = r2d2_soul.llm_node:main',
        ],
    },
)
