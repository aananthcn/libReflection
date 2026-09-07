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
#   3. Compile the driver -- as its own OBJECT library target, so it
#      can mirror TARGET's own COMPILE_DEFINITIONS/INCLUDE_DIRECTORIES/
#      COMPILE_OPTIONS (custom -D defines, non-default struct-packing
#      flags, etc.) on top of a fixed -std=c++20 -g -gdwarf-4 floor --
#      into a throwaway object (never linked into anything --
#      #include-ing an arbitrary .cpp, even one with its own main(), is
#      safe here since this object is never combined with another
#      translation unit).
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
# CAUTION: because step 2 #includes SOURCE verbatim, SOURCE itself must
# not call reflect::Reflect<T>() for a type automatic aggregate
# reflection would hard-fail to compile (e.g. one with a direct array
# member) -- the driver's bootstrap compile (before the generated
# header has real content) falls back to that primary template, not
# the DWARF specialization. See docs/adr/0013's "Known open risks" and
# tutorials/04_dwarf_arrays, which keeps array-containing type
# definitions in a separate header with no reflect::Reflect<T>() calls
# in it, precisely to avoid this.
#
# Expects REFLECTION_ROOT_DIR to already be set, and
# BuildReflectionLibrary.cmake to have already been include()'d (which
# sets REFLECTION_GENERATED_INCLUDE_DIR, needed below) and defined the
# Reflection target.

find_package(Python3 COMPONENTS Interpreter REQUIRED)

function(reflection_generate_dwarf)
    cmake_parse_arguments(ARG "" "TARGET;SOURCE" "" ${ARGN})
    if(NOT ARG_TARGET OR NOT ARG_SOURCE)
        message(FATAL_ERROR "reflection_generate_dwarf() requires TARGET and SOURCE")
    endif()
    if(NOT REFLECTION_GENERATED_INCLUDE_DIR)
        message(FATAL_ERROR "reflection_generate_dwarf() requires BuildReflectionLibrary.cmake "
                             "to be include()'d first (it sets REFLECTION_GENERATED_INCLUDE_DIR)")
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

    # Compiled as a real (OBJECT) CMake target, not a hand-rolled
    # compiler invocation in a custom command -- so it can mirror
    # TARGET's own COMPILE_DEFINITIONS/INCLUDE_DIRECTORIES/
    # COMPILE_OPTIONS via ordinary target_compile_definitions()/
    # target_include_directories()/target_compile_options() reading
    # $<TARGET_PROPERTY:TARGET,...>, resolved at generate time so call
    # order relative to those calls on TARGET doesn't matter. CMake's
    # own target-property machinery is what turns a property list into
    # correctly individually-split -D/-I/etc. flags; splicing them
    # into one COMMAND string by hand (e.g. via "SHELL:...$<JOIN:...>"
    # in add_custom_command) was tried first and does NOT reliably
    # work -- verified: the Unix Makefiles generator did not honor
    # SHELL: at all, passing the whole joined string as one malformed
    # argument instead of splitting it. This target-based approach
    # means the object DWARF is extracted from can't disagree with the
    # real one on anything that affects layout (custom -D defines,
    # non-default struct-packing pragmas via e.g. -fpack-struct). See
    # docs/adr/0013's "Fixed bugs" for why this used to be a real, open
    # risk (a fixed flag set only, with no such guarantee).
    set(driver_target "${ARG_TARGET}_dwarf_extraction_driver")
    add_library(${driver_target} OBJECT "${driver_cpp}")
    target_compile_definitions(${driver_target} PRIVATE
        $<TARGET_PROPERTY:${ARG_TARGET},COMPILE_DEFINITIONS>
    )
    target_include_directories(${driver_target} PRIVATE
        "${REFLECTION_ROOT_DIR}/src" "${CMAKE_CURRENT_BINARY_DIR}" "${REFLECTION_GENERATED_INCLUDE_DIR}"
        $<TARGET_PROPERTY:${ARG_TARGET},INCLUDE_DIRECTORIES>
    )
    target_compile_options(${driver_target} PRIVATE
        -std=c++20 -g -gdwarf-4
        $<TARGET_PROPERTY:${ARG_TARGET},COMPILE_OPTIONS>
    )
    # An add_custom_command's DEPENDS on $<TARGET_OBJECTS:driver_target>
    # alone isn't enough for the Unix Makefiles generator to reliably
    # trigger the recursive sub-make that actually builds
    # driver_target's object first -- verified empirically ("No rule
    # to make target ...dwarf_extraction_driver....cpp.o"). An explicit
    # target-level dependency is generator-agnostic and reliable.
    add_dependencies(${ARG_TARGET} ${driver_target})
    set(extraction_obj "$<TARGET_OBJECTS:${driver_target}>")

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
