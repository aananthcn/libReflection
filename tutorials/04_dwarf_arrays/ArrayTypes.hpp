// Type definitions for the array-shaped cases this tutorial covers.
// main.cpp is the SOURCE passed to reflection_generate_dwarf() (see
// CMakeLists.txt) and #includes this header locally, so every type
// declared here is discovered automatically -- no listing required.
//
// reflect::Reflect<T>() calls for these types are free to live
// anywhere, including directly in SOURCE itself (main.cpp does
// exactly that) -- see docs/adr/0013's "Fixed bugs" for why that
// used to be a real, must-avoid pitfall and no longer is.
#pragma once

#include <array>

// Same shape as tutorials/03_macros_for_special_cases's Histogram,
// where it needs REFLECT_CLASS_BEGIN(Histogram)/REFLECT_MEMBER(buckets)
// written by hand. Here: nothing. This used to resolve incorrectly
// even via the DWARF pipeline (a real bug: the member's size silently
// came out as 0) -- see docs/adr/0013's "Array-member bug found and
// fixed" for what was wrong and how it was found and fixed.
struct Histogram {
    int buckets[4];
};

// A multi-dimensional C array -- also resolved correctly, as
// "double[2][3]" with the real total size (48 bytes) and element
// count (6), not just the first dimension.
struct Grid {
    double cells[2][3];
};

// std::array<T, N> is a real class wrapping a C array internally, so
// its own debug info already carries a name and size directly --
// this needed no special handling in the DWARF pipeline at all, only
// the raw C-array case above did.
struct Samples {
    std::array<float, 4> values;
};
