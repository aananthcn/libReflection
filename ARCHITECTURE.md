# Foundational Requirements
1. Create a libReflection.a, CMake based, that uses C++20, should be buildable on Linux and QNX (SDP 8.0). 
2. The core of the library is around the following interface class:
   ```
   class ClassHash {
        uint64_t words[4]; // 4 * 64 bits = 256 bits
    };

    class ClassReflection
    {
      public:
        using MemberList = std::vector<ClassReflection>;
        using EnumValues = std::unordered_map<std::string, std::int64_t>;
    
        /**
         * @brief Construct a new Class Reflection object
         */
        ClassReflection()
        : name(""),
          type(""),
          offset(0),
          size(0),
          count(1),
          members(),
          hash{0, 0, 0, 0},
          enum_name(""),
          enum_values(),
          bit_flag(false) {}

      public:
        std::string name;
        std::string type;
        std::uint32_t offset;
        std::uint32_t size;
        std::uint32_t count;
        MemberList members;
        ClassHash hash;
        std::string enum_name;
        EnumValues enum_values;
        bool bit_flag;
    };
	```
3. Add public member functions to access these members.
4. The goal of this implementation should match with or realize C++26 reflections but compilable on C++20 and usable on code without following the syntaxes or keywords that will be introduced in C++26.  This means this class must abstract the future C++26 methods and members, but has to be simple. In that respect modify (add or remove) member variables / functions or modify their types to get a minimal implementation working and usable.



# Top Level Folder
| Path | Purpose |
|---|---|
| `ARCHITECTURE.md` | This file — the foundational requirements the library was built to, and reference material (module/tool tables below) for finding your way around the codebase. |
| `CMakeLists.txt` | The root CMake build: defines the `Reflection` static library target, its C++20/QNX-portability settings, `version.txt` → `Version.hpp` generation, and (via `REFLECTION_BUILD_TESTS`) wiring in `tests/`. |
| `README.md` | User-facing documentation: how to build (Linux and QNX SDP 8.0), how to use automatic/macro/DWARF-based reflection, and a tour of the escape hatches. Start here as a consumer of the library. |
| `version.txt` | The single source of truth for the library's version (bare `MAJOR.MINOR.PATCH`) — parsed by `cmake/ParseReflectionVersion.cmake` and substituted into `src/Version.hpp.in`. See docs/adr/0009. |
| `src/` | The library's own C++ source — see "C++ Modules" below for a file-by-file breakdown. Builds into `libReflection.a`. |
| `cmake/` | Reusable CMake modules: `BuildReflectionLibrary.cmake` (the `Reflection` target itself, shared between the root build and a standalone `tutorials/*` project), `GenerateDwarfReflection.cmake` (the `reflection_generate_dwarf()` DWARF pipeline, see docs/adr/0013), `ParseReflectionVersion.cmake` (reads `version.txt`), and `qnx-toolchain.cmake` (a vendored CMake toolchain file for cross-compiling to QNX SDP 8.0, see docs/adr/0006). |
| `tools/` | Python code generators (and their tests) the build depends on — see "Tools for Reflection" below for a tool-by-tool breakdown. |
| `tests/` | The unit test suite (`ReflectionTests`, run via `ctest`) covering basic/automatic/enum/hash/registry reflection — flat and unnumbered by design, part of the root build when `REFLECTION_BUILD_TESTS` is on. See docs/adr/0007. |
| `tutorials/` | Standalone, runnable, walkthrough example projects (`01_hello_world` through `04_dwarf_arrays`), each buildable on its own with no other step first — meant to be read and run, not asserted against like `tests/`. See docs/adr/0011. |
| `docs/adr/` | Architecture Decision Records — the project's actual design history and rationale (one numbered file per decision, e.g. why DWARF, why macros, versioning, QNX portability). The most detailed documentation in the repo; linked from throughout this file. |
| `release/` | Release process scripts and documentation (tracked in git) and the destination for packaged release artifacts (binaries, gitignored — see `release/dist/`). See docs/adr/0006. |
| `build/` *(gitignored)* | The default out-of-tree CMake build directory for the root project — not tracked, created by `cmake -S . -B build`. |


# C++ Modules
Each row below is one "module" in `src/` — a `.hpp` (plus a matching
`.cpp` where the module has out-of-line logic, not just declarations)
sharing one filename stem. Listed in dependency order (each module
includes only modules above it), which is also roughly the order a
reader should go through them in.

