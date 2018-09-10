
# Set the minimum version of CMake that can be used
# To find the cmake version run
# $ cmake --version
cmake_minimum_required(VERSION 2.8)

# Set the project name
project (hello_buildstreams C)

# Add an executable
add_executable(hello_buildstream main.c)


install(TARGETS hello_buildstream DESTINATION /bin) 
