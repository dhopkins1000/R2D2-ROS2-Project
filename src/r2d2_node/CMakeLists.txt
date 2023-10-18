cmake_minimum_required(VERSION 3.5)
project(r2d2_node)

# Default to C++14
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)

ament_package()

install(PROGRAMS
  scripts/r2d2_main.py
  DESTINATION lib/${PROJECT_NAME}
)