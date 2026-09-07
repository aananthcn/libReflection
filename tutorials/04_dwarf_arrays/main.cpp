// tutorials/03_macros_for_special_cases needs REFLECT_CLASS_BEGIN by
// hand for a type with a direct fixed-size array member, because
// automatic aggregate reflection alone can't count one (see
// docs/adr/0001). This tutorial's CMakeLists.txt wires in the SAME
// DWARF-based pipeline as tutorials/01_hello_world instead
// (docs/adr/0013), which resolves a fixed-size array member --
// including a multi-dimensional one, and std::array<T, N> -- with
// zero annotation. The types themselves live in ArrayTypes.hpp, not
// here -- see that file's top comment for why that separation matters
// for this particular tutorial.
#include "ArrayTypes.hpp"
#include <Reflection.hpp>

#include <iostream>

// Every translation unit that calls reflect::Reflect<T>() for one of
// ArrayTypes.hpp's types must see this include, AFTER their
// definitions (the same declare-before-use rule as REFLECT_CLASS_BEGIN,
// see docs/adr/0010) -- it defines the template specializations that
// make the names below resolve.
#include "generated_dwarf_reflection.hpp"

static void Describe(const char* label, const reflect::ClassReflection& r) {
    std::cout << label << " '" << r.GetClassName() << "' (" << r.GetSize() << " bytes):\n";
    for (const auto& m : r.GetMembers()) {
        std::cout << "  " << m.GetType() << " " << m.GetClassName() << " @ offset "
                  << m.GetOffset() << " (size " << m.GetSize() << ", count " << m.GetCount()
                  << ")\n";
    }
}

int main() {
    std::cout << "Zero annotation, resolved via the DWARF pipeline:\n\n";

    Describe("A fixed-size C array member:", reflect::Reflect<Histogram>());
    Describe("A multi-dimensional C array member:", reflect::Reflect<Grid>());
    Describe("A std::array<T, N> member:", reflect::Reflect<Samples>());

    return 0;
}
