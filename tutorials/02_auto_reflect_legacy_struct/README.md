# 02_auto_reflect_legacy_struct

Demonstrates automatic aggregate reflection: `LegacyVector3` and
`LegacyTransform` (in `LegacyTypes.hpp`) have **no**
`REFLECT_CLASS_BEGIN` block, no separate registration file, nothing —
they stand in for a class from an existing codebase you can't modify.
`reflect::Reflect<T>()` still returns real member offsets, sizes,
types, and count, recursing into the nested `LegacyVector3` members
automatically too.

See
[docs/adr/0001-reflection-generation-strategy.md](../../docs/adr/0001-reflection-generation-strategy.md)
for how this works and its limits — in short:

- Member/type **names** are positional (`"field0"`, `"<aggregate>"`),
  not the real source names, because no annotation means nothing
  records the real names anywhere in the compiled program. Use
  `REFLECT_CLASS_BEGIN`/`REFLECT_MEMBER` (see
  [`../03_macros_for_special_cases/`](../03_macros_for_special_cases/))
  for real names.
- A struct with a direct fixed-size array member (`int flags[3];`)
  cannot go through this automatic path — it needs
  `REFLECT_CLASS_BEGIN` instead (a clear compile error tells you so,
  it never silently produces wrong offsets).

An earlier attempt at recovering real names automatically (a
text-scanning generator) was built, verified working, and then
reverted — see
[docs/adr/0012](../../docs/adr/0012-generated-reflection-names.md) for
why, and [docs/adr/0013](../../docs/adr/0013-dwarf-based-reflection-generation.md)
for the current direction.

Standalone — no other build step needed first:

```sh
cmake -S . -B build
cmake --build build
./build/02_auto_reflect_legacy_struct
```
