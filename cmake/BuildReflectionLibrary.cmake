# Defines the Reflection target by compiling it from source.
#
# The single source of truth for "how to build libReflection", included
# by every independently-buildable CMake project in this repo: the root
# CMakeLists.txt (the real project, with tests/ and install() rules),
# tutorials/CMakeLists.txt (build every tutorial at once), and each
# individual tutorials/NN_name/CMakeLists.txt (build just that one, cd
# in and `cmake -S . -B build` with no other step first -- a tutorial
# is a place to build and try things out independently, all the way
# down to a single example; see docs/adr/0011-tutorials-and-their-purpose.md).
# Keeping the library-build logic in one shared file means there's only
# one place to update if it ever changes.
#
# Expects REFLECTION_ROOT_DIR to be set (the directory containing src/)
# and REFLECTION_VERSION_{MAJOR,MINOR,PATCH} to already be parsed (see
# ParseReflectionVersion.cmake) and project() to have already run.
#
# Idempotent: guarded so that when tutorials/CMakeLists.txt and one of
# its add_subdirectory()'d children both include this (building "every
# tutorial at once" still works too), the Reflection target is only
# defined once.
if(NOT TARGET Reflection)
    configure_file(
        "${REFLECTION_ROOT_DIR}/src/Version.hpp.in"
        "${CMAKE_CURRENT_BINARY_DIR}/generated/Version.hpp"
        @ONLY)

    # Recorded so other modules that need this exact directory (e.g.
    # GenerateDwarfReflection.cmake's extraction-driver compile, which
    # can't just guess "${CMAKE_CURRENT_BINARY_DIR}/generated" itself --
    # that guess is wrong whenever it runs from a DIFFERENT directory
    # scope than this file was include()'d from, which happens for
    # tutorials/'s aggregator build (this file is include()'d once at
    # tutorials/CMakeLists.txt's scope, but
    # reflection_generate_dwarf() runs from each
    # tutorials/NN_name/CMakeLists.txt's own subdirectory scope) --
    # can reference the real path instead of re-deriving it.
    set(REFLECTION_GENERATED_INCLUDE_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")

    add_library(Reflection STATIC
        "${REFLECTION_ROOT_DIR}/src/ClassReflection.cpp"
        "${REFLECTION_ROOT_DIR}/src/ReflectionHash.cpp"
        "${REFLECTION_ROOT_DIR}/src/ReflectionRegistry.cpp"
    )

    target_include_directories(Reflection
        PUBLIC
            $<BUILD_INTERFACE:${REFLECTION_ROOT_DIR}/src>
            $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/generated>
            $<INSTALL_INTERFACE:include>
    )

    target_compile_features(Reflection PUBLIC cxx_std_20)
endif()
