# 04_dwarf_arrays

[`tutorials/03_macros_for_special_cases`](../03_macros_for_special_cases/README.md)
needs `REFLECT_CLASS_BEGIN`/`REFLECT_MEMBER` written by hand for a type
with a direct fixed-size array member, because automatic aggregate
reflection alone can't count one (see
[docs/adr/0001](../../docs/adr/0001-reflection-generation-strategy.md)).
This tutorial wires in the same DWARF-based pipeline as
[`tutorials/01_hello_world`](../01_hello_world/README.md)
([docs/adr/0013](../../docs/adr/0013-dwarf-based-reflection-generation.md))
instead, which resolves all four of these with **zero annotation**:

- **`Histogram`** — a direct fixed-size C array member (`int
  buckets[4];`). The same shape as tutorial 03's `Histogram`, but with
  nothing written near the type at all here. This case used to resolve
  *incorrectly* even through the DWARF pipeline — a real bug where the
  member's size silently came out as `0` — found and fixed; see ADR
  0013's "Fixed bugs".
- **`Grid`** — a multi-dimensional C array (`double cells[2][3];`),
  resolving to the real total size (48 bytes) and element count (6),
  not just the first dimension.
- **`Samples`** — a `std::array<float, 4>` member. `std::array<T, N>`
  is a real class wrapping a C array internally, so its own debug info
  already carries a name and size directly — this needed no special
  handling in the DWARF pipeline at all, unlike the raw C-array case
  above.
- **`Meter`** (`ArrayTypeNested.hpp`) — a direct fixed-size array
  member reached two levels down, via `Meter::history`'s type
  (`Buckets`) rather than on `Meter` itself. Resolves the same way;
  automatic aggregate reflection recurses into every un-annotated
  member type, so it doesn't matter how deep the array member is.

`main.cpp` is itself the `SOURCE` passed to `reflection_generate_dwarf()`
(see `CMakeLists.txt`), and calls `reflect::Reflect<T>()` directly for
all four types, including `Meter`. That used to be disallowed for any
type reaching a direct array member — the extraction driver `#include`s
`SOURCE` verbatim to force DWARF emission, and used to compile it
*before* the generated header had real content, so such a call fell
back to automatic aggregate reflection instead and hard-failed (see
[docs/adr/0001](../../docs/adr/0001-reflection-generation-strategy.md)).
Fixed by making `reflect::Reflect<T>()` a no-op under
`REFLECTION_DWARF_DRIVER_BUILD` (`src/TypeInfo.hpp`) during that one
throwaway bootstrap compile — see
[docs/adr/0013](../../docs/adr/0013-dwarf-based-reflection-generation.md)'s
"Fixed bugs".

Standalone — no other build step needed first:

```sh
cmake -S . -B build
cmake --build build
./build/04_dwarf_arrays
```
