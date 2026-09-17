#pragma once

#include "ClassReflection.hpp"

#include <string_view>

namespace reflect {

/// Runtime lookup for code that only has a hash off a shared-memory
/// region (or the wire) and needs to resolve it without knowing the
/// C++ type at compile time. Only finds types that have had
/// Reflect<T>() called on them at least once. See docs/adr/0008.
const ClassReflection* FindByHash(const ClassHash& hash);

/// Same as FindByHash, keyed by DeclHash instead of ClassHash -- for a
/// caller that only has a declaration-level fingerprint (e.g. one it
/// computed itself from a wire-format declaration) and wants to find a
/// matching reflected type without knowing its C++ name. See
/// docs/adr/0016-declaration-level-class-hash.md.
const ClassReflection* FindByDeclHash(const DeclHash& hash);

/// Same as FindByHash, keyed by the reflected type's name instead.
const ClassReflection* FindByName(std::string_view type_name);

namespace detail {

void RegisterInGlobalRegistry(const ClassReflection& reflection);

} // namespace detail
} // namespace reflect
