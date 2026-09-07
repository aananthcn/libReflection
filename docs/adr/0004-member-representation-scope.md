# 0004 — Member Representation Scope (v1)

**Status:** Decided; refined by [0001](0001-reflection-generation-strategy.md)'s
revision — "unregistered" below no longer means "opaque leaf" across the board.
An unregistered *aggregate* (plain struct, no array members) now gets
real automatic offset/size/type/count reflection with no
`REFLECT_CLASS_BEGIN` block. Everything on this page about *which
member kinds* are supported (arrays, nested structs, pointers as
leaves, dynamic containers out of scope) still holds for both the
macro-registered and the automatic path.

## Context

`ClassReflection` models a member's shape with `offset`, `size`, `count`
— a fixed-layout model. Real C++ classes contain pointers, references,
and dynamic containers (`std::vector`, `std::string`, `std::map`, ...)
whose size isn't known from layout alone. ARCHITECTURE.md doesn't say
which of these must be supported, so the scope needs an explicit,
recorded boundary rather than being discovered ad hoc during
implementation.

## Decision

**In scope for v1:**
- Primitive/arithmetic types, `bool`, and `std::string` (treated as an
  opaque leaf type — `type = "std::string"`, `count = 1`, no members).
- Registered `class`/`struct` members, nested by value (matches
  `MemberList = std::vector<ClassReflection>` already holding
  `ClassReflection` by value — nesting always embeds a full copy of the
  member's own reflection).
- Fixed-size C arrays (`T arr[N]`) and `std::array<T, N>`: `count = N`.
- Registered enums (see [0005](0005-enum-and-bitflag-reflection.md)).

**Explicitly out of scope for v1** (documented limitation, not a bug):
- Raw pointer and reference members. Reflected as an opaque leaf
  (`type` = e.g. `"Foo*"`), never dereferenced/recursed into. This is a
  deliberate choice, not an oversight: recursing into pointee types
  risks infinite recursion on self-referential/linked structures
  (a node type pointing to itself), and a pointer's pointee often isn't
  even owned/valid at reflection-registration time.
- Dynamic containers (`std::vector`, `std::map`, `std::unordered_map`,
  etc., beyond the `std::string` special case above). Their size is a
  runtime property of a specific instance, which doesn't fit the
  static `offset`/`size`/`count` model this `ClassReflection` shape
  describes. Revisit if/when a use case needs it — likely as a
  different, instance-aware API rather than forcing it into this
  struct.
- Classes with virtual base classes (multiple/virtual inheritance).
  `offsetof` on such types is undefined behavior; `REFLECT_CLASS_BEGIN`
  will `static_assert(std::is_standard_layout_v<T> || ...)`-style guard
  against the clearly-unsafe cases where practical.

## Consequences

- Reflecting a class containing an unsupported member type either
  degrades gracefully (opaque leaf for pointers/refs) or fails to
  compile with a clear message (dynamic containers not wrapped in a
  helper, virtual-base classes) — never silently wrong offsets.
- This keeps the v1 implementation minimal per ARCHITECTURE.md's
  explicit instruction to trim scope rather than gold-plate.
