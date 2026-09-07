# libReflection

A minimal, dependency-free C++20 static reflection library, buildable
on Linux and QNX SDP 8.0, whose API shape is designed to be replaceable
by real C++26 static reflection later without changing call sites.

The full design rationale — every non-obvious decision below, and why —
lives in [`docs/adr/`](docs/adr/README.md). This README is the
practical how-to; read the ADRs for the "why."

## Building

### Linux (native)

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
ctest --test-dir build
```

Configure the library itself (and `tests/`) from this top-level
directory — `tests/` is not a standalone CMake project, it only works
pulled in via this root `CMakeLists.txt`'s `add_subdirectory()`.
`tutorials/` is different: it's a deliberately standalone project of
its own (see [Tutorials](#tutorials) below) — build it from
`tutorials/`, not from here. Individual tutorial subdirectories
(`tutorials/01_hello_world/`, etc.) are, like `tests/`, not standalone
on their own; running `cmake ..` directly inside one of those will
silently "succeed" at configure time (CMake just warns and treats it
as its own tiny project) and then fail to compile with a
missing-header error.

### QNX SDP 8.0 (cross-compile)

Requires QNX SDP 8.0 installed and its environment sourced first
(provides `QNX_HOST`/`QNX_TARGET` and the per-target compilers on
`PATH`):

Pick the target architecture with a plain environment variable — no
file to edit, no CMake code to write, for either target:

```sh
source /path/to/qnx800/qnxsdp-env.sh

export QNX_ARCH=aarch64     # or x86_64
cmake -S . -B build-qnx \
    -DCMAKE_TOOLCHAIN_FILE="$(pwd)/cmake/qnx-toolchain.cmake" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build-qnx
```

[`cmake/qnx-toolchain.cmake`](cmake/qnx-toolchain.cmake) is vendored
by this library (a deliberate, verified exception to
[docs/adr/0006](docs/adr/0006-build-system-and-qnx-portability.md)'s
original "toolchain is external" stance). `QNX_ARCH` defaults to
`aarch64` if unset; `-DCMAKE_SYSTEM_PROCESSOR=x86_64|aarch64` also works
and takes precedence over `QNX_ARCH` if both are given (useful for a
CI matrix that already sets `CMAKE_SYSTEM_PROCESSOR` some other way).
Verified end to end (full pipeline, including the DWARF reflection
generator below) against a real QNX SDP 8.0 install for both
architectures via both selection methods; see
[docs/adr/0013](docs/adr/0013-dwarf-based-reflection-generation.md).

Tests build for the target too (`ReflectionTests`); running them
requires copying the binary to a QNX target/simulator, since ctest
runs on the build host.

**If you write your own QNX toolchain file instead** (a different SDP
version, a different target triple), point `CMAKE_C_COMPILER`/
`CMAKE_CXX_COMPILER` at the per-target GNU-triple-named binaries
(e.g. `x86_64-pc-nto-qnx8.0.0-g++`), not at the `qcc`/`q++` wrappers.
CMake derives `CMAKE_OBJDUMP` — which
`cmake/GenerateDwarfReflection.cmake` needs to read the right target's
DWARF — from the compiler name: a GNU-triple name resolves correctly
to the matching `<triple>-objdump`, while `qcc`/`q++` can silently
fall back to the host's own `objdump`, which reads the wrong target
and produces wrong or missing reflection data.

## Running the tests

`tests/` is a single automated unit-test suite (`ReflectionTests`)
covering member offsets/sizes, nested structs, fixed arrays,
`ClassHash` behavior, enum/bit-flag values, and registry lookups.

```sh
ctest --test-dir build --output-on-failure
```

Or run the binary directly for full per-case output:

```sh
./build/tests/ReflectionTests
```

## Tutorials

[`tutorials/`](tutorials/README.md) holds numbered example applications
demonstrating the library end to end. It's a **standalone CMake
project** — not part of this repo's main build, not built by the
instructions above — because a tutorial is meant to be a place a human
builds and tries things out independently, not something dragged along
every time the library itself is built (see
[docs/adr/0011](docs/adr/0011-tests-vs-tutorials.md)). It has no
dependency on the root project having been configured or built first:

```sh
cd tutorials
cmake -S . -B build
cmake --build build

