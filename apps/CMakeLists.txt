include_directories(${CMAKE_SOURCE_DIR}/lib/)
link_directories(${CMAKE_SOURCE_DIR}/lib/)

add_executable(baseapp baseapp.c)
target_link_libraries(baseapp cbcomms)

add_executable(sensortagapp sensortagapp.c)
target_link_libraries(sensortagapp cbcomms)

add_executable(accelapp accelapp.c)
target_link_libraries(accelapp cbcomms)
