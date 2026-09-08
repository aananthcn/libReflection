# 05_enums

Enums are never aggregates, so automatic reflection has no path to
them, and
[docs/adr/0013](../../docs/adr/0013-dwarf-based-reflection-generation.md)'s
DWARF-based generator is about class members, not enum value names —
it doesn't cover them either. That leaves two options, and `main.cpp`
shows both.

## Part A — `REFLECT_ENUM_BEGIN` (the supported path)

```cpp
enum class LogLevel { Debug, Info, Warning, Error };
REFLECT_ENUM_BEGIN(LogLevel)
    REFLECT_ENUM_VALUE(Debug)
    REFLECT_ENUM_VALUE(Info)
    REFLECT_ENUM_VALUE(Warning)
    REFLECT_ENUM_VALUE(Error)
REFLECT_ENUM_END()
```

One hand-written line per value, and the enum then flows through the
same `reflect::Reflect<T>()` machinery as every other registered type:
`GetEnumValues()` returns the name→value map, and `FindByName("LogLevel")`
resolves (macro-registered types resolve by name; auto-reflected ones
are `FindByHash`-only — see
[`tutorials/01_hello_world`](../01_hello_world/README.md)).

## Part B — zero-annotation enum↔string in plain C++20

`enum_str<V>()` / `name_of(value)` recover an enumerator's name with
**no macro and no table**: a function template parameterised on the
enumerator *value* bakes its source spelling into `__PRETTY_FUNCTION__`
(a GCC/Clang builtin; `std::source_location::function_name()` is the
standard-blessed equivalent), which is sliced back out at compile time
— the same trick `magic_enum` uses. Works for both a classic unscoped
`enum` and a C++20 scoped `enum class`, is `constexpr` (so
`static_assert(enum_str<Direction::West>() == "West")` holds), and a
value that names no enumerator comes back as `"<unknown>"` rather than
crashing.

This part is **not** libReflection — just plain C++ — but it's the
natural thing to reach for when all you need is enum↔string without
maintaining a `REFLECT_ENUM_VALUE` list. Part B also shows the scoped
vs. unscoped contrast directly: a fixed underlying type
(`enum class Direction : std::uint8_t`), qualified names, and the
C++20 `using enum` declaration.

Standalone — no other build step needed first:

```sh
cmake -S . -B build
cmake --build build
./build/05_enums
```
