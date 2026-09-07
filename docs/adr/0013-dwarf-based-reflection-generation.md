# 0013 — DWARF-Based Reflection Generation

**Status:** Implemented and verified — on the Linux host, via the QNX
SDP 8.0 cross-toolchain (`x86_64` and `aarch64`), and by running on a
real QNX 8.0 aarch64 device (not just cross-compiled). 26 Python tests
in `tools/test_generate_dwarf_reflection.py`. See "Fixed bugs" for the
virtual-base-class bug (a serious one — silently zero members) and the
vtable-pointer exposure, both now fixed, and "Known limitations" for
what's still open.

## Context

[0012](0012-generated-reflection-names.md) was reverted: no macro-based
mechanism, hand-written or generated, can reach a private member
without a `friend` declaration — a source change this project rules
out, and ordinary encapsulation (private data behind a constructor) is
the *typical* shape of a real C++ class, not an edge case.

This ADR answers: can an arbitrary class — including private members —
be reflected without modifying its source at all? Yes, via DWARF debug
info.

## Why DWARF

C++ access control is a compile-time, source-level concept only — the
compiled memory layout is identical regardless of access, which is why
a debugger can already inspect a private field. DWARF debug info
records every data member's name, type, and offset unconditionally, no
`DW_AT_accessibility` gate on reading it. Unlike source-text scanning
or `decltype`/`offsetof`-based macros (C++ expressions, still
access-checked), reading DWARF never asks the compiler's access
checker anything — it reads compiler-emitted metadata about the
already-compiled result.

Confirmed directly: `g++ -g -gdwarf-4 -c` on a class with private
members, inspected via `objdump --dwarf=info`, shows every private
member's real name/type/offset with no special flags:

```
DW_TAG_class_type: DW_AT_name: EncapsulatedPoint, DW_AT_byte_size: 8
  DW_TAG_member: DW_AT_name: x_, DW_AT_type: int,   DW_AT_data_member_location: 0
  DW_TAG_member: DW_AT_name: y_, DW_AT_type: float, DW_AT_data_member_location: 4
```

## How it works

1. **Discover** type names: `tools/generate_dwarf_reflection.py`
   regex-scans `SOURCE` and every local (`"..."`, never `<...>`)
   header it `#include`s transitively for top-level `struct`/`class`
   declarations. Only needs NAMES — DWARF handles everything about
   what's inside them. Templated declarations are excluded (can't be
   touch-instantiated without knowing the template argument); enums
   are not discovered yet (see "Future work").
2. **Emit a driver**: a throwaway `.cpp` that `#include`s `SOURCE` and
   declares one instance of each discovered type, to force the
   compiler to emit that type's *full* DWARF (a type merely named in
   `sizeof()` is not guaranteed full debug output — verified). Each
   instance is a union wrapper with a no-op default constructor/
   destructor (`union Touch_T { T value; char dummy; Touch_T():dummy(0){} ~Touch_T(){} };`),
   not a plain `T touch_T;`, so it compiles even for a type whose only
   constructor requires arguments. A type inheriting from a polymorphic
   base needs one more push beyond just being a union member: the
   driver also emits a never-invoked `NeverCalled_T()` function that
   explicitly destroys the union member via a small
   `ForceFullDwarf<T>` template (guarded by `std::is_destructible_v<T>`
   so a deleted/inaccessible destructor can't turn this into a hard
   compile error) — see "Fixed bugs" for why this specific push is
   needed and why the destructor, not the constructor, is what's
   called.
3. **Compile the driver** as a real CMake `OBJECT` library target,
   mirroring the real target's own `COMPILE_DEFINITIONS`/
   `INCLUDE_DIRECTORIES`/`COMPILE_OPTIONS` on top of a fixed
   `-std=c++20 -g -gdwarf-4` floor and this pipeline's own required
   include paths — see "Fixed bugs" for why mirroring the real
   target's settings matters and how it's actually done (not by
   hand-splicing a command string, which doesn't reliably work).
4. **Extract**: parse the driver object's DWARF via
   `objdump --dwarf=info` / `readelf --debug-dump=info` text output —
   chosen over `pyelftools` (a new pip dependency) or a hand-rolled
   `.debug_info` parser (high effort, high bug risk) specifically
   because both tools already ship with the C/C++ toolchain this
   project already requires, on both Linux and QNX SDP 8.0.
5. **Generate** `REFLECT_DWARF_CLASS_BEGIN`/`REFLECT_DWARF_MEMBER`/
   `REFLECT_DWARF_CLASS_END` (`src/ReflectionMacros.hpp`) with
   name/type/offset/size/count as **literal** values — never
   `decltype`/`offsetof` expressions. This is precisely what reaches a
   private member: nothing in the generated code is an
   access-checked expression.
6. **Wire into the real target's compile**: `cmake/GenerateDwarfReflection.cmake`'s
   `reflection_generate_dwarf(TARGET <t> SOURCE <src>)` runs steps 1–5
   as `add_custom_command` steps, ordered via `OBJECT_DEPENDS` so
   `<t>`'s real compile of `<src>` waits for the freshly generated
   header — one `cmake --build`, no manual step.

**Requirements on `SOURCE`:**
- Must `#include "generated_dwarf_reflection.hpp"` once, after all its
  type definitions — the same declare-before-use rule
  `REFLECT_CLASS_BEGIN`'s output follows (see
  [0010](0010-header-and-macro-sketch.md)).
