# 0009 — version.txt vs. ClassHash, Intended Use Case

**Status:** Confirmed by user

## Context

There are two independent "versioning" concepts in this project that
must not be conflated: the library's own release version, and
`ClassHash`'s role as a per-type fingerprint. ARCHITECTURE.md doesn't
state *why* a class-level 256-bit hash is needed, which matters because
the answer shapes how much precision the hash needs (see
[0002](0002-class-hash-algorithm.md)).

## Decision

- `version.txt` is the **library's own** release version (see
  [0006](0006-build-system-and-qnx-portability.md) for its exact
  format/parsing) — unrelated to any reflected user type.
- `ClassHash` exists for **cross-process layout-drift detection over
  shared-memory IPC**: the user has confirmed any cross-process
  boundary in this system uses shared-memory-based IPC, meaning two
  independently-built processes overlay the *same raw memory* with a
  struct definition each compiled its own copy of — there is no
  serialization step to catch a mismatch. `ClassHash` lets both sides
  compare a cheap fingerprint of a struct's layout before trusting a
  shared-memory region, instead of discovering a drift as silent memory
  corruption or misinterpreted fields.
- This confirms, and sharpens, [0004](0004-member-representation-scope.md)'s
  scope decision: shared-memory structs cannot contain heap-owning
  members (`std::string`, `std::vector`, pointers into process-local
  heaps are meaningless across a process boundary) anyway, so treating
  those as opaque/out-of-scope for full reflection was already the
  right call independent of this confirmation.

## Consequences

- The hash only needs to be good enough to catch *accidental* layout
  drift (a rebuilt producer/consumer pair going out of sync), not
  adversarial tampering — FNV-1a as decided in
  [0002](0002-class-hash-algorithm.md) remains appropriate; no need to
  move to a cryptographic hash.
- Anything placed in a struct meant to cross a shared-memory boundary
  should stick to the v1-supported member kinds in 0004 (primitives,
  fixed-size arrays/`std::array`, nested reflected structs, enums) —
  this is worth calling out in README.md as a usage guideline, not just
  an implementation limitation.
