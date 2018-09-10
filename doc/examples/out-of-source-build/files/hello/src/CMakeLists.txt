
# Set the minimum version of CMake that can be used
# To find the cmake version run
# $ cmake --version
cmake_minimum_required(VERSION 2.8)

# Set the project name
project (hello_main C)

# Set something so that we can see if main.c was compiled from this cmake
# projcet
set(CMAKE_C_FLAGS "-DFULL_PROJECT")

add_subdirectory(main)