- Must **not** itself call `reflect::Reflect<T>()` for a type automatic
  aggregate reflection would hard-fail to compile (e.g. a direct array
  member). Step 2's driver `#include`s `SOURCE` verbatim, so on a fresh
  build — before the generated header has real content — that call
  resolves against the *unspecialized* primary template instead, and
  the bootstrap compile fails. Keep such types' definitions in a
  separate header with no `Reflect<T>()` calls in it (see
  `tutorials/04_dwarf_arrays/ArrayTypes.hpp`); a type automatic
  reflection *can* describe (even with positional names) is unaffected.

## Verified

- **Linux host**: `tutorials/01_hello_world` — a plain aggregate, a
  non-aggregate with private members, a public-member class, and a
  type added after the pipeline was wired up, all resolving correctly
  from one `cmake --build`.
- **QNX SDP 8.0 cross-compile**, `x86_64` and `aarch64`, via a CMake
  toolchain file naming the compiler in GNU-triple form (e.g.
  `x86_64-pc-nto-qnx8.0.0-g++`). This matters: CMake's `CMAKE_OBJDUMP`
  auto-detection (needed so extraction reads the *target's* DWARF, not
  the host's) only resolves correctly with that naming convention —
  confirmed by contrast with a pre-existing QNX CMake project on this
  machine whose `qcc`/`q++`-based toolchain file causes `CMAKE_OBJDUMP`
  to silently fall back to the host's `objdump`.
  `cmake/qnx-toolchain.cmake` (vendored — see
  [0006](0006-build-system-and-qnx-portability.md)) follows this
  convention.
- **Real QNX 8.0 aarch64 hardware** (not a simulator, not just format
  checked): `tutorials/01_hello_world` and the full `ReflectionTests`
  suite were copied to and run directly on a real device — correct
  output, including `PoorPoint`'s private members, and all test cases
  passing natively.

## Known limitations, stated plainly

- **Templates are excluded from discovery entirely** — a templated
  type still needs a hand-written `REFLECT_CLASS_BEGIN`, or a future
  extension that knows which concrete instantiations to touch.
- **A truly unresolvable member's type is silently absent, not loudly
  flagged.** `find_type()` skips it with a
  `// <name>: type not resolved in DWARF info -- skipped, not guessed.`
  comment rather than a wrong literal (the right abstention), but
  nothing surfaces that comment as a build warning. Low risk in
  practice — the only case found is an unbounded/flexible array
  member, not standard C++ for a non-static data member.
- **No member-ordering risk** (unlike [0012](0012-generated-reflection-names.md)'s
  text scanner): DWARF gives an explicit, unambiguous offset per named
  member directly.

## Fixed bugs (history)

- **`objdump` was hardcoded, not toolchain-aware.** A cross-build's
  extraction step used the host's `objdump`, which can't reliably read
  a different target's DWARF. Fixed: `dump_dwarf()`/`extract()`/the
  CLI take an explicit `--objdump <path>`; `cmake/GenerateDwarfReflection.cmake`
  passes `${CMAKE_OBJDUMP}`.
- **A fixed-size array member resolved to size 0, not an abstention.**
  `resolve_type()` had no case for `DW_TAG_array_type`. Fixed: a new
  `_array_dimensions()` helper computes the real element count and
  total size from DWARF's `DW_TAG_subrange_type` children, supporting
  multi-dimensional arrays. `find_type()` was also hardened to skip
  *any* member whose type can't be resolved (comment, not a guess) —
  generalizing the fix beyond just arrays.
- **`REFLECT_DWARF_MEMBER`'s `Count` was hardcoded to 1**, even for
  array members. Fixed: `resolve_type()` returns `(name, size, count)`;
  `REFLECT_DWARF_MEMBER` takes a fifth `Count` argument.
- **A class with a virtual base class silently resolved to zero
  members and `byte_size 0`** — not a compile error, not an
  abstention. Root cause, in two parts: (1) GCC never emits a full
  `DW_TAG_structure_type` definition for a type that (directly or
  transitively) inherits from a polymorphic base when the only touch
  is a union member that's never actually constructed/destroyed — only
  an incomplete `DW_AT_declaration: 1` stub, even though the
  union-wrapper touch computes the type's real size internally; (2)
  `find_type()` didn't check for `DW_AT_declaration` and returned the
  first tag/name match unconditionally, so it silently returned that
  incomplete stub as the type. **Fixed**, both parts: the driver now
  also emits a `ForceFullDwarf<T>` template (guarded by
  `std::is_destructible_v<T>`) and calls it from a never-invoked
  `NeverCalled_<Type>()` function that explicitly destroys the union
  member — verified this forces full emission for a type with a
  virtual base *and* a constructor requiring an argument *and* a
  private member, all at once, without ever needing to know the
  constructor's arguments (unlike calling the real constructor, which
  would). `find_type()` now also skips any `DW_AT_declaration`
  candidate and keeps searching for a real definition — general
  defense-in-depth against picking the wrong DIE for *any*
  forward-declared type, not just this one. Covered by
  `test_virtual_base_class_resolves_correctly` and
  `test_find_type_skips_a_declaration_only_stub`.
