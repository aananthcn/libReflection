# reflection_generate_dwarf(TARGET <t> SOURCE <src>)
#
# Automatically reflects EVERY struct/class declared in SOURCE (or a
# local header it #includes) -- public or private members, aggregate
# or not -- with NO annotation of any kind required. See
# tools/generate_dwarf_reflection.py and
# docs/adr/0013-dwarf-based-reflection-generation.md for how and why.
#
# Pipeline (all of it runs automatically as part of a normal build --
# no separate manual step):
#   1. Scan SOURCE (and any local "..." headers it includes) for
#      struct/class names -- just names, DWARF handles everything else.
#   2. Emit a throwaway "driver" .cpp that #includes SOURCE and
#      declares one instance of each discovered type (forces the
#      compiler to emit that type's FULL debug info -- a type merely
#      named in an unevaluated context like sizeof() is not guaranteed
#      to get full DWARF output, verified empirically).
#   3. Compile the driver with -g -gdwarf-4 into a throwaway object
#      (never linked into anything -- #include-ing an arbitrary .cpp,
#      even one with its own main(), is safe here since this object is
#      never combined with another translation unit).
#   4. Read that object's DWARF (via CMake's own ${CMAKE_OBJDUMP} --
#      the toolchain-matching one, e.g. QNX SDP's target-specific
#      "<triple>-objdump" when cross-compiling, not the host's --
#      falling back to plain "objdump" if CMake didn't detect one) and
#      generate a header with a REFLECT_DWARF_CLASS_BEGIN/
#      REFLECT_DWARF_MEMBER/REFLECT_DWARF_CLASS_END block per type found.
#   5. TARGET's real compile of SOURCE is ordered to happen after step
#      4 (via OBJECT_DEPENDS), so it sees the freshly generated header.
#
# SOURCE must unconditionally
#   #include "generated_dwarf_reflection.hpp"
# after all its type definitions (same declare-before-use rule as
# REFLECT_CLASS_BEGIN -- see docs/adr/0010). A placeholder is written
# automatically on first configure so this never fails to compile
# before extraction has run once.
#
# Expects REFLECTION_ROOT_DIR to already be set.

find_package(Python3 COMPONENTS Interpreter REQUIRED)

function(reflection_generate_dwarf)
    cmake_parse_arguments(ARG "" "TARGET;SOURCE" "" ${ARGN})
    if(NOT ARG_TARGET OR NOT ARG_SOURCE)
        message(FATAL_ERROR "reflection_generate_dwarf() requires TARGET and SOURCE")
    endif()

    set(script "${REFLECTION_ROOT_DIR}/tools/generate_dwarf_reflection.py")
    get_filename_component(source_abs "${ARG_SOURCE}" ABSOLUTE)

    set(generated_header "${CMAKE_CURRENT_BINARY_DIR}/generated_dwarf_reflection.hpp")
    if(NOT EXISTS "${generated_header}")
        file(WRITE "${generated_header}" "#pragma once\n")
    endif()

    set(driver_cpp "${CMAKE_CURRENT_BINARY_DIR}/dwarf_extraction_driver_${ARG_TARGET}.cpp")
    add_custom_command(
        OUTPUT "${driver_cpp}"
        COMMAND "${Python3_EXECUTABLE}" "${script}" --emit-driver "${source_abs}" "${driver_cpp}"
        DEPENDS "${script}" "${source_abs}"
        COMMENT "Discovering reflectable types in ${ARG_SOURCE}"
        VERBATIM
    )

    set(extraction_obj "${CMAKE_CURRENT_BINARY_DIR}/dwarf_extract_${ARG_TARGET}.o")
    add_custom_command(
        OUTPUT "${extraction_obj}"
        COMMAND "${CMAKE_CXX_COMPILER}" -std=c++20 -g -gdwarf-4
                -I "${REFLECTION_ROOT_DIR}/src" -I "${CMAKE_CURRENT_BINARY_DIR}"
                -I "${CMAKE_CURRENT_BINARY_DIR}/generated"
                -c "${driver_cpp}" -o "${extraction_obj}"
        DEPENDS "${driver_cpp}"
        COMMENT "Compiling ${ARG_SOURCE} with debug info for DWARF extraction"
        VERBATIM
    )

    set(objdump_bin "objdump")
    if(CMAKE_OBJDUMP)
        set(objdump_bin "${CMAKE_OBJDUMP}")
    endif()

    add_custom_command(
        OUTPUT "${generated_header}"
        COMMAND "${Python3_EXECUTABLE}" "${script}" --extract
                "${extraction_obj}" "${source_abs}" "${generated_header}"
                --objdump "${objdump_bin}"
        DEPENDS "${extraction_obj}" "${source_abs}" "${script}"
        COMMENT "Generating reflection registration from DWARF for ${ARG_SOURCE}"
        VERBATIM
    )

    set_source_files_properties("${source_abs}" PROPERTIES OBJECT_DEPENDS "${generated_header}")
    target_sources(${ARG_TARGET} PRIVATE "${generated_header}")
    target_include_directories(${ARG_TARGET} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
endfunction()
