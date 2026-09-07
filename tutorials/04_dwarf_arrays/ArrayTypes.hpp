// Type definitions ONLY -- no reflect::Reflect<T>() calls anywhere in
// this file. This is deliberate, not incidental: this header (not
// main.cpp) is the SOURCE passed to reflection_generate_dwarf() below,
// which means the extraction driver #includes THIS file to force
// DWARF emission (see docs/adr/0013). If a reflect::Reflect<T>() call
// for one of these array-containing types lived in the same file the
// driver #includes, the driver's bootstrap compile (before the
// generated header has real content yet) would fall back to automatic
// aggregate reflection for it -- which correctly HARD-FAILS to compile
// for a direct array member, by design (see docs/adr/0001). Keeping
// the actual reflect::Reflect<T>() calls in main.cpp, a file the
// driver never touches, avoids that entirely.
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
