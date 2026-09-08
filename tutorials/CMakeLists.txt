# Convenience aggregator: builds every tutorial at once from here.
#   cmake -S . -B build
#   cmake --build build
#
# Not required -- each NN_name/ subdirectory is ALSO independently
# standalone (its own project(), its own build/): cd into any one of
# them and run the same two commands with no other step first. See
# docs/adr/0011-tutorials-and-their-purpose.md for why tutorials/ (at every
# level) is deliberately not wired into the root CMakeLists.txt.

cmake_minimum_required(VERSION 3.20)

set(REFLECTION_ROOT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/..")
include("${REFLECTION_ROOT_DIR}/cmake/ParseReflectionVersion.cmake")

project(ReflectionTutorials
    VERSION ${REFLECTION_VERSION_MAJOR}.${REFLECTION_VERSION_MINOR}.${REFLECTION_VERSION_PATCH}
    LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include("${REFLECTION_ROOT_DIR}/cmake/BuildReflectionLibrary.cmake")

add_subdirectory(01_hello_world)
add_subdirectory(02_auto_reflect_legacy_struct)
add_subdirectory(03_macros_for_special_cases)
add_subdirectory(04_dwarf_arrays)
add_subdirectory(05_enums)
