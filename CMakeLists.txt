cmake_minimum_required(VERSION 3.20)

set(REFLECTION_ROOT_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
include("${REFLECTION_ROOT_DIR}/cmake/ParseReflectionVersion.cmake")

project(Reflection
    VERSION ${REFLECTION_VERSION_MAJOR}.${REFLECTION_VERSION_MINOR}.${REFLECTION_VERSION_PATCH}
    LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include("${REFLECTION_ROOT_DIR}/cmake/BuildReflectionLibrary.cmake")

option(REFLECTION_BUILD_TESTS "Build libReflection unit tests" ON)
if(REFLECTION_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

# tutorials/ is a standalone sandbox for a human to build and try
# things out independently -- it is NOT part of this project's build.
# See tutorials/README.md and docs/adr/0011-tutorials-and-their-purpose.md.

include(GNUInstallDirs)

install(TARGETS Reflection ARCHIVE DESTINATION "${CMAKE_INSTALL_LIBDIR}")
install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/src/"
        DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}"
        FILES_MATCHING PATTERN "*.hpp")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/generated/Version.hpp"
        DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}")
install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/version.txt"
        DESTINATION "${CMAKE_INSTALL_DATADIR}/Reflection")
