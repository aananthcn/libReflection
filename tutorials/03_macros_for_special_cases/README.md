# 03_macros_for_special_cases

`01_hello_world` and `02_auto_reflect_legacy_struct` show the
*default* path — automatic reflection, zero annotation. This tutorial
covers the cases where `REFLECT_CLASS_BEGIN`/`REFLECT_ENUM_BEGIN`
remain the deliberate, hand-written choice instead, per
[docs/adr/0001-reflection-generation-strategy.md](../../docs/adr/0001-reflection-generation-strategy.md)'s
revision:

1. **Enums, always** — there's no automatic path for enum value names
   at all; `REFLECT_ENUM_BEGIN` is mandatory.
2. **A direct fixed-size array member** — automatic reflection's
   member-count detection is provably ambiguous for these and refuses
   to compile rather than guess; `REFLECT_CLASS_BEGIN` supports
   fixed-size arrays natively.
3. **Real, distinguishable names/identity** — automatically reflected
   types all share the name `"<aggregate>"`, so two different but
   structurally identical types would hash identically. Give a type a
   `REFLECT_CLASS_BEGIN` block whenever that distinction matters (e.g.
   two different shared-memory IPC message types with the same
   layout).
4. **Non-aggregate types** (`BoundedCounter`: a constructor and a
   method) — automatic reflection never attempts these either, but a
   *public* field still reflects fine by hand. A *private* field would
   need a `friend` declaration too — a real, intrusive cost; see
   [docs/adr/0013](../../docs/adr/0013-dwarf-based-reflection-generation.md)
   for why that specific case (private members in code you can't
   modify) is what motivated moving to a DWARF-based approach instead
   of more text-scanning.

Standalone — no other build step needed first:

```sh
cmake -S . -B build
cmake --build build
./build/03_macros_for_special_cases
```
