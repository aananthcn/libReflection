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

## Decision

Write a tiny (~40 line) in-repo test harness (`tests/TestFramework.hpp`)
instead of vendoring a third-party framework: a `TEST_CASE(Name){...}`
macro that self-registers into a static list, and a `REQUIRE(expr)`
macro that records a failure with file/line and keeps running.
`tests/test_main.cpp` runs every registered case and returns non-zero
if anything failed. `tests/` is a single flat unit-test suite (not
numbered) — see [0011](0011-tests-vs-tutorials.md) for why example
applications live in a separate `tutorials/` folder instead of inside
`tests/`.

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
  sensitivity to reordering (per [0002](0002-class-hash-algorithm.md)),
  and enum/bit-flag value round-tripping (per
  [0005](0005-enum-and-bitflag-reflection.md)).
