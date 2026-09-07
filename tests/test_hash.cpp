#include "Reflection.hpp"
#include "TestFramework.hpp"

namespace {

struct HashA {
    int a;
    int b;
};

struct HashB { // structurally identical to HashA, different name
    int a;
    int b;
};

struct HashC { // same members as HashA, reordered
    int b;
    int a;
};

} // namespace

REFLECT_CLASS_BEGIN(HashA)
    REFLECT_MEMBER(a)
    REFLECT_MEMBER(b)
REFLECT_CLASS_END()

REFLECT_CLASS_BEGIN(HashB)
    REFLECT_MEMBER(a)
    REFLECT_MEMBER(b)
REFLECT_CLASS_END()

REFLECT_CLASS_BEGIN(HashC)
    REFLECT_MEMBER(b)
    REFLECT_MEMBER(a)
REFLECT_CLASS_END()

TEST_CASE(HashIsStableAndCachedAcrossCalls) {
    const auto& first = reflect::Reflect<HashA>();
    const auto& second = reflect::Reflect<HashA>();
    REQUIRE(&first == &second);
    REQUIRE(first.GetHash() == second.GetHash());
}

TEST_CASE(HashDiffersByNameEvenWithIdenticalLayout) {
    const auto& a = reflect::Reflect<HashA>();
    const auto& b = reflect::Reflect<HashB>();
    REQUIRE(a.GetHash() != b.GetHash());
}

TEST_CASE(HashDiffersOnMemberReorder) {
    const auto& a = reflect::Reflect<HashA>();
    const auto& c = reflect::Reflect<HashC>();
    REQUIRE(a.GetHash() != c.GetHash());
}
