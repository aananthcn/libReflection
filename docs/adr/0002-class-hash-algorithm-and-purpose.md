# 0002 — ClassHash: Algorithm and Purpose

**Status:** Decided (algorithm); purpose confirmed by user. Merged
from two previously separate ADRs — `0002-class-hash-algorithm.md`
(the *how*) and half of `0009-versioning-and-hash-purpose.md` (the
*why*) — since both were about the same `ClassHash` concept and had
ended up split across two files for no reason other than history. The
other half of the old 0009 (`version.txt`, a wholly separate concept)
is now [0009 — Library Versioning](0009-library-versioning.md).

## Context

`ClassHash` is 256 bits (`uint64_t words[4]`). ARCHITECTURE.md
specifies the shape but not the algorithm, what it hashes over, or
*why* a class-level 256-bit hash is needed at all — and the answer to
"why" directly shapes how much precision the algorithm needs, so both
questions belong in one place.

## Decision

### Why ClassHash exists

`ClassHash` exists for **cross-process layout-drift detection over
shared-memory IPC**: the user has confirmed any cross-process boundary
in this system uses shared-memory-based IPC, meaning two
independently-built processes overlay the *same raw memory* with a
struct definition each compiled its own copy of — there is no
serialization step to catch a mismatch. `ClassHash` lets both sides
compare a cheap fingerprint of a struct's layout before trusting a
shared-memory region, instead of discovering a drift as silent memory
corruption or misinterpreted fields.

This confirms, and sharpens, [0004](0004-member-representation-scope.md)'s
scope decision: shared-memory structs cannot contain heap-owning
members (`std::string`, `std::vector`, pointers into process-local
heaps are meaningless across a process boundary) anyway, so treating
those as opaque/out-of-scope for full reflection was already the right
call independent of this confirmation.

A cryptographic hash (SHA-256) is unnecessary given this purpose — this
is a structural fingerprint used to detect *accidental* layout drift
between two independently compiled binaries, not a security boundary.
A cryptographic hash would also be significantly harder to implement
correctly as `constexpr`/portable C++20 with zero dependencies, working
against the "minimal implementation" mandate.

### How it's computed

- **What is hashed:** a canonical string built from the class's own
  `name`, and for each member (in declaration order): `name`, `type`,
  `offset`, `size`, `count`; plus, if the type is an enum, `enum_name`
  and each `(key, value)` pair in `enum_values`, and `bit_flag`. Members
  are hashed recursively through their own already-computed `hash`
  field rather than re-serializing nested members, so a change to a
  deeply nested type's layout propagates up.
- **How:** FNV-1a 64-bit, run four times over the same canonical byte
  string with four different offset-basis seeds, to fill the four
  `uint64_t` lanes of `ClassHash`. FNV-1a is a few lines of C++, requires
  no dependency, and is more than sufficient for structural-drift
  detection (accidental collision of two *different* layouts across all
  four independently-seeded 64-bit lanes is not a realistic concern for
  this use case) — directly because the purpose above only needs to
  catch *accidental* drift, not resist a deliberate adversary.
- **When computed:** at first registration (inside the lazy
  initialization described in [0008](0008-thread-safety-and-registry.md)),
  not as a `constexpr` compile-time value in v1. Making the full
  recursive hash a `constexpr` evaluated entirely at compile time is a
  reasonable future improvement but adds real complexity (constexpr
  string building, constexpr containers) that isn't required to meet
  the stated requirements.

## Consequences

- Two builds of the same source produce the same `ClassHash` as long as
  member declaration order and types match — which is exactly the
  layout-drift signal this is for.
- The hash is *not* a security-grade fingerprint; it must not be used
  for anything where a deliberate adversary could try to engineer a
  collision. FNV-1a remains appropriate for this use case; no need to
  move to a cryptographic hash.
- Documented and testable: a unit test can assert that reordering,
  renaming, or resizing a member changes the hash, and that reflecting
  the same class twice (two `Reflect<T>()` calls) yields an identical
  hash.
- Anything placed in a struct meant to cross a shared-memory boundary
  should stick to the v1-supported member kinds in
  [0004](0004-member-representation-scope.md) (primitives, fixed-size
  arrays/`std::array`, nested reflected structs, enums) — this is worth
  calling out in README.md as a usage guideline, not just an
  implementation limitation.
