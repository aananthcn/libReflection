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
#   0. Lint SOURCE for a reflect::Reflect<T>() call this pipeline's
#      discovery step won't actually be able to reach -- a hard build
#      error (see generate_dwarf_reflection.py's "--lint" section),
#      so a real problem surfaces with a clear message here rather
#      than as a confusing template-instantiation error wall from step
#      3's compile, or (worse) a silent loss of real names/hash-
#      identity that never fails the build at all.
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
# NOTE: step 2 #includes SOURCE verbatim, so if SOURCE itself calls
# reflect::Reflect<T>() for some T (e.g. a type with a direct array
# member, which automatic aggregate reflection can't count -- see
# docs/adr/0001), that call gets compiled as part of the driver's
# bootstrap compile too, before the generated header has real content.
# This used to be a real, must-avoid pitfall (see
# tutorials/04_dwarf_arrays/pitfall/), fixed by having Reflect<T>()
# itself become a no-op under REFLECTION_DWARF_DRIVER_BUILD (defined
# below, only on the driver target) -- the driver never needs
# Reflect<T>()'s result, only T's complete-type "touch", so SOURCE no
# longer needs to avoid calling it. See docs/adr/0013's "Fixed bugs".
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

    # Fails the build (hard error, one line per finding) if SOURCE
    # contains a reflect::Reflect<T>() call for a struct/class T this
    # pipeline's discovery step can't actually reach -- see
    # generate_dwarf_reflection.py's "--lint" section. The real
    # target's own include directories are needed so a "<...>"
    # #include that actually resolves to a local project header (vs.
    # a genuine external system/library one) is recognized as such;
    # written to a file via file(GENERATE), not spliced into the
    # custom command's own argv, for the same reason step 3 below
    # compiles the driver as a real OBJECT target instead of
    # hand-splicing flags into a command string -- verified in that
    # case (see docs/adr/0013's "Fixed bugs") that the Unix Makefiles
    # generator does not reliably split a genex-expanded list passed
    # that way.
    set(lint_include_dirs_file "${CMAKE_CURRENT_BINARY_DIR}/${ARG_TARGET}_reflect_lint_include_dirs.txt")
    file(GENERATE OUTPUT "${lint_include_dirs_file}" CONTENT
"${REFLECTION_ROOT_DIR}/src
${CMAKE_CURRENT_BINARY_DIR}
${REFLECTION_GENERATED_INCLUDE_DIR}
$<JOIN:$<TARGET_PROPERTY:${ARG_TARGET},INCLUDE_DIRECTORIES>,\n>
"
    )
    set(lint_stamp "${CMAKE_CURRENT_BINARY_DIR}/${ARG_TARGET}_reflect_lint.stamp")
    add_custom_command(
        OUTPUT "${lint_stamp}"
        COMMAND "${Python3_EXECUTABLE}" "${script}" --lint "${source_abs}"
                --include-dirs-file "${lint_include_dirs_file}"
        COMMAND "${CMAKE_COMMAND}" -E touch "${lint_stamp}"
        DEPENDS "${script}" "${source_abs}" "${lint_include_dirs_file}"
        COMMENT "Checking ${ARG_SOURCE} for unreachable reflect::Reflect<T>() targets"
        VERBATIM
    )

    set(driver_cpp "${CMAKE_CURRENT_BINARY_DIR}/dwarf_extraction_driver_${ARG_TARGET}.cpp")
    add_custom_command(
        OUTPUT "${driver_cpp}"
        COMMAND "${Python3_EXECUTABLE}" "${script}" --emit-driver "${source_abs}" "${driver_cpp}"
        DEPENDS "${script}" "${source_abs}" "${lint_stamp}"
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
    # REFLECTION_DWARF_DRIVER_BUILD turns reflect::Reflect<T>() into a
    # no-op (src/TypeInfo.hpp) for this driver-only compile -- see the
    # NOTE above. Defined only here, never on ARG_TARGET's own compile.
    target_compile_definitions(${driver_target} PRIVATE
        REFLECTION_DWARF_DRIVER_BUILD=1
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
