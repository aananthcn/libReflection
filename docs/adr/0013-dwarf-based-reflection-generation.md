# 0013 — DWARF-Based Reflection Generation

**Status:** Implemented and verified — on the Linux host, via the QNX
SDP 8.0 cross-toolchain (`x86_64` and `aarch64`), and by running on a
real QNX 8.0 aarch64 device (not just cross-compiled). 40 Python tests
in `tools/test_generate_dwarf_reflection.py`. See "Fixed bugs" for the
virtual-base-class bug (a serious one — silently zero members), the
vtable-pointer exposure, the flags-mirroring gap, template discovery
(including nested template arguments), and the silently-absent-skip
build warning, all now fixed/closed, and "Known limitations" for
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
   what's inside them. A template's bare declaration alone can't be
   touch-instantiated (no template argument is known there), so the
   same file set is searched again for actual USES of each discovered
   template (e.g. `Box<int> value;`, or a nested one like
   `Box<Box<int>>`) instead — see "Fixed bugs" for how this works
   (a bracket-depth scanner, not a regex, is what makes nesting work)
   and its residual risks. Enums are not discovered yet (see "Future
   work").
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
   access-checked expression. A type DWARF has no record of at all, or
   an individual member whose type can't be confidently resolved
   (`resolve_type()`'s `"<unknown>"` sentinel), is left out — noted
   with a `//` comment **and** a real `#warning` directive, so a build
   that `#include`s the generated header can't silently miss it (see
   "Fixed bugs").
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

- **A chained relational comparison shaped exactly like a
  single-argument template use with an integer-literal argument** (e.g.
  `Box < 5 > threshold`) is indistinguishable from a genuine non-type
  template instantiation `Box<5>` by text alone, and is *not* filtered
  out — see `tools/test_generate_dwarf_reflection.py`'s
  `test_known_residual_risk_of_bare_integer_comparison`, which records
  this as an accepted, understood trade-off. Low real-world risk
  (unparenthesized chained comparisons are rare and usually already
  flagged by `-Wparentheses`), and the failure mode if it ever happens
  is a **loud, hard compile error** in the generated driver (a name
  that isn't actually a template instantiation fails to compile) —
  never silently wrong reflection data.
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
- **Templates were excluded from discovery entirely** — a template
  class's bare declaration alone can't be touch-instantiated (no
  template argument is known there), so it was skipped outright, with
  no path to reach it non-intrusively. Fixed: `discover_type_names()`
  now tracks each discovered template's base name separately, then
  searches the same file set again for actual USES of it (e.g.
  `Box<int> value;`) — a type that's genuinely instantiated somewhere
  in the program is a real, existing type, resolvable the same way any
  other type is. Each distinct use is normalized to GCC's canonical
  DWARF spelling (`_normalize_template_instantiation()`: no space
  after `<`/before `>`, exactly one space after each comma — verified
  against real compiled output) so `find_type()`'s later exact-string
  lookup matches; an argument that doesn't look like a plausible
  type/literal (`_TEMPLATE_ARG_SHAPE_RE`) is abstained on, not guessed
  at — see "Known limitations" for the one residual risk this still
  leaves. (A nested template argument, e.g. `Box<Box<int>>`'s outer
  layer, was ALSO abstained on at this point — fixed separately below.)

  **A second, compounding bug found while building this**: a
  multi-argument instantiation's canonical name has a top-level comma
  (`Pair<int, float>`) — naively emitting
  `REFLECT_DWARF_CLASS_BEGIN(Pair<int, float>, 8)` gets misparsed by
  the C preprocessor as **three** macro arguments, not two (angle
  brackets don't protect a comma from argument-splitting the way
  parentheses do) — a hard compile error for any multi-argument
  template, not a silent one. Fixed by changing
  `REFLECT_DWARF_CLASS_BEGIN`'s signature to
  `(ByteSize, Name, ...)`, making the type itself the macro's trailing
  *variadic* argument (`__VA_ARGS__` captures everything after `Name`
  verbatim, comma included) and passing `Name` as an explicit string
  literal instead of deriving it via `#Type` stringification (which
  doesn't need to change now that `Type` and `Name` are separate
  parameters). Verified end to end, including that the generated
  header actually compiles when consumed by real code, not just that
  its generated text looks right: both `Box<int>` and
  `Pair<int, float>` resolve correctly with real member names, sizes,
  and offsets. Covered by
  `test_finds_template_instantiation_used_in_source`,
  `test_finds_multi_argument_template_instantiation`,
  `test_normalizes_instantiation_spacing_variants`,
  `test_template_instantiation_resolves_correctly`, and
  `test_multi_argument_template_instantiation_resolves_correctly`.
- **A template instantiation used only inside a nested template
  argument was never captured as a whole** (e.g. `Box<Box<int>>` itself
  was never touched, though the inner `Box<int>` incidentally was,
  since it also appears as a plain, non-nested match on its own) — the
  use-scanner excluded `<`/`>` from the argument character class
  entirely, so it could never match past the FIRST closing `>`, whether
  or not that was the real end of the outer argument list. **Fixed**:
  `_find_balanced_template_args()` replaces that exclusion with a
  bracket-depth counter — each `<` in the scanned text is +1 depth,
  each `>` is −1, and the match ends only when depth returns to 0 — so
  a nested `<...>` no longer ends the outer scan early. Each argument
  is then validated and normalized recursively
  (`_normalize_arg()`/`_normalize_arg_list()`/`_split_top_level_args()`):
  a leaf argument still has to match `_TEMPLATE_ARG_SHAPE_RE`, and a
  nested one has to be a clean `Name<...>` with nothing trailing after
  its own matching `>` (e.g. `Box<int>*` as one argument slot still
  abstains the whole outer instantiation, not guessed at). Confirmed
  empirically against real compiled DWARF that GCC's name for a nested
  instantiation inserts a space between adjacent closing brackets —
  `Box<Box<int>>` is spelled `"Box<Box<int> >"`, `Box<Box<Box<int>>>` is
  `"Box<Box<Box<int> > >"` — a leftover of the pre-C++11 rule against
  `>>` being lexed as the shift operator that GCC's internal type
  printer still follows; `_close_adjacent_angle_brackets()` reproduces
  this by turning every `>>` into `> >` (verified for 2 and 3 levels of
  nesting and for a nested argument alongside a plain one, e.g.
  `Pair<int, Box<int>>`). This same spelling is valid C++ source text
  too (whitespace is insignificant outside literals), so the identical
  canonical string works unmodified as both the driver's touch-instance
  type and the generated macro's trailing `Type` argument — exactly
  like the multi-argument-comma case above needed no separate handling
  for driver emission vs. macro invocation vs. DWARF lookup. Verified
  end to end through the real `reflection_generate_dwarf()` CMake
  pipeline in a scratch project: `Box<Box<int>>` resolves at runtime
  with the correct class name, size, and a `"value"` member correctly
  typed as `"Box<int>"` (itself independently resolved too). Covered by
  `test_resolves_the_outer_layer_of_a_nested_instantiation_too`,
  `test_resolves_triple_nested_instantiation`,
  `test_resolves_nested_instantiation_as_one_of_several_arguments`,
  `test_abstains_on_a_nested_instantiation_with_trailing_junk`, and
  `test_nested_template_instantiation_resolves_correctly`.
- **A truly unresolvable member's type, or a whole type not found in
  DWARF at all, was silently absent — noted only in a `//` comment
  inside a generated file nobody reads, never surfaced at build time.**
  The right behavior (abstain, don't guess) was already in place; only
  its visibility was missing. Fixed: `extract()` now also emits a real
  `#warning` preprocessor directive alongside each such comment —
  `#warning <Type>::<member>: type not resolved in DWARF info --
  member skipped, not guessed.` for an individual member, `#warning
  <Type>: not found in DWARF info -- entire type skipped, not
  guessed.` for a whole type. `#warning` is a non-standard but
  essentially universal GCC/Clang extension (QNX's GCC-based `qcc`/
  `g++` front end included), never fails the build — same "abstain,
  never guess, never break the build" policy as everything else this
  tool does, just made visible. Verified end to end through the real
  `reflection_generate_dwarf()` CMake pipeline (a flexible/unbounded
  array member — the one known real-world case that hits this path —
  compiles cleanly with exactly one `-Wcpp` warning at the exact
  generated line, no error). Covered by
  `test_skipped_member_emits_a_build_warning` and
  `test_type_not_found_emits_a_build_warning`.

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
