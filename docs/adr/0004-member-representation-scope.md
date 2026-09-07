# 0004 — Member Representation Scope (v1)

**Status:** Decided; refined twice. [0001](0001-reflection-generation-strategy.md)'s
revision means "unregistered" no longer means "opaque leaf" across the
board — an unregistered *aggregate* now gets real automatic
offset/size/type/count reflection with no annotation.
[0013](0013-dwarf-based-reflection-generation.md) adds a **third**
mechanism (DWARF-based, zero-annotation, reaches private members and
non-aggregates too). This page's scope decisions (which member kinds
are in/out) mostly still hold across all three mechanisms; see
"Re-verified against the DWARF pipeline" below for what was checked
directly and what needed a caveat or a fix.

## Context

`ClassReflection` models a member's shape with `offset`, `size`,
`count` — a fixed-layout model. Real C++ classes contain pointers,
references, and dynamic containers (`std::vector`, `std::string`,
`std::map`, ...) whose size isn't known from layout alone.
ARCHITECTURE.md doesn't say which of these must be supported, so the
scope needs an explicit, recorded boundary.

## Decision

**In scope for v1:**
- Primitive/arithmetic types, `bool`, and `std::string` (opaque leaf —
  `type = "std::string"`, `count = 1`, no members).
- Registered `class`/`struct` members, nested by value.
- Fixed-size C arrays (`T arr[N]`) and `std::array<T, N>`: `count = N`.
- Registered enums (see [0005](0005-enum-and-bitflag-reflection.md)).

**Explicitly out of scope for v1** (documented limitation, not a bug):
- Raw pointer and reference members — opaque leaf (`type` = e.g.
  `"Foo*"`), never dereferenced/recursed into. Deliberate: recursing
  risks infinite recursion on self-referential/linked structures, and
  a pointer's pointee often isn't owned/valid at registration time.
- Dynamic containers (`std::vector`, `std::map`, etc., beyond the
  `std::string` special case) — size is a runtime property, doesn't
  fit the static `offset`/`size`/`count` model. Revisit if/when needed,
  likely as a different, instance-aware API.
- Classes with virtual base classes — `offsetof` on such types is
  undefined behavior; `REFLECT_CLASS_BEGIN` guards against the
  clearly-unsafe cases where practical.

## Consequences

- Reflecting an unsupported member type degrades gracefully (opaque
  leaf for pointers/refs) or fails to compile (dynamic containers,
  virtual-base classes) — never silently wrong offsets. This briefly
  didn't hold for the DWARF path and a virtual base class (a real bug,
  found and fixed — see below).
- Keeps v1 minimal per ARCHITECTURE.md's instruction to trim scope
  rather than gold-plate.

## Re-verified against the DWARF pipeline

[0013](0013-dwarf-based-reflection-generation.md) reads compiled DWARF
directly rather than evaluating a C++ expression, so each claim above
was checked against it directly (real compiles, real DWARF):

- **Pointers**: still a correct opaque leaf, including
  self-referential types (`Node* next` → `"Node*"`, no recursion). ✓
- **`std::array<T, N>`'s element count is not recoverable via the
  DWARF path** — `count` comes out `1`, unlike the macro/automatic path
  where `count = N` still holds. `std::array` is a real class wrapping
  a C array internally, so its own `DW_TAG_structure_type` resolves
  directly (correct name/size) without the array-count logic ever
  running. A documented gap (size/name are correct; only `GetCount()`
  is affected), not silent-wrong-data.
- **Dynamic containers are not specially excluded by the DWARF path** —
  they resolve like any other member, reporting the real static
  control-block size (e.g. `std::vector<int>` → 24 bytes), never the
  dynamic contents. Consistent with this page's static model and the
  shared-memory-IPC warning elsewhere; just don't assume this path
  never mentions `std::vector` — it does, faithfully, at the
  control-block level.
- **Fixed a real bug found while checking this: namespace-qualified
  type names were silently truncated.** `parse_name()` stripped
  objdump's `"(indirect string, offset: 0x...): <name>"` wrapper via
  `raw.rsplit(":", 1)` — for any STL type (`std::vector`, `std::string`,
  ...), the last `:` in the string lands inside the name's own `::`,
  not the wrapper boundary, so e.g. `std::vector<int>` resolved to
  `"allocator<int> >"` instead of the real
  `"vector<int, std::allocator<int> >"`. Fixed: finds the literal
  `"): "` delimiter instead. Covered by `TestParseName` and
  `test_namespace_qualified_type_name_is_not_truncated`.
- **A real, serious bug, since fixed: a class with a virtual base class
  used to silently resolve to zero members and byte_size 0** — not a
  compile error, not an abstention, contradicting this page's "never
  silently wrong" guarantee. Root cause and fix tracked in
  [0013](0013-dwarf-based-reflection-generation.md)'s "Fixed bugs" (GCC
  didn't emit a full definition for such a type unless its destructor
  was actually called somewhere in compiled code; `find_type()` also
  didn't check for an incomplete-declaration DIE). This page's
  "never silently wrong" guarantee holds again.
- **Lower-severity issue, found alongside it, since fixed**: DWARF
  exposed the compiler-generated vtable pointer as an ordinary member
  (`_vptr.Base`, type `"<unknown>**"`) for any class with a virtual
  function. Fixed in [0013](0013-dwarf-based-reflection-generation.md)'s
  "Fixed bugs": `find_type()` now excludes any `_vptr.`-prefixed member
  entirely — it was never a declared data member.
