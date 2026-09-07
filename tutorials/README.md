# Tutorials

Every level here is a **standalone CMake project** — build and try
things out independently, with no dependency on the main library
build. See [docs/adr/0011](../docs/adr/0011-tests-vs-tutorials.md) for
why: a tutorial is a place a human builds and experiments
independently, not something the main project should drag along.

Build everything at once from here:

```sh
cd tutorials
cmake -S . -B build
cmake --build build
```

...or build just **one** tutorial, entirely on its own, with no other
step first:

```sh
cd tutorials/01_hello_world
cmake -S . -B build
cmake --build build
```

Each numbered subdirectory builds to its own executable, demonstrating
one aspect of using libReflection end to end. These are separate from
[`../tests/`](../tests/), which is the automated unit-test suite
(`ReflectionTests`) run via `ctest` as part of the main library build.

- **`01_hello_world/`** — the current, working answer to "zero
  annotation, real names, even private members": a plain aggregate, a
  class with a constructor and private members, and a public-member
  class all resolve correctly via
  [docs/adr/0013](../docs/adr/0013-dwarf-based-reflection-generation.md)'s
  DWARF-based pipeline, wired up automatically in this directory's
  `CMakeLists.txt`.
- **`02_auto_reflect_legacy_struct/`** — automatic reflection alone
  (no DWARF pipeline here): zero annotation, but positional/sentinel
  names, showing the fallback `01_hello_world` improves on.
- **`03_macros_for_special_cases/`** — `REFLECT_CLASS_BEGIN`/
  `REFLECT_ENUM_BEGIN` written by hand: enums, array members, and
  non-aggregate types with public members — the cases that predate
  and don't need [0013](../docs/adr/0013-dwarf-based-reflection-generation.md).

Add a new tutorial by creating `NN_name/` with its own `main.cpp` and a
`CMakeLists.txt` modeled on an existing one (`cmake_minimum_required()`,
`project(...)`, `include()` of `../../cmake/ParseReflectionVersion.cmake`
and `../../cmake/BuildReflectionLibrary.cmake`, then
`add_executable(NN_name ...)` linked against `Reflection`) so it stays
independently buildable too, then add `add_subdirectory(NN_name)` to
this folder's `CMakeLists.txt`.
