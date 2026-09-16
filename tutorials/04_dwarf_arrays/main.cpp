// tutorials/03_macros_for_special_cases needs REFLECT_CLASS_BEGIN by
// hand for a type with a direct fixed-size array member, because
// automatic aggregate reflection alone can't count one (see
// docs/adr/0001). This tutorial's CMakeLists.txt wires in the SAME
// DWARF-based pipeline as tutorials/01_hello_world instead
// (docs/adr/0013), which resolves a fixed-size array member --
// including a multi-dimensional one, a std::array<T, N>, and one
// reached through another struct's member -- with zero annotation.
// The types themselves live in ArrayTypes.hpp/ArrayTypeNested.hpp,
// not here; see those files' top comments.
//
// This file is itself the SOURCE passed to reflection_generate_dwarf()
// (see CMakeLists.txt), and it calls reflect::Reflect<T>() directly,
// including for Meter (which reaches Buckets's direct array member
// two levels down via Meter::history). That used to be a hard compile
// failure: the extraction driver #includes SOURCE verbatim to force
// DWARF emission, and used to compile it before the generated header
// had real content, so any reflect::Reflect<T>() call living in
// SOURCE fell back to automatic aggregate reflection instead -- which
// hard-fails for a direct array member (docs/adr/0001). Fixed by
// making reflect::Reflect<T>() a no-op under REFLECTION_DWARF_DRIVER_BUILD
// (src/TypeInfo.hpp), defined only on the driver's own throwaway
// compile -- see docs/adr/0013's "Fixed bugs".
#include "ArrayTypeNested.hpp"
#include "ArrayTypes.hpp"
#include <Reflection.hpp>

#include <iostream>

// Every translation unit that calls reflect::Reflect<T>() for one of
// these types must see this include, AFTER their definitions (the
// same declare-before-use rule as REFLECT_CLASS_BEGIN, see
// docs/adr/0010) -- it defines the template specializations that
// make the names below resolve.
#include "generated_dwarf_reflection.hpp"

static void Describe(const char* label, const reflect::ClassReflection& r) {
    std::cout << label << " '" << r.GetName() << "' (" << r.GetSize() << " bytes):\n";
    for (const auto& m : r.GetMembers()) {
        std::cout << "  " << m.GetType() << " " << m.GetName() << " @ offset "
                  << m.GetOffset() << " (size " << m.GetSize() << ", count " << m.GetCount()
                  << ")\n";
    }
}

int main() {
    std::cout << "Zero annotation, resolved via the DWARF pipeline:\n\n";

    Describe("A fixed-size C array member:", reflect::Reflect<Histogram>());
    Describe("A multi-dimensional C array member:", reflect::Reflect<Grid>());
    Describe("A std::array<T, N> member:", reflect::Reflect<Samples>());
    Describe("A direct array member reached two levels down:", reflect::Reflect<Meter>());

    return 0;
}
