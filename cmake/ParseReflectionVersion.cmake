# Parses REFLECTION_ROOT_DIR/version.txt into REFLECTION_VERSION_{MAJOR,MINOR,PATCH}.
#
# Split out from BuildReflectionLibrary.cmake because it must run
# BEFORE project() (its result feeds project()'s VERSION), whereas
# BuildReflectionLibrary.cmake must run AFTER project() (it calls
# add_library(), which needs a language already enabled).
#
# Expects REFLECTION_ROOT_DIR to already be set (the directory
# containing version.txt and src/). Included by both the root
# CMakeLists.txt and tutorials/CMakeLists.txt -- see
# docs/adr/0011-tutorials-and-their-purpose.md for why tutorials/ needs its own
# copy of this wiring rather than being pulled in by the root build.

file(STRINGS "${REFLECTION_ROOT_DIR}/version.txt" REFLECTION_VERSION_RAW LIMIT_COUNT 1)
string(STRIP "${REFLECTION_VERSION_RAW}" REFLECTION_VERSION_RAW)
if(NOT REFLECTION_VERSION_RAW MATCHES "^([0-9]+)\\.([0-9]+)\\.([0-9]+)$")
    message(FATAL_ERROR "version.txt ('${REFLECTION_VERSION_RAW}') must be a bare MAJOR.MINOR.PATCH version, e.g. 0.1.0")
endif()
set(REFLECTION_VERSION_MAJOR "${CMAKE_MATCH_1}")
set(REFLECTION_VERSION_MINOR "${CMAKE_MATCH_2}")
set(REFLECTION_VERSION_PATCH "${CMAKE_MATCH_3}")
