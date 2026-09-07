#pragma once

// Stands in for a struct from an existing codebase you can't modify:
// no reflection annotation of any kind. Automatic aggregate reflection
// derives the real offsets/sizes/types/count -- see
// docs/adr/0001-reflection-generation-strategy.md's revision.

namespace legacy_codebase_you_cannot_touch {

struct LegacyVector3 {
    float x;
    float y;
    float z;
};

struct LegacyTransform {
    LegacyVector3 position; // nested aggregate -- auto-reflected recursively too
    LegacyVector3 scale;
};

} // namespace legacy_codebase_you_cannot_touch
