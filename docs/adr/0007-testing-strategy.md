# 0007 — Testing Strategy

**Status:** Decided

## Context

ARCHITECTURE.md's folder tree has no `tests/` entry, but a reflection
library with recursive layout math, hashing, and macro expansion needs
verification — this is exactly the kind of code where a subtle bug
(wrong offset, wrong hash on reorder) is easy to write and easy to miss
without automated tests. The main constraint is that whatever test
framework is chosen must also run on the QNX SDP 8.0 target, and the
QNX cross-build environment cannot be assumed to have network access
(embedded/CI cross-compile environments frequently are air-gapped).

Two different things needed a home early on: this automated unit-test
suite, and numbered, runnable example applications demonstrating the
library end to end (the "hello world" of using libReflection, and
onward as `02_xxx`, `03_xxx`, ...). These were first split into a
similarly-named `test/` (examples) vs. `tests/` (unit suite) pair,
which in practice was too easy to confuse — files ended up merged into
the wrong one, and folders had to be untangled more than once before
landing on separate, visibly-distinct names: `tests/` (this ADR) and
`tutorials/` (see [0011](0011-tutorials-and-their-purpose.md) —
`tutorials/` was chosen specifically because it can't be confused with
`tests/` by a near-identical name, unlike the earlier `test/`/`tests/`
pair, which had no plural/singular distinction to misread or mistype).

## Decision

Write a tiny (~40 line) in-repo test harness (`tests/TestFramework.hpp`)
instead of vendoring a third-party framework: a `TEST_CASE(Name){...}`
macro that self-registers into a static list, and a `REQUIRE(expr)`
macro that records a failure with file/line and keeps running.
`tests/test_main.cpp` runs every registered case and returns non-zero
if anything failed.

`tests/` is exactly one thing: the flat `ReflectionTests` unit-test
suite (`test_main.cpp`, `test_*.cpp`, `TestFramework.hpp`) — not
numbered, no subfolders, nothing else. It is part of the root
project's build: anyone building the library gets it built and
registered with `ctest` automatically (`REFLECTION_BUILD_TESTS`,
default `ON`, in the root `CMakeLists.txt`). Example applications
belong in `tutorials/` instead — see
[0011](0011-tutorials-and-their-purpose.md) for why that's a
completely separate, standalone project rather than more subfolders
under `tests/`.

Revised from the original plan to vendor Catch2. Reasoning: this
project's test needs are plain assertions (offset/hash/enum-value
checks), not Catch2's BDD sections/matchers/generators, so a ~40-line
harness covers 100% of what's actually used; and it avoids committing a
large third-party amalgamated header (or fetching one over the network
during this build-out) for a QNX SDP 8.0 target where minimizing both
dependencies and code size is already a stated goal
(ARCHITECTURE.md item 4). `FetchContent`/`find_package(GTest)` were
already rejected for the network/pre-installed-package assumption; a
vendored Catch2 header remains a reasonable fallback if test needs grow
past plain assertions later.

## Consequences

- No file should ever need to move between `tests/` and `tutorials/`
  based on a naming mixup — they serve visibly different purposes
  (verification vs. demonstration) and have visibly different names,
  not just similarly-named folders like the original `test/`/`tests/`
  pair.
- `tests/` builds a single `ReflectionTests` executable, linked
  against `Reflection` and the header-only in-repo harness — zero
  third-party code, no extra runtime dependency ships in
  `libReflection.a` itself.
- Tests run identically under native Linux and, given a QNX target
  with a way to execute binaries (real hardware, simulator, or QEMU),
  under QNX — the harness's only requirement is a C++20 compiler.
- No fancy failure reporting (diffs, matchers) — `REQUIRE` just prints
  the failed expression and location. Sufficient for this test surface;
  revisit if test complexity grows.
- Minimum test coverage before calling v1 done: offset/size/count
  correctness for nested structs and arrays, `ClassHash` stability and
  sensitivity to reordering (per [0002](0002-class-hash-algorithm-and-purpose.md)),
  and enum/bit-flag value round-tripping (per
  [0005](0005-enum-and-bitflag-reflection.md)).