| Module | File(s) | Purpose |
|---|---|---|
| `ClassReflection` | `ClassReflection.hpp`, `ClassReflection.cpp` | The library's one core data structure — the C++20 stand-in for a C++26 reflection value. `ClassHash` is a 256-bit structural fingerprint (4× `uint64_t`); `ClassReflection` is the recursive description of a type's shape (name, type, offset, size, count, its own `ClassHash`, a member list of more `ClassReflection`s, and enum-specific fields). Fields are public but read elsewhere only through `Get*()`/`Is*()` accessors. `FindMember()` (direct, non-recursive by-name lookup) is the one out-of-line piece of logic. Also defines `kAutoAggregateTypeName`, the `"<aggregate>"` sentinel for annotation-free aggregates, shared with `AggregateReflection` and `ReflectionRegistry`. See docs/adr/0002, docs/adr/0003. |
| `ReflectionFwd` | `ReflectionFwd.hpp` | Just a forward declaration of `Reflect<T>()`, so `AggregateReflection.hpp` can call it from inside a template body without waiting for `TypeInfo.hpp`'s full definition — breaks what would otherwise be a `TypeInfo.hpp` ⇄ `AggregateReflection.hpp` circular `#include`. |
| `AggregateTie.generated` | `AggregateTie.generated.hpp` | Auto-generated by `tools/generate_aggregate_tie.py` — do not edit by hand. Provides `TieMembers(T&, std::integral_constant<std::size_t, N>)` overloads for every `N` from 0 to 64, each decomposing `T` via a structured binding of exactly `N` names into a `std::tie()`. One overload per count because a structured binding's arity must be a source-level literal, not a template parameter. See docs/adr/0014 for the code-generation decision and why the field cap starts at 64; docs/adr/0001 for the automatic-aggregate path it serves. |
| `AggregateReflection` | `AggregateReflection.hpp` | The mechanism behind *automatic*, zero-annotation reflection for a plain aggregate with no `REFLECT_CLASS_BEGIN` block. Finds member count by binary-searching (via `FieldCountSearch`/`BraceOk`/`ParenOk`) the largest `N` a "universal type" can brace/paren-construct `T` with, cross-checking C++20 paren-init (P0960) against brace-init to detect — and refuse via `static_assert`, never mis-count — a direct fixed-size array member. Recovers member offsets/sizes/types, but never real names (`"field0"`, `"field1"`, ... — nothing compiled records a member's source name) or enum value names. Caps at `kMaxAggregateFields` (64) direct members — a loud `static_assert` past that, not a mis-count; see docs/adr/0014 for why 64. See docs/adr/0001. |
| `ReflectionHash` | `ReflectionHash.hpp`, `ReflectionHash.cpp` | Computes `ClassReflection::hash` — a non-cryptographic FNV-1a-based 256-bit fingerprint used to detect layout drift between independently-built processes sharing a struct over shared-memory IPC. `ComputeHash()` hashes a canonical string of a reflection's own shape plus each member's name/offset/already-computed hash (not a recursive walk of the member's own members), 4× with 4 seeds. `ValidateEnum()` also lives here: a debug-only assertion that every bit-flag enum value is 0 or a power of two. See docs/adr/0002, docs/adr/0005. |
| `ReflectionRegistry` | `ReflectionRegistry.hpp`, `ReflectionRegistry.cpp` | The process-wide, mutex-guarded runtime lookup (`FindByHash`/`FindByName`) from a `ClassHash` or type name back to a `ClassReflection`, backed by a function-local `static` (C++11 "magic statics" — thread-safe, exactly-once init) and populated lazily as `Reflect<T>()` is called. Auto-reflected aggregates are excluded from the by-name index (they'd all collide under the shared `kAutoAggregateTypeName` key) but stay reachable via `FindByHash()`. See docs/adr/0008. |
| `TypeInfo` | `TypeInfo.hpp` | The customization point (`TypeInfo<T>`) every reflection goes through, and `Reflect<T>()`, the library's primary entry point. The primary template dispatches to automatic aggregate reflection or an opaque-leaf description via `TypeName<T>()` (deliberately not `typeid(T).name()`, to avoid forcing RTTI on `-fno-rtti` builds). Built-in specializations cover `std::string`, `T[N]`, `std::array<T, N>`, and `T*`. `REFLECT_*` macros work by fully specializing this same template, always taking precedence. `Reflect<T>()` computes, hashes, and registers a type exactly once, on first use. See docs/adr/0004, docs/adr/0010. |
| `ReflectionMacros` | `ReflectionMacros.hpp` | The manual registration DSL for what automatic reflection can't reach. `REFLECT_CLASS_BEGIN`/`REFLECT_MEMBER`/`REFLECT_CLASS_END` hand-annotate a type via `decltype`/`offsetof` (access-checked, public members only). `REFLECT_DWARF_CLASS_BEGIN`/`REFLECT_DWARF_MEMBER`/`REFLECT_DWARF_CLASS_END` are the machine-generated counterpart (by `tools/generate_dwarf_reflection.py`): every value is a literal straight from DWARF, never an access-checked expression, reaching private members too; `Type` is deliberately the trailing variadic argument so a template instantiation's top-level comma survives macro parsing intact. `REFLECT_ENUM_BEGIN`/`REFLECT_BITFLAG_ENUM_BEGIN`/`REFLECT_ENUM_VALUE`/`REFLECT_ENUM_END` register enum value names. See docs/adr/0001, docs/adr/0005, docs/adr/0010, docs/adr/0013. |
| `Version` | `Version.hpp.in` | Not a header itself — a CMake `configure_file()` template. `CMakeLists.txt` substitutes `version.txt`'s parsed major/minor/patch/raw values into it at configure time, writing the result as `Version.hpp` into the build tree's generated-headers directory — the only "module" whose real header isn't in `src/` at all. See docs/adr/0009. |
| `Reflection` | `Reflection.hpp` | The single public entry point (`#include <Reflection.hpp>`), pulling together `ClassReflection`, `ReflectionMacros`, `ReflectionRegistry`, `TypeInfo`, and the generated `Version.hpp` behind one include. See docs/adr/0010, README.md. |



# Tools for Reflection
`tools/` holds the Python-based code generators (and their tests) the
build depends on — CMake invokes these automatically; they are not
normally run by hand except to regenerate a checked-in file after a
deliberate change.

| Tool | Purpose | Invocation |
|---|---|---|
| `generate_aggregate_tie.py` | Generates `src/AggregateTie.generated.hpp`'s `TieMembers()` overloads (N = 0..`MAX_FIELDS`, 64 by default) — one per structured-binding arity, since arity can't be templated in standard C++20. A one-time/rare-regeneration generator, not run during a normal build; its output is checked in. `MAX_FIELDS` here must stay equal to `kMaxAggregateFields` in `src/AggregateReflection.hpp`. See docs/adr/0014 (the decision, and why the cap starts at 64); docs/adr/0001 for the path it serves. | `python3 tools/generate_aggregate_tie.py > src/AggregateTie.generated.hpp` (only after changing `MAX_FIELDS`) |
| `generate_dwarf_reflection.py` | The DWARF-based reflection pipeline (docs/adr/0013): discovers `struct`/`class` names — and template instantiations, including nested ones (`Box<Box<int>>`) — in a source file and its local includes; emits a throwaway "driver" `.cpp` that touch-instantiates each discovered type to force full DWARF emission; reads the compiled driver object's `objdump --dwarf=info` output; and generates a `REFLECT_DWARF_CLASS_BEGIN`/`REFLECT_DWARF_MEMBER`/`REFLECT_DWARF_CLASS_END` header with literal name/type/offset/size/count values straight from debug info — reaching private members and non-aggregates with zero source annotation, since DWARF doesn't respect C++ access control. Driven automatically by CMake (`cmake/GenerateDwarfReflection.cmake`'s `reflection_generate_dwarf()`), not normally invoked directly. | `--emit-driver <source.cpp> <driver.cpp>` and `--extract <object.o> <source.cpp> <output.hpp> [--objdump <path>]` |
| `test_generate_dwarf_reflection.py` | The Python test suite for `generate_dwarf_reflection.py` (46 tests): pure text-scanning unit tests (discovery, driver emission, argument normalization) plus end-to-end tests that actually compile a fixture with a real compiler, extract its DWARF, and check the generated registration — the ones that matter most, since the whole point of the tool is what a real compiler's debug info says. Skips its end-to-end tests if `g++`/`objdump` aren't on `PATH`. Run automatically via `ctest` as `GenerateDwarfReflectionPyTest`. | `python3 -m unittest tools/test_generate_dwarf_reflection.py`, or via `ctest -R GenerateDwarfReflectionPyTest` |
