#pragma once

#include "ClassReflection.hpp"

#include <string_view>

namespace reflect {

/// Runtime lookup for code that only has a hash off a shared-memory
/// region (or the wire) and needs to resolve it without knowing the
/// C++ type at compile time. Only finds types that have had
/// Reflect<T>() called on them at least once. See docs/adr/0008.
const ClassReflection* FindByHash(const ClassHash& hash);

/// Same as FindByHash, keyed by the reflected type's name instead.
const ClassReflection* FindByName(std::string_view type_name);

namespace detail {

void RegisterInGlobalRegistry(const ClassReflection& reflection);

} // namespace detail
} // namespace reflect
