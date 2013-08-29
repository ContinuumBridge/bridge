include_directories(${CMAKE_SOURCE_DIR}/lib/)
link_directories(${CMAKE_SOURCE_DIR}/lib/)

add_executable(setupChannel setupChannel.c)
target_link_libraries(setupChannel cbcomms)
