# 0014 — Aggregate Tie Code Generation

**Status:** Decided. Implementation detail of
[0001](0001-reflection-generation-strategy.md)'s automatic aggregate
reflection — recorded because it's the one piece of that path that is
*generated source*, and because the field cap (`64`) is an arbitrary
number that deserves a reason on the record.

## Context

Automatic aggregate reflection ([0001](0001-reflection-generation-strategy.md))
derives a struct's members from the type itself via a structured
binding:

```cpp
auto& [a0, a1, a2] = probe;      // decompose a 3-member aggregate
return std::tie(a0, a1, a2);     // -> tuple of references, for offset/type work
```

The catch: **a structured binding's arity is syntax, not a template
parameter.** There is no C++20 spelling of `auto& [a...] = probe;` that
is generic over a compile-time `N`. (C++26's P1061, "structured
bindings can introduce a pack", would allow it — not available here,
and QCC support would be years out regardless.) So this single step
can't be a template, a fold expression, or anything recursive. It has
to be written out once per possible member count:

```cpp
template <typename T>
inline auto TieMembers(T& probe, std::integral_constant<std::size_t, N>) { ... }
```

one overload per `N`, tag-dispatched on `std::integral_constant<size_t, N>`
so `CountAggregateFields<T>()`'s result selects the right one.

Writing 65 near-identical overloads (N = 0..64) by hand is exactly the
kind of mechanical, transcription-error-prone work a generator should
do.

## Decision

`tools/generate_aggregate_tie.py` emits `src/AggregateTie.generated.hpp`:
one `TieMembers()` overload for every `N` in `0..MAX_FIELDS`.

- **The generated header is committed to the repo**, not produced at
  build time. It is a pure function of one integer (`MAX_FIELDS`) —
  it depends on nothing about the consuming project, unlike
  [0013](0013-dwarf-based-reflection-generation.md)'s DWARF pipeline,
  which *must* run per-build because it reads the user's own types.
  Committing it keeps Python out of the library's build graph
  entirely, keeps the artifact diffable in review, and makes the build
  deterministic with no codegen step. Regeneration is a deliberate,
  rare, manual act:

  ```sh
  python3 tools/generate_aggregate_tie.py > src/AggregateTie.generated.hpp
  ```

- **The file has a hand-edit warning banner** and points back at both
  the script and this ADR.

- **Exceeding the cap is a compile error, never silent.**
  `CountAggregateFields<T>()` in `AggregateReflection.hpp` guards the
  count with

  ```cpp
  static_assert(!kIsBraceConstructibleWithN<T, kMaxAggregateFields + 1>,
      "aggregate has more than kMaxAggregateFields members -- give it an "
      "explicit REFLECT_CLASS_BEGIN block, or raise kMaxAggregateFields "
      "in AggregateReflection.hpp and regenerate AggregateTie.generated.hpp ...");
  ```

  so a 65-member aggregate fails loudly with the fix in the message,
  rather than picking a wrong overload or truncating members.

## `MAX_FIELDS` — why start at 64

`MAX_FIELDS` (in the script) and `kMaxAggregateFields` (in
`src/AggregateReflection.hpp`) are the same number and must stay
equal — see "Known coupling" below. `64` is a **starting** value,
chosen to be comfortably past every realistic case while keeping the
generated and instantiated code small:

- **Real plain-data structs don't get near it.** This path only ever
  runs for C++20 aggregates: no user-declared constructor, all members
  public — POD-ish records, config blobs, and the shared-memory IPC
  message structs [0002](0002-class-hash-algorithm-and-purpose.md) is
  built around. A *flat* aggregate with more than 64 direct data
  members is rare and usually a modelling smell (it wants nested
  sub-structs, each reflected recursively anyway). 64 clears typical
  real structs with wide margin.

- **The generator is O(N) in lines, and every line is parsed
  everywhere.** `AggregateReflection.hpp` includes the generated header
  unconditionally, so all 65 overloads are parsed in every TU that
  pulls in reflection — even one reflecting a 3-field struct. At 64
  the file is ~400 lines; the cost is real but negligible. Doubling
  the cap doubles that fixed per-TU parse cost for a ceiling almost no
  one will reach.

- **The field-count search widens with the cap.**
  `FieldCountSearch` binary-searches `[0, kMaxAggregateFields]`, and
  each probe instantiates an `N`-argument brace-init / paren-init
  SFINAE check (`kIsBraceConstructibleWithN`, `kIsParenConstructibleWithN`).
  `log2(64) ≈ 6` levels with bounded per-probe width keeps
  compile-time template load modest; raising the cap raises the top of
  that range for every reflected aggregate, not just large ones.

- **It's a round, memorable power of two**, and raising it is a
  one-line edit plus a regen — cheap to revisit if a real type ever
  needs it. Peer libraries land in the same order of magnitude
  (Boost.PFR's precise mode has historically capped around ~100 for
  similar reasons).

In short: 64 is deliberately conservative. It is the point past which
we would rather you *think* — restructure the type, or opt into
`REFLECT_CLASS_BEGIN` — than silently pay a bigger fixed cost for
everyone.

## Known coupling

Three places name the cap and are kept in sync **by hand**:

| Location | Form |
|---|---|
| `tools/generate_aggregate_tie.py` | `MAX_FIELDS = 64` |
| `src/AggregateReflection.hpp` | `inline constexpr std::size_t kMaxAggregateFields = 64;` |
| `src/AggregateTie.generated.hpp` (banner) | `N = 0..64` (emitted from `MAX_FIELDS`) |

The generated banner tracks the script automatically. The
`AggregateReflection.hpp` constant does not — if you raise one and not
the other, either the `static_assert` fires below the number of
overloads that actually exist (harmless, just a lower effective cap) or
it permits an `N` with no matching `TieMembers()` overload (a hard
compile error at the call site). The `static_assert`'s own message
spells out "raise `kMaxAggregateFields` … and regenerate", so the
failure is self-documenting; a single shared constant would be nicer
but isn't worth a build-time codegen step for a number that changes
approximately never.

## Consequences

- The automatic-aggregate path has exactly one generated-source
  dependency, and it is static, tiny, reviewable, and regenerated only
  on a conscious cap change.
- No Python, no codegen, no extra build step for the core library on
  account of this mechanism — contrast
  [0013](0013-dwarf-based-reflection-generation.md), whose generation
  is inherently per-project and therefore build-time.
- Aggregates with > 64 direct members are unsupported on this path by
  construction, with a compile error that names both fixes (raise the
  cap + regen, or `REFLECT_CLASS_BEGIN`). This sits alongside the other
  "loud, not silently wrong" limits in
  [0001](0001-reflection-generation-strategy.md)'s "Unsupported shapes".
- If C++26 structured-binding packs (P1061) ever become usable on all
  target compilers, the generated header and its script collapse into a
  single real template and this ADR becomes historical.
