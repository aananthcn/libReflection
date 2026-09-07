# 0012 — Generated Reflection Names

**Status:** REVERTED. Built, verified working end to end (see below),
then reverted once its founding assumption turned out to be wrong.
Superseded by [0013](0013-dwarf-based-reflection-generation.md). Kept
in full, not deleted or merged away, because it's a genuine
"built it, it worked, the premise was still wrong" record worth
preserving as-is — unlike [0001](0001-reflection-generation-strategy.md)'s
revision (an *additive* refinement of a standing decision), this is a
full reversal of a decision that was, on its own narrow terms, correct.

## Why this was reverted

The entire mechanism below — the text scanner, the name overlay, the
array-handling revision — is scoped to **plain aggregates**: types
with no user-declared constructor and no private/protected members.
The unstated assumption underneath adopting this scope was that plain
aggregates are *representative* of what a real ~10,000-class legacy
C++ codebase mostly looks like.

That assumption is wrong. Ordinary encapsulation — private data behind
a constructor and accessors — is the *typical* shape of a hand-written
C++ class, not an edge case. For any class with private members, the
only way *any* macro-based mechanism (hand-written `REFLECT_CLASS_BEGIN`
or this ADR's generated version) can reach them is a `friend`
declaration inside the class — a source modification. That is exactly
the constraint this whole project started from: the original authors
of the legacy codebase will not accept changes to their headers. So
for whatever fraction of a real legacy codebase uses ordinary
encapsulation — likely the majority — this entire mechanism, however
well-built, does not help at all, non-intrusively.

[0013](0013-dwarf-based-reflection-generation.md) exists because DWARF
debug info exposes real member names/offsets/types regardless of C++
access control (a debugger can already inspect a private field; the
data is compiler-emitted, not access-checked) — the one path found so
far that can reach the case that actually matters most, without
touching the original source at all.

Everything below this point is preserved as it was at the time this
was believed to be the right direction, for the reasoning and the
lessons in it (in particular "A mistake made and fixed" below, which
remains a real and worthwhile lesson independent of the reversal).

## Context (as it was understood at the time)

[0001](0001-reflection-generation-strategy.md)'s revision solved the
*structural* half of the 10,000-class problem: automatic aggregate
reflection gets real offsets/sizes/types/count with zero annotation.
It deliberately can't recover real **names** — nothing in a compiled
C++ program records a struct's own name or its members' source
identifiers, full stop, in any standard mechanism available today (see
the extended discussion in this conversation about why: no
`typeid`-based approach works without RTTI, and the one non-standard
trick that could work, `__PRETTY_FUNCTION__` parsing, was already
rejected for QCC portability risk).

So for a codebase where real names matter (debugging, logging,
pretty-printing, or distinguishing two structurally-identical-but-
different IPC message types by hash), the only options were still
"annotate it yourself" — whether inline via `REFLECT_CLASS_BEGIN` or
in a separate non-intrusive file — which for 10,000 classes is exactly
the manual-effort problem this whole line of design work has been
trying to eliminate.

The idea explored here: a CMake-invoked tool that scans the *source
text* of a header (where the real names still exist, unlike the
compiled binary) and generates the registration automatically, so a
human never has to write or maintain it. This reopens [0001](0001-reflection-generation-strategy.md)'s
originally-rejected "external code-generation tool" option — but the
rejection there was specifically about a **libclang** dependency and
the QNX SDP 8.0 cross-build complexity that came with it. A plain
Python script invoked as a host-side CMake build step avoids that
specific objection: it runs on the build host regardless of what
target is being cross-compiled for, the same as any other codegen
build step.

## The real risk, and how the design manages it

A hand-rolled text scanner is not a real C++ parser. Real codebases
have macros, templates, unusual formatting, `#ifdef` branches — a
naive scanner will inevitably misparse *something* at scale, and the
dangerous failure mode is a **confident wrong answer**, not a clean
error.

Two design choices directly address this, and both were verified, not
just assumed:

1. **Abstain rather than guess.** The scanner
   (`tools/generate_reflection_names.py`) only emits a registration
   for a struct if *every* statement in its body is unambiguously
   either an access specifier or a single, plain `Type name;` data
   member — no arrays, bit-fields, default initializers, multiple
   declarators, methods, or nested types. The moment it hits anything
   it doesn't confidently understand, it emits nothing for that whole
   type, leaving it on the already-safe automatic-reflection fallback.
   This is tested directly: `tools/test_generate_reflection_names.py`
   has explicit cases asserting abstention for each of those shapes,
   plus namespace-qualification and basic happy-path cases (18 tests,
   passing).

2. **The generated names are only an overlay on top of the
   already-correct automatic structural reflection — they never
   replace it.** New macros `REFLECT_NAMES_BEGIN`/`REFLECT_FIELD_NAME`/
   `REFLECT_NAMES_END` (`src/ReflectionMacros.hpp`) call
   `detail::DescribeAggregate<T>()` (the same function automatic
   reflection itself uses) to get the real offsets/sizes/types/count,
   and only then relabel `r.name`/`r.type` and each member's `name`.
   Critically, `REFLECT_FIELD_NAME(Name)` forces a real reference to
   `ReflectedT::Name` via `decltype` — a hallucinated or misspelled
   name the generator invents is a **compile error**, not silently
   wrong data (verified: a deliberately wrong name in a test failed to
   compile with a clear "is not a member of" diagnostic). The one risk
   this can't catch is two *real* member names supplied in the wrong
   order — a data problem, never a memory-safety or hash-corruption
   one, and one that would be visible in the generated file itself,
   which is deliberately not hidden away (see below).

   The same "reference the real thing, don't trust a bare string"
   principle extends to enums: `REFLECT_ENUM_BEGIN`/`REFLECT_ENUM_VALUE`
   already required this (`static_cast<int64_t>(ReflectedT::Value)`),
   so generating enum registrations was even lower-risk than the
   struct case from the start.

## Decision

Adopt the tool, scoped exactly as prototyped:

- **`tools/generate_reflection_names.py`** scans one or more headers
  and generates a **header** (not a `.cpp` — see "A mistake made and
  fixed" below) containing `REFLECT_NAMES_BEGIN`/`REFLECT_ENUM_BEGIN`
  blocks for every type it could confidently parse.
- **`cmake/GenerateReflectionNames.cmake`** provides
  `reflection_generate_names(TARGET <t> OUTPUT_VAR <v> HEADERS <hdrs>)`,
  wiring the scan into the build as an `add_custom_command` (rerun
  automatically whenever a scanned header or the script itself
  changes) and adding the generated header as a source of `<t>` (a
  standard CMake idiom to force generation before it's `#include`d).
- Callers must `#include "generated_reflection_names.hpp"` themselves,
  in every translation unit that calls `Reflect<T>()` for a covered
  type — this is deliberate, not an oversight: it keeps the mechanism
  visible and the declare-before-use rule (below) satisfiable by
  ordinary means, rather than trying to inject the include invisibly.
- This adds a **new host-side build dependency: Python 3**, required
  at configure/build time (via `find_package(Python3 COMPONENTS
  Interpreter REQUIRED)`), on whatever machine runs CMake — not a
  runtime or target dependency, and not a departure from "the target
  binary has zero dependencies," but a real, new requirement on the
  development host that didn't exist before this ADR. Worth stating
  plainly rather than glossing over given this project's
  otherwise-strict zero-dependency posture.

## A mistake made and fixed while building this

The first working version generated a separate `.cpp` file, compiled
as its own translation unit, and linked in alongside the consumer's
`.cpp`. This *silently produced wrong output* — the consuming `.cpp`
never saw the generated `template<> struct TypeInfo<T>` specialization
(it lives in a different TU), so it fell back to instantiating the
*primary*, unspecialized template, and got sentinel/positional names
exactly as if the generator had never run. Worse, this is technically
an ODR violation (two TUs defining the same template specialization
differently — one with it, one without), which the observed behavior
(the linker silently keeping one definition and discarding the other)
is a plausible-but-unspecified consequence of, not a guaranteed one.

This is the *same* declare-before-use rule already documented in
[0010](0010-header-and-macro-sketch.md) for `REFLECT_CLASS_BEGIN`
output — a rule that was already known and written down, and still
got missed applying to this new generator's own output. Fixed by
making the generator emit a header (`#pragma once`) instead, requiring
callers to explicitly `#include` it. Recorded here specifically so the
mistake — and that it was a known rule, not a new discovery — doesn't
get repeated the next time this mechanism is extended.

## Revision: array members are covered too, via a second generation strategy

The first version of this tool abstained on any struct with a direct
fixed-size array member, on the theory that since automatic aggregate
reflection can't count array members reliably (see
[0001](0001-reflection-generation-strategy.md)'s revision), there was
no structural result to overlay generated names onto.

That theory undersold what the *scanner* itself can do. Automatic
reflection's limitation is specifically about *counting members at
runtime via construction probing* — it has no access to the source
text, only to the compiled type. The generator has the opposite
situation: it reads an array member's declarator (`int buckets[4];`)
directly out of the source, so it never needs to *count* anything
ambiguous — it already knows there's a member named `buckets`. And
`REFLECT_MEMBER` (the existing, already-proven macro) already handles
array members correctly on its own, via `decltype`/`offsetof`,
independent of automatic reflection entirely — this was verified
directly (a hand-written `REFLECT_CLASS_BEGIN`/`REFLECT_MEMBER` block
for a struct with an `int a; int buckets[4];` shape correctly reports
`buckets`' count as 4) before changing anything.

**Revised decision:** the generator now scans for two confidently-
understood member shapes — plain scalar/class members (as before) and
fixed-size array declarators — and picks its output strategy based on
whether a struct contains any array member:

- **No array members:** unchanged — `REFLECT_NAMES_BEGIN`/
  `REFLECT_FIELD_NAME`, the overlay on automatic reflection's
  already-correct structural output.
- **One or more array members:** a full `REFLECT_CLASS_BEGIN`/
  `REFLECT_MEMBER` block instead, one `REFLECT_MEMBER` per field
  (array or not), exactly what a human would otherwise write by hand.

This is a **narrower safety profile than the overlay**, worth being
precise about rather than claiming equal safety: each *individual*
`REFLECT_MEMBER(Name)` is still compiler-verified (a hallucinated name
is a compile error, via the same `decltype`/`offsetof` mechanism a
hand-written block already uses), but there is no second, independent
structural source to fall back on if the scanner *misses* a member
entirely — an undercount here means an incomplete reflection (a real
member absent from `GetMembers()`), not just a mislabeled one. This is
the same risk profile already accepted for enum generation from the
start, so it's not a new category of risk to the design, but it is a
step down from the overlay case's double-verification, and is
recorded here so that distinction doesn't get lost.

**A second, related gap found and fixed at the same time:** the
scanner did not track member *access* (`public`/`private`/`protected`)
at all — it would happily include a `private` member in a generated
`REFLECT_FIELD_NAME`/`REFLECT_MEMBER`, which fails to compile
(`decltype`/`offsetof` on an inaccessible member is ill-formed) rather
than abstaining gracefully. This wasn't a correctness risk (a hard
compile error, not silent wrong data) but it broke the "abstain
cleanly" property and would take down the whole generated header's
compilation for what might otherwise be a usable type. Fixed:
the scanner now tracks the current access section (defaulting to
`public` for a `struct`, `private` for a `class`, matching C++'s own
default) and abstains the *entire* type the moment a non-public data
member is found — partial coverage was rejected as an option, since it
would misalign the overlay's positional-index correspondence for the
members that *were* emitted.

`tutorials/03_macros_for_special_cases/Histogram` (previously the
tutorial's example of a hand-written-macro-required type) now gets its
`REFLECT_CLASS_BEGIN`/`REFLECT_MEMBER` block generated automatically.
The tutorial was updated to introduce `BoundedCounter` — a type with a
constructor and a method, hence not an aggregate at all — as the new,
genuinely-remaining example of a type that needs hand-written
`REFLECT_CLASS_BEGIN`, since neither automatic reflection nor the
generator can safely handle a type whose body they don't fully
recognize as data-member declarations.

## What got built and verified

- `src/ReflectionMacros.hpp`: `REFLECT_NAMES_BEGIN`/`REFLECT_FIELD_NAME`/
  `REFLECT_NAMES_END`.
- `tools/generate_reflection_names.py` + `tools/test_generate_reflection_names.py`
  (25 passing tests: the happy path, every abstention case — bit-fields,
  default initializers, multiple declarators, methods, non-public
  members — array-member handling, namespace qualification, and enum
  handling).
- `cmake/GenerateReflectionNames.cmake`.
- `tests/test_name_overlay.cpp` in the main unit-test suite, exercising
  the macros directly (not just via generated code).
- All three tutorials updated: `01_hello_world` and
  `02_auto_reflect_legacy_struct` now show **real names**, generated
  automatically from `HelloWorld.hpp`/`LegacyTypes.hpp` — zero
  hand-written annotation, zero hand-maintained side file.
  `03_macros_for_special_cases`'s `Color`, `Vec3`, and (after the
  revision above) `Histogram` all get generated registrations now;
  `BoundedCounter` (a type with a constructor and a method — not an
  aggregate at all) is the tutorial's current, genuinely-remaining
  example of a type that still needs a hand-written
  `REFLECT_CLASS_BEGIN` block.

## Consequences

- For the common case (plain data structs, including ones with
  fixed-size array members, and simple enums — exactly what
  shared-memory IPC structs already need to be per
  [0009](0009-versioning-and-hash-purpose.md)), a human now writes
  **zero** reflection code and gets real names, not just positional
  ones. The 10,000-class scenario is now: nothing to write for the
  common shape (arrays included), `REFLECT_CLASS_BEGIN` only for
  non-aggregate types (constructors/methods), bit-fields, non-public
  members, or anything else the scanner abstains on.
- The scanner will not achieve full coverage across an arbitrary
  10,000-class codebase — any struct with methods, templates, macros
  in its body, non-public members, or unusual formatting falls back to
  automatic reflection's positional names, same as today. That's the
  intended, safe degradation, not a bug to chase down.
- Python 3 is now a required host-side build tool for any target using
  `reflection_generate_names()` (not for the library or `tests/`
  themselves, which don't use it).

## What was actually removed on revert

- `tools/generate_reflection_names.py`, `tools/test_generate_reflection_names.py`.
- `cmake/GenerateReflectionNames.cmake`.
- `REFLECT_NAMES_BEGIN`/`REFLECT_FIELD_NAME`/`REFLECT_NAMES_END` from
  `src/ReflectionMacros.hpp`.
- `tests/test_name_overlay.cpp` and its `ctest` registration.
- The Python-3-required-host-tool consequence above — no longer true;
  Python is not a dependency of anything currently in this repo.
- All three tutorials' codegen wiring; `tutorials/03_macros_for_special_cases`
  reverted to hand-written `REFLECT_CLASS_BEGIN`/`REFLECT_ENUM_BEGIN`
  for `Color`/`Histogram`/`Vec3`, plus `BoundedCounter` added as a
  fourth case (a non-aggregate with a public field, reflects fine by
  hand — the private-member case is what [0013](0013-dwarf-based-reflection-generation.md)
  is for).
