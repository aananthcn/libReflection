# QNX SDP 8.0 CMake toolchain file, for x86_64 and aarch64 QNX targets.
#
# Source the SDP 8.0 environment first (qnxsdp-env.sh -- puts the
# per-target compiler binaries below on PATH), then pick the target
# with a plain environment variable -- no file to edit, no -D flag
# required (though -DCMAKE_SYSTEM_PROCESSOR=... still works too, and
# takes precedence if both are given):
#
#   export QNX_ARCH=aarch64     # or x86_64 (default: aarch64)
#   cmake -S . -B build-qnx -DCMAKE_TOOLCHAIN_FILE=<repo>/cmake/qnx-toolchain.cmake
#   cmake --build build-qnx
#
# Deliberately names the per-target GNU-triple compiler binaries
# (x86_64-pc-nto-qnx8.0.0-g++, aarch64-unknown-nto-qnx8.0.0-g++) rather
# than the qcc/q++ wrappers: CMake derives CMAKE_OBJDUMP from the
# compiler name, and only the GNU-triple form reliably resolves to the
# matching per-target objdump. cmake/GenerateDwarfReflection.cmake
# depends on CMAKE_OBJDUMP being the *correct* target's objdump --
# with qcc/q++ it was observed to silently fall back to the host's
# own objdump instead, which reads the wrong target. Verified end to
# end for both architectures against a real QNX SDP 8.0 install; see
# docs/adr/0013-dwarf-based-reflection-generation.md.

if(NOT CMAKE_SYSTEM_PROCESSOR)
    if(DEFINED ENV{QNX_ARCH})
        set(CMAKE_SYSTEM_PROCESSOR "$ENV{QNX_ARCH}")
    else()
        set(CMAKE_SYSTEM_PROCESSOR aarch64)
    endif()
endif()

set(CMAKE_SYSTEM_NAME QNX)

if(CMAKE_SYSTEM_PROCESSOR STREQUAL "x86_64")
    set(CMAKE_C_COMPILER x86_64-pc-nto-qnx8.0.0-gcc)
    set(CMAKE_CXX_COMPILER x86_64-pc-nto-qnx8.0.0-g++)
elseif(CMAKE_SYSTEM_PROCESSOR STREQUAL "aarch64")
    set(CMAKE_C_COMPILER aarch64-unknown-nto-qnx8.0.0-gcc)
    set(CMAKE_CXX_COMPILER aarch64-unknown-nto-qnx8.0.0-g++)
else()
    message(FATAL_ERROR
        "cmake/qnx-toolchain.cmake: unsupported CMAKE_SYSTEM_PROCESSOR "
        "'${CMAKE_SYSTEM_PROCESSOR}' -- supported values: x86_64, aarch64")
endif()

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
