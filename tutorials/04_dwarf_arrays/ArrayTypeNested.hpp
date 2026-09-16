#pragma once

// A direct fixed-size C-array member reached through ANOTHER struct's
// member, not directly on the type passed to reflect::Reflect<T>() --
// contrast with ArrayTypes.hpp's Histogram, where the array member is
// on the reflected type itself. The distinction doesn't matter:
// automatic aggregate reflection recurses into every member type with
// no annotation of its own, so this array member would trip the same
// static_assert no matter how many levels down it's reached from --
// see docs/adr/0001. Resolved correctly here via the same DWARF
// pipeline, with zero annotation on either struct.
struct Buckets {
    int counts[8];
};

struct Meter {
    Buckets history;
    int id;
};
