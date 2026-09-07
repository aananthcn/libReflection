# 01_hello_world

Every type in `main.cpp` reflects with **zero annotation of any
kind** — no `REFLECT_CLASS_BEGIN`, no `friend` declaration, nothing
written in or near the class — via the DWARF-based pipeline (see
[docs/adr/0013](../../docs/adr/0013-dwarf-based-reflection-generation.md)):

- **`HelloWorld`** (in `HelloWorld.hpp`) — a plain aggregate.
- **`PoorPoint`** — a user-declared constructor *and* private members.
  Neither automatic reflection nor `REFLECT_CLASS_BEGIN` (without an
  intrusive `friend` declaration) could ever reach `x`/`y` here — this
  is the case [0012](../../docs/adr/0012-generated-reflection-names.md)'s
  text-scanning generator was reverted over, and exactly the case
  DWARF exists to solve, since DWARF debug info records a member's
  name/type/offset unconditionally, the same way a debugger can
  already inspect a private field.
- **`BetterPoint`** — public members, no constructor; resolves with
  its real name too, not automatic reflection's `"<aggregate>"`
  fallback.

This directory's `CMakeLists.txt` compiles `main.cpp` a second time
with debug info, reads every type's real structure straight out of
the resulting DWARF, and generates
`generated_dwarf_reflection.hpp` — all as ordinary build steps, no
separate manual step. Add a brand-new type to `main.cpp` (public,
private, aggregate or not) and it resolves correctly on the very next
`cmake --build`, with no changes anywhere else.

Standalone — no other build step needed first:

```sh
cmake -S . -B build
cmake --build build
./build/01_hello_world
```
