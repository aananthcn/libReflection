// The scenario this tutorial demonstrates: a large existing codebase
// with structs the original authors won't let you modify, and where
// writing/maintaining a hand-written REFLECT_CLASS_BEGIN registration
// per class doesn't scale (10,000 classes = 10,000 files to keep in
// sync forever). See docs/adr/0001-reflection-generation-strategy.md.
//
// LegacyVector3/LegacyTransform (in LegacyTypes.hpp) stand in for such
// classes: no REFLECT_CLASS_BEGIN block anywhere, no annotation of any
// kind, not even a separate hand-written registration file --
// automatic aggregate reflection gets the real structure with zero
// annotation. Real names are a separate, harder problem this tutorial
// deliberately does NOT solve -- see
// docs/adr/0012-generated-reflection-names.md (a text-scanning
// generator that was built, verified, and reverted) and
// docs/adr/0013-dwarf-based-reflection-generation.md (the current
// direction).
#include "LegacyTypes.hpp"
#include <Reflection.hpp>

#include <iostream>

using legacy_codebase_you_cannot_touch::LegacyTransform;

int main() {
    const auto& r = reflect::Reflect<LegacyTransform>();

    std::cout << "Reflected '" << r.GetType() << "' (" << r.GetSize()
              << " bytes) with zero annotation:\n";
    for (const auto& member : r.GetMembers()) {
        std::cout << "  " << member.GetName() << " (" << member.GetType()
                  << ") @ offset " << member.GetOffset() << ", size "
                  << member.GetSize() << "\n";
        for (const auto& nested : member.GetMembers()) {
            std::cout << "    " << nested.GetName() << " (" << nested.GetType()
                      << ") @ relative offset " << nested.GetOffset() << "\n";
        }
    }

    std::cout << "\nNote: member/type names are positional (\"field0\", "
                 "\"<aggregate>\", ...) -- see the README for why, and how "
                 "to opt into real names with REFLECT_CLASS_BEGIN instead.\n";

    return 0;
}
