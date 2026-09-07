# 0011 — Tutorials and Their Purpose

**Status:** Decided; revised twice — `tutorials/` is now a fully
standalone CMake project, not built by the root project at all, and
**each individual tutorial is independently standalone too** (see
"Revision" and "Second revision" below). Formerly titled
"`tests/` vs. `tutorials/`"; the content specific to `tests/` (what it
is, why it's scoped the way it is, and the shared naming history with
`tutorials/`) now lives in [0007](0007-testing-strategy.md), the ADR
actually about testing strategy, leaving this file for `tutorials/`
alone — see 0007's Context for why these two needed separate,
visibly-distinct homes in the first place.

## Context

`tutorials/` holds numbered, runnable example applications
demonstrating the library end to end (the "hello world" of using
libReflection, and onward as `02_xxx`, `03_xxx`, ...) — a place a human
builds and tries things out, distinct from [0007](0007-testing-strategy.md)'s
automated `ReflectionTests` unit suite.

Originally `tutorials/` was wired into the root `CMakeLists.txt` via
`add_subdirectory(tutorials)`, the same way `tests/` is. This was
wrong: a *tutorial* is, by definition, a place a human goes to build
and try things out on their own — not something that should be forced
to build every time the library itself is configured, and not
something whose CMake wiring should implicitly assume it's a
subdirectory of a larger, already-configured project.

The concrete symptom: someone tried to build a single tutorial
directly (`cd tutorials/01_hello_world && cmake ..`), which failed —
`01_hello_world/CMakeLists.txt` had no `project()` call and no idea
where the library's headers lived, because it had only ever been
designed to be pulled in by the root project.

## Decision

`tutorials/` holds the numbered example applications
(`01_hello_world/`, `02_...`, ...), each its own standalone executable.
See `tutorials/README.md`.

## Revision: `tutorials/` is a standalone project, not part of the root build

**Revised decision:** `tutorials/` is now its own independent,
self-contained CMake project:

- `tutorials/CMakeLists.txt` has its own `cmake_minimum_required()` and
  `project(ReflectionTutorials ...)`, and can be configured and built
  entirely on its own, from a clean checkout, with **zero** dependency
  on the root project having been configured or built first:
  ```sh
  cd tutorials
  cmake -S . -B build
  cmake --build build
  ```
- The root `CMakeLists.txt` no longer references `tutorials/` at all —
  no `add_subdirectory`, no `REFLECTION_BUILD_TUTORIALS` option.
- Both projects need to compile `libReflection` from the same source,
  so that logic (version parsing, `configure_file` for the generated
  `Version.hpp`, `add_library(Reflection ...)`) was factored out into
  two small shared CMake modules —
  `cmake/ParseReflectionVersion.cmake` (must run *before* `project()`,
  since its output feeds `project()`'s `VERSION`) and
  `cmake/BuildReflectionLibrary.cmake` (must run *after* `project()`,
  since `add_library` needs a language already enabled) — `include()`d
  by both `CMakeLists.txt` files. This keeps "how to build
  libReflection" defined in exactly one place despite there now being
  two independent top-level projects that need it.

## Second revision: every individual tutorial is also independently standalone

The first revision above stopped short: it made `tutorials/` (the
folder as a whole) standalone, but a single tutorial subdirectory
(`tutorials/01_hello_world/`) still had no `project()` of its own —
it only worked pulled in via `tutorials/CMakeLists.txt`'s
`add_subdirectory()`. The same concrete symptom recurred: someone
tried `cd tutorials/01_hello_world && mkdir build && cd build &&
cmake ..`, which failed the same way as before, one level down.

**Revised again:** "a tutorial is a place to build and try things out
independently" applies all the way down to a *single* example, not
just to the `tutorials/` folder as a unit. Every
`tutorials/NN_name/CMakeLists.txt` now has its own
`cmake_minimum_required()` + `project(...)` + `include()` of both
shared `cmake/` modules, exactly like `tutorials/CMakeLists.txt`
itself — so `cd tutorials/01_hello_world && cmake -S . -B build &&
cmake --build build` works with **no** other step first, from a clean
checkout.

Making this work without a duplicate-target error when
`tutorials/CMakeLists.txt` still `add_subdirectory()`s all three (its
own `include(BuildReflectionLibrary.cmake)` runs, then each child's
runs again) required one change: `BuildReflectionLibrary.cmake` is now
guarded with `if(NOT TARGET Reflection)`, so whichever CMakeLists.txt
processes first defines the target and every subsequent `include()` of
it — from a parent or a nested `project()` in a child during the same
configure — is a harmless no-op. Nested `project()` calls within a
single configure run are legal in CMake (used by any multi-project
tree); the only mildly informed choice was giving each tutorial its
own `project()` name (e.g. `HelloWorldTutorial`) so they don't collide
with `ReflectionTutorials` or with each other by name.

Verified all three usage modes still work after this change: the root
project, `tutorials/` building all three at once, and each
`tutorials/NN_name/` built completely on its own from its own nested
`build/` directory. (Also re-verified later, when a fourth tutorial —
`04_dwarf_arrays` — was added: see
[0013](0013-dwarf-based-reflection-generation.md)'s "Fixed bugs" for a
real cmake include-path bug this exact three-level structure surfaced,
unrelated to this ADR's own decisions but found by exercising them.)

## Consequences

- Building the library (`cmake -S . -B build` at the repo root) never
  builds tutorials as a side effect, and building/trying out a
  tutorial — the whole `tutorials/` folder, or just one example — never
  requires configuring the root project (or `tutorials/` itself) first.
  Each of the three levels (root, `tutorials/`, `tutorials/NN_name/`)
  is independently `cmake -S . -B build`-able on its own.
- `cmake/` is a new additive top-level folder (see
  [0006](0006-build-system-and-qnx-portability.md)), holding the shared
  modules every one of those independent projects includes.
