# 0012 — Generated Reflection Names

**Status:** REVERTED. Built and verified working, then reverted because
its founding assumption was wrong. Superseded by
[0013](0013-dwarf-based-reflection-generation.md). Kept as a historical
record (not deleted) — trimmed to requirements/lessons rather than the
full build narrative.

## Why reverted

This mechanism only ever covered **plain aggregates** (no constructor,
no private/protected members) — on the assumption that plain
aggregates are representative of a real ~10,000-class legacy codebase.
That assumption is wrong: ordinary encapsulation (private data behind a
constructor/accessors) is the *typical* shape of a hand-written C++
class. Reaching a private member with any macro-based mechanism
(hand-written or generated) requires a `friend` declaration — a source
change this project rules out from the start. So for most of a real
legacy codebase, this mechanism doesn't help at all.

[0013](0013-dwarf-based-reflection-generation.md) replaces it: DWARF
debug info exposes real member names/offsets/types regardless of C++
access control, reaching the case that actually matters without
touching the original source.

## Requirements this mechanism met (while it was the plan)

- Scan header/source text for `struct`/`class`/`enum` declarations,
  entirely at build time (host-side Python + CMake), with **zero**
  human-written or human-maintained registration code for a type it
  could confidently parse.
- **Abstain, never guess.** Emit a registration for a type only when
  every statement in its body is unambiguous: a plain `Type name;`
  member, a fixed-size array declarator, or an access specifier.
  Anything else (bit-fields, default initializers, multiple
  declarators, methods, nested types, templates, macros, a non-`public`
  member) → emit nothing for that whole type, leaving it on the
  automatic-reflection fallback.
- **Never trust a bare generated string.** A generated member/enumerator
  reference must be a real, compiler-checked expression
  (`decltype(ReflectedT::Name)` / `static_cast<int64_t>(ReflectedT::Value)`),
  so a hallucinated or misspelled name is a compile error, never
  silently wrong data.
- Two output shapes depending on whether a struct has an array member:
  - No array members: `REFLECT_NAMES_BEGIN`/`REFLECT_FIELD_NAME` — a
    thin name/type-label **overlay** on top of automatic aggregate
    reflection's already-correct offsets/sizes/count (double-verified:
    wrong structure fails automatic reflection, wrong name fails to
    compile).
  - One or more array members: a full `REFLECT_CLASS_BEGIN`/
    `REFLECT_MEMBER` block instead (automatic reflection can't count
    array members at all — see [0001](0001-reflection-generation-strategy.md)).
    Narrower safety profile: each member is still compile-checked
    individually, but there's no independent structural source to
    catch the scanner *missing* a member entirely.
- Output must be a **header** (`#pragma once`), explicitly `#include`d
  by every consumer, honoring [0010](0010-header-and-macro-sketch.md)'s
  declare-before-use rule — never a separate `.cpp`. (A `.cpp`-based
  specialization silently fails: the consuming TU never sees it, falls
  back to positional names, and it's an ODR violation besides. Found
  and fixed during the build; recorded here so it isn't rediscovered.)
- New host-side-only build dependency: Python 3 (via
  `find_package(Python3 COMPONENTS Interpreter REQUIRED)`) — not a
  target/runtime dependency.

## What was built and verified

- `tools/generate_reflection_names.py` + `tools/test_generate_reflection_names.py`
  (25 tests: happy path, every abstention case, array-member handling,
  namespace qualification, enum handling).
- `cmake/GenerateReflectionNames.cmake`
  (`reflection_generate_names(TARGET <t> OUTPUT_VAR <v> HEADERS <hdrs>)`).
- `REFLECT_NAMES_BEGIN`/`REFLECT_FIELD_NAME`/`REFLECT_NAMES_END` in
  `src/ReflectionMacros.hpp`, plus `tests/test_name_overlay.cpp`.
- All three tutorials updated to use generated registrations for every
  type they could cover; `BoundedCounter` (constructor + method, not an
  aggregate at all) was `tutorials/03_macros_for_special_cases`'s
  remaining example of a type still needing a hand-written
  `REFLECT_CLASS_BEGIN`.

## Consequences (while adopted)

- Zero reflection code to write for the common shape (plain data
  structs, including array members, and simple enums) — matches
  exactly what a shared-memory IPC struct needs to be per
  [0002](0002-class-hash-algorithm-and-purpose.md).
- Never full coverage of an arbitrary codebase by design: any type with
  methods, templates, macros, non-public members, or unusual formatting
  falls back to automatic reflection's positional names — intended safe
  degradation, not a bug.

## What was removed on revert

- `tools/generate_reflection_names.py`, `tools/test_generate_reflection_names.py`.
- `cmake/GenerateReflectionNames.cmake`.
- `REFLECT_NAMES_BEGIN`/`REFLECT_FIELD_NAME`/`REFLECT_NAMES_END` from
  `src/ReflectionMacros.hpp`.
- `tests/test_name_overlay.cpp` and its `ctest` registration.
- The Python-3-required-host-tool consequence — no longer true.
- All three tutorials' codegen wiring; `tutorials/03_macros_for_special_cases`
  reverted to hand-written `REFLECT_CLASS_BEGIN`/`REFLECT_ENUM_BEGIN`.