./build/01_hello_world/01_hello_world
./build/02_auto_reflect_legacy_struct/02_auto_reflect_legacy_struct
./build/03_macros_for_special_cases/03_macros_for_special_cases
```

Each numbered subdirectory is independently standalone too — e.g.
`cd tutorials/01_hello_world && cmake -S . -B build && cmake --build build`
works on its own, with no other step first, if you only want to try
out one.

## Packaging a release

See [`release/README.md`](release/README.md).

## Usage

**Default: automatic reflection, zero annotation.** Any plain
aggregate (public members, no user-declared constructors/virtuals, no
direct fixed-size array member) reflects with no
`REFLECT_CLASS_BEGIN` block at all — member offsets, sizes, types, and
count are derived automatically from the type itself, with nothing to
write and nothing to keep in sync:

```cpp
#include <Reflection.hpp>

// Some struct from an existing codebase -- unmodified, unannotated,
// no separate registration file either.
struct LegacyVector3 { float x; float y; float z; };

const auto& r = reflect::Reflect<LegacyVector3>();
r.GetMembers().size();               // 3
r.GetMembers()[0].GetOffset();       // 0

// Runtime lookup by hash (e.g. off a shared-memory region), not the
// compile-time type. FindByName does NOT work here -- see below.
reflect::FindByHash(r.GetHash());
```

The trade-off: type and member names are positional
(`"<aggregate>"`, `"field0"`, `"field1"`, ...) rather than the real
source names, since nothing in a compiled C++ program records those.
A struct with a direct fixed-size array member can't use this path at
all — it fails to compile with a clear message pointing at
`REFLECT_CLASS_BEGIN` instead of silently producing wrong offsets.
Walkthrough: [`tutorials/02_auto_reflect_legacy_struct/`](tutorials/02_auto_reflect_legacy_struct/README.md).

*(A text-scanning tool that generated real names automatically for
this case was built, verified working, and then reverted because its
premise — that plain aggregates are representative of a real legacy
codebase — was wrong; see
[docs/adr/0012](docs/adr/0012-generated-reflection-names.md).)*

### Real names, even for private members: the DWARF pipeline

[docs/adr/0013](docs/adr/0013-dwarf-based-reflection-generation.md)'s
DWARF-based pipeline resolves the real name of **any** type — a plain
aggregate, a class with a user-declared constructor, one with private
members, any combination — with **zero annotation**, by compiling the
source a second time with debug info and reading the real
name/type/offset/size straight out of DWARF, which doesn't respect
C++ access control (a debugger can already inspect a private field;
the compiler emits the data unconditionally). Wired up automatically
via `cmake/GenerateDwarfReflection.cmake`:

```cmake
# In your CMakeLists.txt:
include("${REFLECTION_ROOT_DIR}/cmake/GenerateDwarfReflection.cmake")
add_executable(my_app main.cpp)
target_link_libraries(my_app PRIVATE Reflection)
reflection_generate_dwarf(TARGET my_app SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/main.cpp")
```

```cpp
// main.cpp -- no annotation on PoorPoint at all, private members included
class PoorPoint {
public:
    PoorPoint() : x{}, y{} {}
private:
    int x;
    int y;
};

#include "generated_dwarf_reflection.hpp"  // after all type definitions in this file

const auto& r = reflect::Reflect<PoorPoint>();
r.GetClassName();                 // "PoorPoint", not "<unregistered>"
r.FindMember("x")->GetOffset();   // 0 -- the real, private member
```

One `cmake --build` runs the whole pipeline; adding a brand-new type
to `main.cpp` resolves correctly on the next build with no other
change. Walkthrough: [`tutorials/01_hello_world/`](tutorials/01_hello_world/README.md).

### The escape hatch: `REFLECT_CLASS_BEGIN`/`REFLECT_ENUM_BEGIN`

Needed for: **enums** (always — there's no automatic path for enum
value names), **a direct fixed-size array member** (the DWARF pipeline
above doesn't correctly resolve one yet either — see
[docs/adr/0013](docs/adr/0013-dwarf-based-reflection-generation.md)'s
"Known open risks"), and whenever **real, distinguishable names/
identity** matter (two different but structurally identical
auto-reflected types would otherwise hash identically — see
[docs/adr/0001](docs/adr/0001-reflection-generation-strategy.md)).
Reaches public members only without a `friend` declaration — see the
DWARF pipeline above for the non-intrusive private-member path.

**Not the accepted final answer for enums or array members either** —
same as the private-member case the DWARF pipeline above already
eliminated, both are addressable by extending that same pipeline
(DWARF already records an enum's named values and an array's element
type/count, unconditionally), just not done yet; see
[docs/adr/0013](docs/adr/0013-dwarf-based-reflection-generation.md)'s
"Future work" section.

```cpp
#include <Reflection.hpp>

struct Vec3 { float x, y, z; };
REFLECT_CLASS_BEGIN(Vec3)
    REFLECT_MEMBER(x)
    REFLECT_MEMBER(y)
    REFLECT_MEMBER(z)
REFLECT_CLASS_END()

enum class Color { Red, Green, Blue };
REFLECT_ENUM_BEGIN(Color)
    REFLECT_ENUM_VALUE(Red)
    REFLECT_ENUM_VALUE(Green)
    REFLECT_ENUM_VALUE(Blue)
REFLECT_ENUM_END()

const auto& r = reflect::Reflect<Vec3>();
r.GetMembers().size();            // 3
r.FindMember("y")->GetOffset();   // offsetof(Vec3, y)

// Only macro-registered types resolve by name:
reflect::FindByName("Vec3");
reflect::FindByHash(r.GetHash());
```

Walkthrough: [`tutorials/03_macros_for_special_cases/`](tutorials/03_macros_for_special_cases/README.md).

### Ordering rule

A member's type must be `REFLECT_*`'d *before* the struct that embeds
it, in the same translation unit (or an included header) — reflect
leaf/nested types first, then the types that contain them. See
[docs/adr/0010](docs/adr/0010-header-and-macro-sketch.md) for why.

### What's reflectable in v1

Primitives, `std::string` (opaque leaf), fixed-size C arrays,
`std::array<T, N>`, nested structs (macro-registered or plain
aggregates — see above), and `REFLECT_ENUM_BEGIN`/
`REFLECT_BITFLAG_ENUM_BEGIN`'d enums. Pointers and references reflect
as opaque leaves (never dereferenced). Dynamic containers
(`std::vector`, `std::map`, ...) and classes with virtual base classes
are out of scope. See
[docs/adr/0004](docs/adr/0004-member-representation-scope.md) for the
full reasoning.

**If a struct crosses a process boundary over shared-memory IPC**
(this project's cross-process IPC mechanism), keep it to the member
kinds above — anything heap-owning (`std::string`, pointers, dynamic
containers) is meaningless once copied into another process's address
space. See
[docs/adr/0009](docs/adr/0009-versioning-and-hash-purpose.md).

## Folder layout

```
.
├── build/            # local build output (gitignored)
├── cmake/            # shared modules included by both CMakeLists.txt below
├── CMakeLists.txt
├── docs/adr/         # design decisions and their rationale
├── README.md
├── release/          # release scripts/docs (tracked) + dist/ (gitignored artifacts)
├── src/              # public headers + implementation, flat (no include/ split)
├── tests/            # ReflectionTests: the automated unit-test suite (part of this build)
├── tools/            # generate_aggregate_tie.py, generate_dwarf_reflection.py + tests
├── tutorials/        # standalone sandbox project (own build/, own CMakeLists.txt) -- see tutorials/README.md
└── version.txt       # bare MAJOR.MINOR.PATCH version string; CMakeLists.txt parses this
```
