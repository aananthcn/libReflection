// tutorials/01_hello_world and 02_auto_reflect_legacy_struct show the
// *default* path: automatic reflection, no annotation. This tutorial
// covers the cases that path can't (or shouldn't) handle, where
// REFLECT_CLASS_BEGIN remains the explicit, deliberate choice. See
// docs/adr/0001-reflection-generation-strategy.md's revision for the
// full reasoning behind each case below. (Enums are their own case --
// see tutorials/05_enums.)
//
// (An earlier text-scanning generator, tools/generate_reflection_names.py,
// tried to automate real names for cases like these -- it was built,
// verified working, and then reverted once its founding assumption
// turned out to be wrong; see docs/adr/0012 and docs/adr/0013 for what
// replaces it.)
#include <Reflection.hpp>

#include <iostream>

// Case 1: a direct fixed-size array member. Automatic reflection's
// member-count detection is provably ambiguous for these (see the ADR)
// and refuses to compile rather than risk silently wrong offsets --
// REFLECT_CLASS_BEGIN supports fixed-size arrays natively instead.
struct Histogram {
    int buckets[4];
};
REFLECT_CLASS_BEGIN(Histogram)
    REFLECT_MEMBER(buckets)
REFLECT_CLASS_END()

// Case 2: real, distinguishable names/identity wanted. Automatically
// reflected types all share the name "<aggregate>", so two structurally
// identical-but-different types would hash identically -- a real
// concern for shared-memory IPC message types. Give a type a
// REFLECT_CLASS_BEGIN block whenever that distinction matters.
struct Vec3 {
    float x;
    float y;
    float z;
};
REFLECT_CLASS_BEGIN(Vec3)
    REFLECT_MEMBER(x)
    REFLECT_MEMBER(y)
    REFLECT_MEMBER(z)
REFLECT_CLASS_END()

// Case 3: a class with a constructor and a method -- not an aggregate
// at all, so automatic reflection can't touch it either. Its field is
// public, so REFLECT_CLASS_BEGIN/REFLECT_MEMBER still work fine; only
// a PRIVATE member would additionally need a friend declaration (see
// docs/adr/0013 for why that's a real, non-intrusive-defeating cost,
// and what the DWARF-based direction does about it).
class BoundedCounter {
public:
    BoundedCounter() : count(0) {}
    void Increment() {
        if (count < 100) {
            ++count;
        }
    }

    int count;
};
REFLECT_CLASS_BEGIN(BoundedCounter)
    REFLECT_MEMBER(count)
REFLECT_CLASS_END()

int main() {
    const auto& histogram = reflect::Reflect<Histogram>();
    const auto* buckets = histogram.FindMember("buckets");
    std::cout << "Histogram.buckets is an array of " << buckets->GetCount()
              << " ints (automatic reflection would have refused to compile this)\n";

    const auto& vec3 = reflect::Reflect<Vec3>();
    std::cout << "Vec3 keeps its real name '" << vec3.GetName()
              << "' and member names (" << vec3.FindMember("y")->GetName()
              << ", ...) instead of \"<aggregate>\"/\"field1\"\n";

    const auto& counter = reflect::Reflect<BoundedCounter>();
    std::cout << "BoundedCounter is not an aggregate (constructor + method), "
                 "but its public 'count' field reflects fine by hand: "
              << counter.FindMember("count")->GetName() << "\n";

    // reflect::FindByName only ever resolves macro-registered types
    // like these -- see tutorials/01_hello_world for the auto-reflected
    // (FindByHash-only) case.
    std::cout << "FindByName(\"Vec3\") found it: "
              << std::boolalpha << (reflect::FindByName("Vec3") == &vec3) << "\n";

    return 0;
}
