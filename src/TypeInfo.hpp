#pragma once

#include "AggregateReflection.hpp"
#include "ClassReflection.hpp"
#include "ReflectionHash.hpp"
#include "ReflectionRegistry.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <type_traits>

namespace reflect {

// Leaf type name resolution. Deliberately does NOT fall back to
// typeid(T).name(): this library must not force RTTI on a consumer
// (some embedded/QNX builds use -fno-rtti) just to print a name for a
// case that's already an opaque leaf by design -- see docs/adr/0010
// "Implementation notes".
template <typename T>
const char* TypeName() { return "<unregistered>"; }

template <> inline const char* TypeName<bool>() { return "bool"; }
template <> inline const char* TypeName<char>() { return "char"; }
template <> inline const char* TypeName<signed char>() { return "signed char"; }
template <> inline const char* TypeName<unsigned char>() { return "unsigned char"; }
template <> inline const char* TypeName<short>() { return "short"; }
template <> inline const char* TypeName<unsigned short>() { return "unsigned short"; }
template <> inline const char* TypeName<int>() { return "int"; }
template <> inline const char* TypeName<unsigned int>() { return "unsigned int"; }
template <> inline const char* TypeName<long>() { return "long"; }
template <> inline const char* TypeName<unsigned long>() { return "unsigned long"; }
template <> inline const char* TypeName<long long>() { return "long long"; }
template <> inline const char* TypeName<unsigned long long>() { return "unsigned long long"; }
template <> inline const char* TypeName<float>() { return "float"; }
template <> inline const char* TypeName<double>() { return "double"; }

/**
 * @brief Customization point for describing a type's shape.
 *
 * Primary template, used for any type without a REFLECT_CLASS_BEGIN/
 * REFLECT_ENUM_BEGIN specialization (those always take precedence, since
 * they're full specializations of this same template):
 *   - Plain aggregates (structs with public members, no user-declared
 *     constructors/virtuals) get *automatic* structural reflection --
 *     real member offsets/sizes/types/count, derived from T itself with
 *     no annotation. See docs/adr/0001-reflection-generation-strategy.md.
 *   - Everything else (primitives, unregistered enums/non-aggregates)
 *     is an opaque leaf, as before. See docs/adr/0004 and docs/adr/0010
 *     "Implementation notes".
 */
template <typename T>
struct TypeInfo {
    static ClassReflection Describe() {
        if constexpr (std::is_aggregate_v<T> && !std::is_union_v<T>) {
            return detail::DescribeAggregate<T>();
        } else {
            ClassReflection r;
            r.name = r.type = TypeName<T>();
            r.size = static_cast<std::uint32_t>(sizeof(T));
            r.count = 1;
            return r;
        }
    }
};

template <>
struct TypeInfo<std::string> {
    static ClassReflection Describe() {
        ClassReflection r;
        r.name = r.type = "std::string";
        r.size = static_cast<std::uint32_t>(sizeof(std::string));
        r.count = 1;
        return r;
    }
};

// Fixed-size C array: T arr[N] -> count = N. See docs/adr/0004.
template <typename T, std::size_t N>
struct TypeInfo<T[N]> {
    static ClassReflection Describe() {
        ClassReflection r = TypeInfo<T>::Describe();
        r.count = static_cast<std::uint32_t>(N);
        r.size = static_cast<std::uint32_t>(sizeof(T) * N);
        return r;
    }
};

// std::array<T, N> -> count = N. See docs/adr/0004.
template <typename T, std::size_t N>
struct TypeInfo<std::array<T, N>> {
    static ClassReflection Describe() {
        ClassReflection r = TypeInfo<T>::Describe();
        r.count = static_cast<std::uint32_t>(N);
        r.size = static_cast<std::uint32_t>(sizeof(T) * N);
        return r;
    }
};

// Pointer members are an opaque leaf, never dereferenced -- avoids
// infinite recursion on self-referential types and reflecting into
// memory that may not be owned/valid at registration time. See
// docs/adr/0004.
template <typename T>
struct TypeInfo<T*> {
    static ClassReflection Describe() {
        ClassReflection r;
        r.name = r.type = std::string(TypeName<T>()) + "*";
        r.size = static_cast<std::uint32_t>(sizeof(T*));
        r.count = 1;
        return r;
    }
};

/**
 * @brief Primary entry point: get the (cached, registered) reflection
 * for T. Calling this on a type with no REFLECT_* annotation is not an
 * error -- it returns an opaque leaf via the primary TypeInfo template.
 *
 * NOTE: if T's REFLECT_CLASS_BEGIN/REFLECT_ENUM_BEGIN block is not yet
 * visible (declared earlier in this translation unit / an included
 * header) at the point this is instantiated, T reflects as a leaf
 * instead of using its registered shape. See docs/adr/0010
 * "declare-before-use ordering rule".
 */
template <typename T>
const ClassReflection& Reflect() {
    static const ClassReflection instance = [] {
        ClassReflection r = TypeInfo<T>::Describe();
        r.hash = detail::ComputeHash(r);
        detail::RegisterInGlobalRegistry(r);
        return r;
    }();
    return instance;
}

} // namespace reflect
