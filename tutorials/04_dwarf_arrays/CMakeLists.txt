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

# SOURCE is ArrayTypes.hpp, NOT main.cpp -- see ArrayTypes.hpp's top
# comment for why: the extraction driver #includes SOURCE directly, so
# main.cpp's reflect::Reflect<T>() calls must stay out of that file,
# or the driver's bootstrap compile (before the generated header has
# real content) would hit automatic aggregate reflection's deliberate
# hard-fail for a direct array member.
reflection_generate_dwarf(
    TARGET 04_dwarf_arrays
    SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/ArrayTypes.hpp"
)

# reflection_generate_dwarf() only orders ITS OWN SOURCE (ArrayTypes.hpp)
# to wait for the generated header. main.cpp also needs the real
# specializations (it's the file that actually calls
# reflect::Reflect<T>()), so its compile must wait too.
set_source_files_properties("${CMAKE_CURRENT_SOURCE_DIR}/main.cpp" PROPERTIES
    OBJECT_DEPENDS "${CMAKE_CURRENT_BINARY_DIR}/generated_dwarf_reflection.hpp"
)
