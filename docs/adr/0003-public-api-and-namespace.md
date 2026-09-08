# 0003 — Namespace & Public Accessor API

**Status:** Decided

## Context

ARCHITECTURE.md item 3 asks for "public member functions to access
these members" but the fields are already public, and no namespace,
accessor naming, or lookup/entry-point API is specified. Left
unaddressed, this is the part of the design actual calling code touches
the most, so it needs to be nailed down before implementation.

## Decision

**Namespace:** `reflect` — short, matches the `REFLECT_*` macro prefix,
unlikely to collide with `std::` or a future `std::meta`.

**Accessors on `ClassReflection`** (all `const`, `noexcept` where they
can't throw): thin wrappers over the existing public fields, plus a
handful of derived convenience queries. Fields stay public (per
ARCHITECTURE.md's class shown as-is) — the accessors exist because
future callers (and any C++26-migration shim) should go through methods,
not fields, so the shim can change field representation later without
breaking callers.

```
GetName() / GetType() / GetOffset() / GetSize() / GetCount()
GetMembers() / GetHash() / GetEnumName() / GetEnumValues()
IsBitFlag()
IsEnum()      // !enum_name.empty()
IsArray()     // count > 1
FindMember(std::string_view name) const -> const ClassReflection*
```

**Entry points (free functions in `reflect::`):**

```
template<typename T> const ClassReflection& Reflect();
const ClassReflection* FindByHash(const ClassHash&);
const ClassReflection* FindByName(std::string_view);
```

`Reflect<T>()` is the primary, compile-time-checked entry point —
calling it on a type with no `REFLECT_CLASS_BEGIN`/`REFLECT_ENUM_BEGIN`
block is a compile error (see [0010](0010-header-and-macro-sketch.md)
for the enforcement mechanism). `FindByHash`/`FindByName` are the
runtime-lookup path for code that only has a name or a hash off the
wire (e.g. deserialization, IPC) and needs to resolve it to a
`ClassReflection` without knowing `T` at compile time.

## Consequences

- Calling code never touches a registry object directly — just
  `reflect::Reflect<Foo>()` or `reflect::FindByHash(...)`.
- Because `Reflect<T>()` is a template, an unregistered type fails at
  the call site with a clear compile error rather than returning an
  empty/default `ClassReflection` at runtime.
