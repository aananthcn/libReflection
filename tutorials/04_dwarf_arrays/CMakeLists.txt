# Fully standalone: cd into this directory and
#   cmake -S . -B build && cmake --build build
# works with no other step first -- no need to configure/build the
# root project or tutorials/ first. See docs/adr/0011-tutorials-and-their-purpose.md.
cmake_minimum_required(VERSION 3.20)

set(REFLECTION_ROOT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../..")
include("${REFLECTION_ROOT_DIR}/cmake/ParseReflectionVersion.cmake")

project(DwarfArraysTutorial
    VERSION ${REFLECTION_VERSION_MAJOR}.${REFLECTION_VERSION_MINOR}.${REFLECTION_VERSION_PATCH}
    LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include("${REFLECTION_ROOT_DIR}/cmake/BuildReflectionLibrary.cmake")
include("${REFLECTION_ROOT_DIR}/cmake/GenerateDwarfReflection.cmake")

add_executable(04_dwarf_arrays main.cpp)
target_link_libraries(04_dwarf_arrays PRIVATE Reflection)

# SOURCE is main.cpp itself -- the same file that calls
# reflect::Reflect<T>() (see main.cpp's top comment). That used to be
# disallowed (SOURCE gets #include-d verbatim into the extraction
# driver's bootstrap compile, before the generated header has real
# content), but reflect::Reflect<T>() becoming a no-op under
# REFLECTION_DWARF_DRIVER_BUILD during that one bootstrap compile
# (src/TypeInfo.hpp) removed the restriction -- see docs/adr/0013's
# "Fixed bugs". reflection_generate_dwarf() orders SOURCE's real
# compile to wait for the generated header itself, so no extra
# OBJECT_DEPENDS is needed here.
reflection_generate_dwarf(
    TARGET 04_dwarf_arrays
    SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/main.cpp"
)
