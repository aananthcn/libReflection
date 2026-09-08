// The "hello world" of a reflection library, now on the DWARF-based
// pipeline: no annotation of ANY kind, in the class itself or
// anywhere else, for ANY of the three types below -- plain aggregate,
// private members, or a public-member class. This directory's
// CMakeLists.txt compiles this file a second time with debug info,
// reads the real name/type/offset/size of every member straight out
// of DWARF (which doesn't respect C++ access control), and generates
// generated_dwarf_reflection.hpp automatically as part of a normal
// build. See docs/adr/0013-dwarf-based-reflection-generation.md.
#include "HelloWorld.hpp"
#include <Reflection.hpp>

#include <iomanip>
#include <iostream>


// ----- Example Code Section Added by Aananth -------------
// Not an aggregate at all (user-declared constructor) and has private
// members. Neither automatic reflection nor REFLECT_CLASS_BEGIN
// (without an intrusive friend declaration) could reach x/y -- but
// DWARF debug info records them unconditionally, same as it would for
// a debugger, so this resolves correctly with zero changes here.
class PoorPoint {
public:
    PoorPoint() : x{}, y{} {}
private:
    int x;
    int y;
};

// A genuine aggregate (no constructor, public members) -- resolves
// correctly too, via the same DWARF pipeline, not automatic
// reflection's positional-name fallback.
class BetterPoint {
public:
    int x;
    int y;
};

// A brand new type, added after the pipeline was already wired up --
// proving the workflow: edit, build once, run, and it just resolves.
struct Widget {
    double weight;
    char code;
};

// Every translation unit that calls reflect::Reflect<T>() for one of
// the types above must see this include, AFTER their definitions (the
// same declare-before-use rule as REFLECT_CLASS_BEGIN, see
// docs/adr/0010) -- it defines the template specializations that make
// the names below resolve.
#include "generated_dwarf_reflection.hpp" // *NOTE*: This file MUST be included after all class and struct declarations.


static void check_this_aswell() {
    const auto& r2 = reflect::Reflect<PoorPoint>();
    const auto& r3 = reflect::Reflect<BetterPoint>();

    std::cout << std::endl;
    std::cout << "r2's class name: " << r2.GetClassName() << "\n";
    for (const auto& m : r2.GetMembers()) {
        std::cout << "  " << m.GetType() << " " << m.GetClassName() << " @ offset " << m.GetOffset() << "\n";
    }
    std::cout << "r3's class name: " << r3.GetClassName() << "\n";
    for (const auto& m : r3.GetMembers()) {
        std::cout << "  " << m.GetType() << " " << m.GetClassName() << " @ offset " << m.GetOffset() << "\n";
    }
    const auto& r4 = reflect::Reflect<Widget>();
    std::cout << "r4's class name: " << r4.GetClassName() << "\n";
    for (const auto& m : r4.GetMembers()) {
        std::cout << "  " << m.GetType() << " " << m.GetClassName() << " @ offset " << m.GetOffset() << "\n";
    }
    std::cout << std::endl;
}
// ----------------------------------------------------------


int main() {
    const auto& r = reflect::Reflect<HelloWorld>();

    std::cout << "\nHello, reflection!\n";
    std::cout << "Describing a '" << r.GetClassName() << "' (" << r.GetSize()
              << " bytes), reflected with zero annotation:\n";

    for (const auto& member : r.GetMembers()) {
        std::cout << "  " << member.GetType() << " " << member.GetClassName() << " @ offset "
                  << member.GetOffset() << " (size " << member.GetSize() << ")\n";
    }

    std::cout << "ClassHash: " << std::hex;
    for (auto word : r.GetHash().words) {
        std::cout << std::setw(16) << std::setfill('0') << word << " ";
    }
    std::cout << std::dec << "\n";

    const auto* found = reflect::FindByName("HelloWorld");
    std::cout << "FindByName(\"HelloWorld\") resolved to the same reflection: "
              << std::boolalpha << (found == &r) << "\n";

    check_this_aswell();

    return 0;
}
