# 0006 — Build System & QNX SDP 8.0 Portability

**Status:** Decided

## Context

ARCHITECTURE.md fixes the top-level folder layout (`build/`,
`CMakeLists.txt`, `README.md`, `release/`, `src/`, `version.txt`) and
requires CMake + C++20 + Linux/QNX SDP 8.0. It doesn't say how the QNX
cross-toolchain is supplied, what `release/` and `version.txt` are for
mechanically, or whether the given tree is exhaustive.

## Decision

- **CMake baseline:** `cmake_minimum_required(VERSION 3.20)`,
  `add_library(Reflection STATIC ...)`,
  `target_compile_features(Reflection PUBLIC cxx_std_20)`,
  `set(CMAKE_CXX_EXTENSIONS OFF)`. Output artifact name `libReflection.a`
  as specified.
- **QNX toolchain: a reference file is vendored, revising this ADR's
  original stance.** This ADR originally said the toolchain file was
  purely external — the caller's own SDP-provided
  `qnx.nto.toolchain.cmake`. That was never actually verified; when
  [0013](0013-dwarf-based-reflection-generation.md)'s DWARF pipeline
  was tested against a real QNX SDP 8.0 install, a real, non-obvious
  requirement surfaced: `cmake/GenerateDwarfReflection.cmake` needs
  CMake's `CMAKE_OBJDUMP` to resolve to the *target*-specific
  `objdump`, which CMake only derives correctly when the toolchain
  file names the compiler using its GNU-triple form (e.g.
  `x86_64-pc-nto-qnx8.0.0-g++`) rather than the `qcc`/`q++` wrappers —
  with the wrappers, `CMAKE_OBJDUMP` was observed to silently fall
  back to the *host's* `objdump`, which reads the wrong target. Since
  this is a specific, easy-to-get-wrong requirement of this library
  rather than generic QNX/CMake knowledge, `cmake/qnx-toolchain.cmake`
  is now vendored as a verified-working reference. Switching target
  architecture is a plain `export QNX_ARCH=x86_64|aarch64` before
  configuring — no toolchain-file edit, no per-target CMake code —
  with `-DCMAKE_SYSTEM_PROCESSOR=x86_64|aarch64` also accepted and
  taking precedence if both are given. This still assumes the caller
  has sourced QNX SDP 8.0's environment (`qnxsdp-env.sh`) first so the
  named compiler binaries are on `PATH`. A caller may still supply
  their own toolchain file instead (a different SDP version, a
  different target) as long as it follows the same GNU-triple
  convention; README.md documents both paths.
- **`version.txt`** holds a bare `MAJOR.MINOR.PATCH` version string
  (e.g. `0.1.0` — no `v` prefix, per user confirmation), the single
  source of truth for the library's version. `CMakeLists.txt` reads it
  via `file(STRINGS ...)` and requires an exact `^[0-9]+\.[0-9]+\.[0-9]+$`
  match (`FATAL_ERROR` otherwise) to feed `project(Reflection VERSION ...)`;
  the same string is also embedded verbatim as `reflect::kVersionString`
  for display/telemetry.
- **`release/`** is a source-tracked folder for release-specific
  **scripts and documents**, plus the destination for packaged release
  **artifacts** (binaries). It is not merely a CMake
  `CMAKE_INSTALL_PREFIX`: `release/scripts/package.sh` is a checked-in
  script that invokes `cmake --install` into a versioned, gitignored
  `release/dist/` subfolder and tars the result — so the scripts/docs
  under `release/` are tracked, while the binaries `package.sh`
  produces under `release/dist/` are not (they're build output, kept
  out of git the same way `build/` is).
- **Folder layout deviations from ARCHITECTURE.md, all additive:**
  - `tests/` (not in the original tree) — required to verify the
    library at all; see [0007](0007-testing-strategy.md).
  - `tutorials/` — numbered example applications, kept separate from
    `tests/` *and built as its own standalone CMake project*, not part
    of this build at all; see [0011](0011-tests-vs-tutorials.md) for why.
  - `cmake/` — `ParseReflectionVersion.cmake`/`BuildReflectionLibrary.cmake`,
    the shared modules both this `CMakeLists.txt` and
    `tutorials/CMakeLists.txt` include so "how to build libReflection"
    has one definition despite being two independent top-level
    projects; see [0011](0011-tests-vs-tutorials.md). Also
    `GenerateDwarfReflection.cmake` (the [0013](0013-dwarf-based-reflection-generation.md)
    pipeline) and `qnx-toolchain.cmake` (the vendored QNX SDP 8.0
    reference toolchain file, see above). (A now-removed module,
    `GenerateReflectionNames.cmake`, briefly lived here for
    [0012](0012-generated-reflection-names.md)'s codegen tool; removed
    when that ADR was reverted.)
  - `docs/` — this ADR set, plus the header/macro sketch.
  - No separate `include/` under `src/`: public headers live directly
    under `src/` alongside their `.cpp` files (matches the tree exactly
    as given — a single-directory small library layout), with
    `target_include_directories(Reflection PUBLIC src)`.

## Consequences

- Anyone building for QNX needs SDP 8.0 installed and its environment
  sourced; this library adds no QNX-specific CMake logic of its own
  beyond being toolchain-file-agnostic C++20.
- The four additive folders (`tests/`, `tutorials/`, `cmake/`, `docs/`) don't
  conflict with anything ARCHITECTURE.md's tree names — they're pure
  additions, called out here so they don't read as scope creep later.
