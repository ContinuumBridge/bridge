cmake_minimum_required(VERSION 2.8)

project(appframework C)

set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -Wall -Werror -std=c99")

add_subdirectory(lib)
add_subdirectory(apps)
add_subdirectory(devices)
add_subdirectory(concentrator)
