include_directories(${CMAKE_SOURCE_DIR}/lib/)
link_directories(${CMAKE_SOURCE_DIR}/lib/)

add_executable(basedev basedev.c)
target_link_libraries(basedev cbcomms)
