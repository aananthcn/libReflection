add_executable(ReflectionTests
    test_main.cpp
    test_basic_reflection.cpp
    test_hash.cpp
    test_enum.cpp
    test_registry.cpp
    test_auto_aggregate.cpp
)

target_link_libraries(ReflectionTests PRIVATE Reflection)

add_test(NAME ReflectionTests COMMAND ReflectionTests)

# Unit tests for tools/generate_dwarf_reflection.py -- the DWARF-based
# generator (see docs/adr/0013-dwarf-based-reflection-generation.md).
# Independent of the C++ library; end-to-end cases compile real
# fixtures and inspect actual DWARF output, so they're skipped
# automatically if g++/objdump aren't on PATH.
find_package(Python3 COMPONENTS Interpreter REQUIRED)
add_test(
    NAME GenerateDwarfReflectionPyTest
    COMMAND "${Python3_EXECUTABLE}" "${REFLECTION_ROOT_DIR}/tools/test_generate_dwarf_reflection.py" -v
)
