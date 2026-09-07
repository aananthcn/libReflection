# 0010 — Header & Macro Sketch

**Status:** Decided (this is the concrete contract 0001–0009 add up to;
implementation should match it unless a real obstacle turns up, in
which case update this file first)

## `src/ClassReflection.hpp` (public API surface)

```cpp
#pragma once
#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace reflect {

struct ClassHash {
    std::uint64_t words[4]{0, 0, 0, 0};
    bool operator==(const ClassHash&) const noexcept;
};

class ClassReflection {
public:
    using MemberList  = std::vector<ClassReflection>;
    using EnumValues  = std::unordered_map<std::string, std::int64_t>;

    ClassReflection() = default;

    // Accessors (thin wrappers over the public fields below).
    const std::string& GetClassName() const noexcept { return name; }
    const std::string& GetType() const noexcept { return type; }
    std::uint32_t GetOffset() const noexcept { return offset; }
    std::uint32_t GetSize() const noexcept { return size; }
    std::uint32_t GetCount() const noexcept { return count; }
    const MemberList& GetMembers() const noexcept { return members; }
    const ClassHash& GetHash() const noexcept { return hash; }
    const std::string& GetEnumName() const noexcept { return enum_name; }
    const EnumValues& GetEnumValues() const noexcept { return enum_values; }
    bool IsBitFlag() const noexcept { return bit_flag; }
    bool IsEnum() const noexcept { return !enum_name.empty(); }
    bool IsArray() const noexcept { return count > 1; }
    const ClassReflection* FindMember(std::string_view name) const noexcept;

    // Fields as specified in ARCHITECTURE.md — left public; accessors
    // above are the sanctioned read path for callers (see ADR 0003).
    std::string name;
    std::string type;
    std::uint32_t offset = 0;
    std::uint32_t size = 0;
    std::uint32_t count = 1;
    MemberList members;
    ClassHash hash{};
    std::string enum_name;
    EnumValues enum_values;
    bool bit_flag = false;
};

// Primary entry point. Specialized by REFLECT_CLASS_*/REFLECT_ENUM_*
// macros; calling this on an unregistered type is a compile error.
template <typename T>
const ClassReflection& Reflect() {
    static_assert(sizeof(T) == 0,
        "T is not reflected — annotate it with REFLECT_CLASS_BEGIN/"
        "REFLECT_ENUM_BEGIN.");
}

const ClassReflection* FindByHash(const ClassHash&);
const ClassReflection* FindByName(std::string_view type_name);

} // namespace reflect
```

## `src/ReflectionMacros.hpp` (registration DSL)

```cpp
#define REFLECT_CLASS_BEGIN(Type)                                          \
    template <> const ::reflect::ClassReflection&                          \
    ::reflect::Reflect<Type>() {                                           \
        using ReflectedT = Type;                                           \
        static const ::reflect::ClassReflection instance = [] {            \
            ::reflect::ClassReflection r;                                  \
            r.name = r.type = #Type;                                       \
            r.size = sizeof(Type);

#define REFLECT_MEMBER(Member)                                             \
            r.members.push_back(                                           \
                ::reflect::detail::ReflectMember<ReflectedT>(               \
                    #Member, offsetof(ReflectedT, Member),                 \
                    r.members.size()));

#define REFLECT_CLASS_END()                                                \
            r.hash = ::reflect::detail::ComputeHash(r);                    \
            ::reflect::detail::RegisterInGlobalRegistry(r);                \
            return r;                                                      \
        }();                                                               \
        return instance;                                                   \
    }

#define REFLECT_ENUM_BEGIN(Type)      /* analogous, sets enum_name */
#define REFLECT_BITFLAG_ENUM_BEGIN(Type) /* same, sets bit_flag = true */
#define REFLECT_ENUM_VALUE(Value)     /* r.enum_values[#Value] = ... */
#define REFLECT_ENUM_END()            /* same tail as REFLECT_CLASS_END */
```

`::reflect::detail::ReflectMember<T>(name, offset, index)` is the piece
that, given the member's compile-time type (recovered via a small
per-member helper macro argument or `decltype` trick — an
implementation detail to finalize in code, not in this sketch), fills
in `type`, `size`, `count`, and recursively nests the member's own
`Reflect<MemberT>()` result when `MemberT` is itself a registered
class/enum, or synthesizes an opaque leaf for primitives/pointers per
[0004](0004-member-representation-scope.md).

## Example usage

```cpp
struct Vec3 { float x, y, z; };
REFLECT_CLASS_BEGIN(Vec3)
    REFLECT_MEMBER(x)
    REFLECT_MEMBER(y)
    REFLECT_MEMBER(z)
REFLECT_CLASS_END()

enum class Color { Red, Green, Blue };
REFLECT_ENUM_BEGIN(Color)
    REFLECT_ENUM_VALUE(Red)
    REFLECT_ENUM_VALUE(Green)
    REFLECT_ENUM_VALUE(Blue)
REFLECT_ENUM_END()

const auto& r = reflect::Reflect<Vec3>();
r.GetMembers().size();       // 3
r.FindMember("y")->GetOffset(); // offsetof(Vec3, y)
```

## Implementation notes (refined while building)

The sketch above was refined during implementation; recording the
deltas here rather than leaving the sketch inaccurate:

- **`TypeInfo<T>` trait replaces the static_assert-on-`Reflect<T>()`
  idea.** Detecting "does a specialization of a function template
  exist" isn't reliably expressible in portable C++20. Instead,
  `reflect::TypeInfo<T>` is a *class* template with a generic primary
  definition (opaque leaf: `type = TypeName<T>()`, `size = sizeof(T)`,
  no members) and `REFLECT_CLASS_BEGIN`/`REFLECT_ENUM_BEGIN` emit a full
  *specialization* of `TypeInfo<T>` rather than of `Reflect<T>()`
  itself. `Reflect<T>()` is now a single, non-macro-generated function
  template that just calls `TypeInfo<T>::Describe()`, hashes the
  result, and registers it — so it never fails to compile; an
  unregistered type simply reflects as an opaque leaf, which is a
  better fit for 0004's "pointers/unregistered types are opaque leaves"
  rule anyway (one mechanism now covers both cases instead of two).
- **No RTTI dependency.** `TypeName<T>()` has explicit overloads for
  every fundamental arithmetic type plus `bool`; anything else falls
  back to the literal string `"<unregistered>"` rather than
  `typeid(T).name()`. This was a deliberate change from the obvious
  typeid-based fallback: some embedded/QNX builds compile with
  `-fno-rtti`, and this library shouldn't force RTTI on a consumer just
  to print a fallback type name for a case (pointers to
  unregistered types) that's already explicitly out of full-fidelity
  scope per 0004.
- **Declare-before-use ordering rule.** Because `REFLECT_MEMBER(Member)`
  expands to `reflect::Reflect<decltype(ReflectedT::Member)>()`, the
  member's type must already have its `TypeInfo` specialization
  (if any) declared earlier in the same translation unit / an included
  header — the same ordering rule C++ requires for any explicit
  template specialization to be visible before first use. In practice:
  **reflect a struct's member types before reflecting the struct
  itself.** This is called out in README.md as a usage rule, not just
  buried here.

## Next step

Implemented in `src/`. See README.md for build instructions and the
usage rule above.
