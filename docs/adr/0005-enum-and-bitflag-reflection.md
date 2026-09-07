# 0005 — Enum & Bit-Flag Reflection Semantics

**Status:** Decided

## Context

`ClassReflection` carries `enum_name`, `enum_values`, and `bit_flag`
fields but ARCHITECTURE.md doesn't say how they get populated or what
`bit_flag` actually gates.

## Decision

- `REFLECT_ENUM_BEGIN(EnumType)` / `REFLECT_ENUM_VALUE(ValueName)` /
  `REFLECT_ENUM_END()` register an enum the same way classes are
  registered: `Reflect<EnumType>()` returns a `ClassReflection` with
  `type = enum_name = "EnumType"`, `size = sizeof(EnumType)`,
  `members` empty, and `enum_values` populated as
  `{"ValueName" -> static_cast<int64_t>(EnumType::ValueName)}` for each
  registered value.
- `REFLECT_BITFLAG_ENUM_BEGIN(EnumType)` is the same macro family with
  `bit_flag = true` set on the resulting `ClassReflection`. In debug
  builds, `REFLECT_ENUM_END()` for a bit-flag enum asserts every
  registered value is `0` or a power of two, catching a mis-tagged enum
  at registration time instead of letting `bit_flag` silently lie.
  `bit_flag` is purely descriptive metadata (e.g. so a generic
  pretty-printer knows to render `A | B` instead of picking one name) —
  it does not change how `enum_values` is stored.
- A struct member whose type is a reflected enum embeds that enum's
  full `ClassReflection` (including `enum_name`/`enum_values`) as its
  entry in `MemberList`, consistent with 0004's "nesting always embeds
  a full copy" rule — callers never need a separate enum-lookup path
  when walking a struct's members.

## Consequences

- `IsEnum()` (`!enum_name.empty()`) is a reliable, cheap way to branch
  generic code (serializers, pretty-printers) between "struct with
  members" and "enum with values" without a separate type-tag field.
- Bit-flag validation only runs in debug builds to avoid adding runtime
  cost in release builds on constrained embedded (QNX) targets.
