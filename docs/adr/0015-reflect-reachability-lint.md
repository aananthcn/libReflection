# 0015 — `reflect::Reflect<T>()` Reachability Lint

**Status:** Decided and implemented. See `tools/generate_dwarf_reflection.py`'s
`--lint` mode (`find_unreachable_reflect_targets()`) and
`cmake/GenerateDwarfReflection.cmake`'s pipeline step 0.

## Context

[0013](0013-dwarf-based-reflection-generation.md)'s pipeline only
generates a real DWARF specialization for a type it can actually
*discover* — declared in `SOURCE` itself, or reached by following a
local (`"..."`) `#include` from it, transitively. A
`reflect::Reflect<T>()` call for a type outside that reachable set
doesn't fail loudly by itself:

- If `T` happens to be a shape automatic aggregate reflection can
  describe cleanly, the call still compiles — it just silently falls
  back to the primary template, losing `T`'s real name and
  hash-identity ([0001](0001-reflection-generation-strategy.md),
  [0002](0002-class-hash-algorithm-and-purpose.md)).
- If `T` reaches a direct fixed-size array member (or another shape
  automatic aggregate reflection can't count), the call hard-fails —
  but as a `static_assert` deep inside `AggregateReflection.hpp`,
  reported at the `reflect::Reflect<T>()` call site with no hint that
  the *real* problem is upstream: `T` was never discoverable in the
  first place.

This was found via a real incident, not a hypothetical: a colleague's
build (`tutorials/07_CAS_Structure`-shaped) hit exactly the second
case, and the actual root cause (a build-wiring mistake, not a code
problem) took real diagnosis to find, hidden behind a wall of
template-instantiation errors. Two concrete unreachable-target shapes
were identified:

1. `T` is declared only behind a `<...>`-style include, never a
   `"..."` one — a type the discovery step (by design) never follows.
2. `T` isn't declared anywhere reachable from `SOURCE` at all — e.g.
   it's defined in a different `.cpp`, compiled and linked separately
   but never `#include`-d from `SOURCE`.

## Options considered

- **Leave it as-is.** Rejected: inconsistent with this pipeline's
  established "abstain, never guess, but *surface* it" policy — the
  same reasoning behind 0013's `#warning` directives for an
  individually-unresolved member. A whole unreachable *target*
  deserves at least the same visibility a single unresolved *member*
  already gets.
- **A separate, opt-in script** (e.g. run manually or as a CI step,
  not wired into the build). Considered, then rejected in favor of
  always-on: the failure mode is as much a silent *degradation* (lost
  real names/hash-identity, no compile error at all) as a hard
  failure, and an opt-in check is one more thing to remember to run —
  easiest to skip precisely on the large, unfamiliar legacy codebase
  that needs it most.
- **Automatic, wired into every `reflection_generate_dwarf()` call.**
  Chosen — see Decision.

For severity, both a non-fatal `#warning` (matching 0013's existing
per-member policy) and a hard build error were weighed; hard error was
chosen deliberately, against that precedent — see Decision for why the
two cases aren't actually analogous.

## Decision

**Runs automatically, as pipeline step 0**, before the extraction
driver ever compiles — added to `reflection_generate_dwarf()` itself,
not a separate opt-in target, so it can't be skipped or forgotten.

**A violation is a hard build error**, not a `#warning`. This is a
deliberate divergence from 0013's own per-member policy, not an
inconsistency: an individually-unresolved *member* is something the
pipeline already handles gracefully on its own (the member is simply
omitted, the rest of the type still resolves correctly) — a
`#warning` there is purely informational. An unreachable
`reflect::Reflect<T>()` *target*, by contrast, is a call the caller
explicitly wrote expecting a real, working reflection of `T` — letting
it proceed either hard-fails later behind a confusing wall of
templates, or compiles clean while silently handing back degraded
data. Neither outcome is one to let through quietly.

**Scope is deliberately narrow**: only a `reflect::Reflect<T>()` call
where `T` is a **bare, unqualified identifier** (no `::`, `<`, `*`,
`[`) is checked at all. A template instantiation, pointer, qualified
name, or array alias is never flagged — each either already has its
own correct handling (a real `TypeInfo<T>` specialization, or DWARF's
own template-instantiation discovery) or can't be reliably classified
from text alone without a real compiler's semantic knowledge (e.g. a
local `typedef` aliasing an array type, indistinguishable from a
struct name by spelling alone). Abstaining here follows this whole
tool's standing policy: never guess, never risk a false positive on a
large legacy codebase's realistic type spellings.

**Known-good exclusions** (never flagged even though not "discovered"
by the DWARF pipeline): C++ primitives, `<cstdint>`-style fixed-width
aliases, `std::string`, any local `typedef`/`using` alias found
anywhere in the reachable set, and any name registered via
`REFLECT_CLASS_BEGIN`/`REFLECT_ENUM_BEGIN`. All of these bypass the
DWARF pipeline correctly by design already, so flagging one would be a
false positive by construction, not a defensible "maybe".

**Include-dir resolution goes through a generated text file**
(`file(GENERATE)`), not spliced into the lint's own custom-command
`argv` — the same reasoning 0013's "Fixed bugs" already established
for the extraction driver's `COMPILE_DEFINITIONS`/`INCLUDE_DIRECTORIES`:
splicing a genex-expanded list into a hand-built command string does
not reliably split into separate arguments under the Unix Makefiles
generator. `--include-dir` (repeatable) is kept too, for direct CLI/test
use.

## A bug found while building this

The lint's own traversal initially made the exact mistake
`discover_type_names()`'s own code comment already warns against: it
searched for `#include` directives in text that had already had string
literals blanked out, which blanks out a quoted include *path* too
(it looks exactly like a string literal to a regex). This produced a
real false positive (`tutorials/01_hello_world`'s `HelloWorld`,
declared in a locally-`#include`-d header, was wrongly flagged as
unreachable). Fixed by searching for `#include` directives in
comments-only-stripped text, and reserving the fully-stripped
(comments *and* string/char literals) text for everything else this
lint scans (struct/class declarations, macro registrations, typedefs,
`Reflect<T>()` call sites) — mirroring the same two-pass separation
`_scan_declarations()` already used for the real pipeline. Covered by
`test_finds_type_only_reachable_through_local_include`.

## Consequences

- A `reflect::Reflect<T>()` call for a type this pipeline can't
  actually reach now fails **fast**, with a message that names the
  real cause (which `<...>` vs. `"..."` distinction, or "not found at
  all") and a concrete fix — before the driver's bootstrap compile,
  rather than surfacing as either an unrelated-looking
  template-instantiation wall or nothing at all.
- False-negative by design for anything not a bare identifier — an
  accepted gap, not an oversight: worth it to never false-positive on
  a real codebase's aliases, pointers, or template usages.
- One more mandatory step in every DWARF-pipeline build. Small (pure
  text scanning, no compiler invocation), but real and unconditional,
  unlike an opt-in check that could be skipped.
