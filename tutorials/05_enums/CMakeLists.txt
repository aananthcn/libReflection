# Fully standalone: cd into this directory and
#   cmake -S . -B build && cmake --build build
# works with no other step first -- no need to configure/build the
# root project or tutorials/ first. See docs/adr/0011-tutorials-and-their-purpose.md.
cmake_minimum_required(VERSION 3.20)

set(REFLECTION_ROOT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../..")
include("${REFLECTION_ROOT_DIR}/cmake/ParseReflectionVersion.cmake")

project(EnumsTutorial
    VERSION ${REFLECTION_VERSION_MAJOR}.${REFLECTION_VERSION_MINOR}.${REFLECTION_VERSION_PATCH}
    LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# No DWARF pipeline here: 0013's generator covers class members, not
# enum value names (see its scope). Enums use either REFLECT_ENUM_BEGIN
# or the plain-C++ trick below -- neither needs GenerateDwarfReflection.
include("${REFLECTION_ROOT_DIR}/cmake/BuildReflectionLibrary.cmake")

add_executable(05_enums main.cpp)
target_link_libraries(05_enums PRIVATE Reflection)
