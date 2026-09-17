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
 * @brief Computes the 256-bit declaration-level fingerprint of a
 * fully-populated ClassReflection (name, and per member: name/type/count,
 * plus enum info if applicable). Deliberately excludes offset/size, and
 * deliberately does NOT recurse into a member's own DeclHash the way
 * ComputeHash recurses into a member's ClassHash -- it uses each member's
 * type *name string* directly instead. This keeps DeclHash computable
 * from a flat (name, member[{name, type_name}]) declaration with no
 * nested structure, which is exactly the shape a wire-format declaration
 * (e.g. Bytesoup's clsinf archive) can also produce -- see
 * docs/adr/0016-declaration-level-class-hash.md.
 */
DeclHash ComputeDeclHash(const ClassReflection& reflection);

/**
 * @brief In debug builds, asserts that a bit-flag enum's values are each
 * 0 or a power of two. No-op for non-bit-flag reflections. See docs/adr/0005.
 */
void ValidateEnum(const ClassReflection& reflection);

} // namespace reflect::detail
