#pragma once

// No reflection annotation here at all -- automatic aggregate
// reflection derives the real structure (offsets/sizes/types/count),
// see docs/adr/0001-reflection-generation-strategy.md's revision.
struct HelloWorld {
    int id;
    float value;
    bool enabled;
};
