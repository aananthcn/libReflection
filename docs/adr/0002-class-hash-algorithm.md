# 0002 — ClassHash Algorithm

**Status:** Decided

## Context

`ClassHash` is 256 bits (`uint64_t words[4]`). ARCHITECTURE.md specifies
the shape but not the algorithm or what it hashes over. Two questions:
*what* gets hashed, and *how*.

A cryptographic hash (SHA-256) is unnecessary — this is a structural
fingerprint used to detect layout drift between two independently
compiled binaries (see [0009](0009-versioning-and-hash-purpose.md)), not
a security boundary. A cryptographic hash would also be significantly
harder to implement correctly as `constexpr`/portable C++20 with zero
dependencies, working against the "minimal implementation" mandate.

## Decision

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
  this use case).
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
  collision.
- Documented and testable: a unit test can assert that reordering,
  renaming, or resizing a member changes the hash, and that reflecting
  the same class twice (two `Reflect<T>()` calls) yields an identical
  hash.
