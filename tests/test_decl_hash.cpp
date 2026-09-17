#include "Reflection.hpp"
#include "ReflectionHash.hpp" // internal header -- white-box test of ComputeDeclHash's offset/size independence
#include "TestFramework.hpp"

namespace {

struct DeclHashA {
    int a;
    int b;
};

struct DeclHashB { // structurally identical to DeclHashA, different name
    int a;
    int b;
};

struct DeclHashC { // same members as DeclHashA, reordered
    int b;
    int a;
};

} // namespace

REFLECT_CLASS_BEGIN(DeclHashA)
    REFLECT_MEMBER(a)
    REFLECT_MEMBER(b)
REFLECT_CLASS_END()

REFLECT_CLASS_BEGIN(DeclHashB)
    REFLECT_MEMBER(a)
    REFLECT_MEMBER(b)
REFLECT_CLASS_END()

REFLECT_CLASS_BEGIN(DeclHashC)
    REFLECT_MEMBER(b)
    REFLECT_MEMBER(a)
REFLECT_CLASS_END()

TEST_CASE(DeclHashIsStableAndCachedAcrossCalls) {
    const auto& first = reflect::Reflect<DeclHashA>();
    const auto& second = reflect::Reflect<DeclHashA>();
    REQUIRE(&first == &second);
    REQUIRE(first.GetDeclHash() == second.GetDeclHash());
}

TEST_CASE(DeclHashDiffersByNameEvenWithIdenticalLayout) {
    const auto& a = reflect::Reflect<DeclHashA>();
    const auto& b = reflect::Reflect<DeclHashB>();
    REQUIRE(a.GetDeclHash() != b.GetDeclHash());
}

TEST_CASE(DeclHashDiffersOnMemberReorder) {
    // Declaration order is part of the declaration -- reordering members
    // changes DeclHash, same as it changes ClassHash.
    const auto& a = reflect::Reflect<DeclHashA>();
    const auto& c = reflect::Reflect<DeclHashC>();
    REQUIRE(a.GetDeclHash() != c.GetDeclHash());
}

TEST_CASE(DeclHashAndClassHashAreDistinctEvenForTheSameType) {
    const auto& a = reflect::Reflect<DeclHashA>();
    // Not a meaningful comparison in general (different bit widths mean
    // nothing about equal/unequal content), but the two must be reachable
    // as genuinely different values/types -- guards against a copy-paste
    // bug that wires GetDeclHash() to the same storage as GetHash().
    REQUIRE(a.GetHash().words[0] != a.GetDeclHash().words[0] ||
            a.GetHash().words[1] != a.GetDeclHash().words[1] ||
            a.GetHash().words[2] != a.GetDeclHash().words[2] ||
            a.GetHash().words[3] != a.GetDeclHash().words[3]);
}

TEST_CASE(DeclHashIsIndependentOfOffsetAndSizeUnlikeClassHash) {
    // The whole point of DeclHash (docs/adr/0016): two ClassReflection
    // values with the same name/member declaration but different
    // offset/size (as if produced by two different ABIs/compilers) must
    // produce the SAME DeclHash, while ComputeHash (ClassHash) must
    // still tell them apart. Built by hand, not via Reflect<T>(), since
    // one compiled program only ever gives one real layout for a type.
    reflect::ClassReflection narrow;
    narrow.name = narrow.type = "SameDeclDifferentLayout";
    narrow.size = 8;
    {
        reflect::ClassReflection m;
        m.name = "a";
        m.type = "int32_t";
        m.count = 1;
        m.offset = 0;
        m.size = 4;
        narrow.members.push_back(m);
    }
    {
        reflect::ClassReflection m;
        m.name = "b";
        m.type = "int32_t";
        m.count = 1;
        m.offset = 4;
        m.size = 4;
        narrow.members.push_back(m);
    }

    reflect::ClassReflection padded = narrow;
    padded.size = 16;             // as if a stricter ABI padded the whole struct
    padded.members[1].offset = 8; // and pushed member b further out

    REQUIRE(reflect::detail::ComputeDeclHash(narrow) == reflect::detail::ComputeDeclHash(padded));
    REQUIRE(reflect::detail::ComputeHash(narrow) != reflect::detail::ComputeHash(padded));
}

TEST_CASE(FindByDeclHashReturnsSameInstanceAsReflect) {
    const auto& r = reflect::Reflect<DeclHashA>();
    const auto* found = reflect::FindByDeclHash(r.GetDeclHash());
    REQUIRE(found != nullptr);
    REQUIRE(found == &r);
}

TEST_CASE(FindByDeclHashReturnsNullForUnknownHash) {
    reflect::DeclHash bogus{{1, 2, 3, 4}};
    REQUIRE(reflect::FindByDeclHash(bogus) == nullptr);
}
