#pragma once

#include "ClassReflection.hpp"

namespace reflect::detail {

/**
 * @brief Computes the 256-bit structural fingerprint of a fully-populated
 * ClassReflection (name/type/size/count, enum info if applicable, and each
 * member's own already-computed hash). See docs/adr/0002.
 */
ClassHash ComputeHash(const ClassReflection& reflection);

/**
 * @brief In debug builds, asserts that a bit-flag enum's values are each
 * 0 or a power of two. No-op for non-bit-flag reflections. See docs/adr/0005.
 */
void ValidateEnum(const ClassReflection& reflection);

} // namespace reflect::detail