- **A cmake include-path bug broke `tutorials/01_hello_world` when
  built via the `tutorials/` aggregator** (not standalone): the
  extraction driver guessed the generated `Version.hpp`'s directory as
  `${CMAKE_CURRENT_BINARY_DIR}/generated`, which is wrong when
  `BuildReflectionLibrary.cmake` and `reflection_generate_dwarf()` run
  in different directory scopes (true for the aggregator, not for a
  standalone tutorial build). Fixed: `BuildReflectionLibrary.cmake`
  now records the real path in `REFLECTION_GENERATED_INCLUDE_DIR`, used
  by `GenerateDwarfReflection.cmake` instead of re-derived.
- **DWARF exposed the compiler-generated vtable pointer as an ordinary
  member** (`_vptr.Base`, type `"<unknown>**"`) for any class with a
  virtual function — accurate data, but not something a consumer wants
  surfaced as a declared field. Fixed: `find_type()` now excludes any
  member whose name starts with `_vptr.` entirely (neither emitted nor
  reported as skipped — it was never a declared data member, so it's
  not "unresolved," it's categorically not reflectable data). The
  class's own `byte_size` is read independently from the class DIE's
  `DW_AT_byte_size`, so excluding this pseudo-member doesn't affect the
  reported total size — only removes it from `GetMembers()`. Covered by
  `test_vtable_pointer_is_excluded_from_members`.
- **The extraction driver used a fixed flag set, not the real target's
  own compile settings** — meaning a custom `-D` define or a
  non-default, layout-affecting flag (e.g. struct-packing) on the real
  target could make the extracted object silently disagree with the
  real one. Fixed: the driver now compiles as a real CMake `OBJECT`
  library (`cmake/GenerateDwarfReflection.cmake`'s
  `<TARGET>_dwarf_extraction_driver`) with
  `target_compile_definitions`/`target_include_directories`/
  `target_compile_options` reading `$<TARGET_PROPERTY:TARGET,...>` off
  the real target, resolved at generate time. **A hand-rolled
  `add_custom_command` invocation splicing these properties into one
  command string via `"SHELL:...$<JOIN:...>"` was tried first and does
  not work** — verified: the Unix Makefiles generator did not honor
  `SHELL:` at all, passing the whole joined string through as one
  malformed argument instead of splitting it into separate flags. The
  `OBJECT`-library approach avoids this entirely by letting CMake's own
  target-property machinery (proven correct for any ordinary target)
  form the flags, rather than reimplementing that logic by hand.
  Verified end to end: a `target_compile_definitions()` macro that
  changes a member's array size (`#ifdef`-guarded) is now correctly
  reflected in the extracted layout, cross-compiled for QNX SDP 8.0 too.

## Future work: enums

`REFLECT_ENUM_BEGIN` is the one remaining escape hatch this pipeline
doesn't close yet — not a permanent requirement, same as the
private-member case this ADR already eliminated. Addressable by
extending this same pipeline: match `enum`/`enum class` in discovery,
and read `DW_TAG_enumeration_type`/`DW_TAG_enumerator` (name + constant
value, no access control involved) in `find_type()`/`resolve_type()`.

## Consequences

- A materially bigger mechanism than [0012](0012-generated-reflection-names.md)'s
  text scanner: an extra compile pass per reflected source file, a
  DWARF text-output parser, and CMake wiring to sequence
  discover → compile → extract → generate → real-compile automatically.
- The only approach found so far that reaches a private member, or a
  class with a constructor requiring arguments, without modifying the
  class that owns it.
- Array members are now resolved correctly. Enums still have only a
  working fallback (`REFLECT_ENUM_BEGIN`) — an unclosed gap, not a
  solved one (see "Future work").
