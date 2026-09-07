#include "Reflection.hpp"
#include "TestFramework.hpp"

namespace {

struct RegistryLookup {
    int value;
};

} // namespace

REFLECT_CLASS_BEGIN(RegistryLookup)
    REFLECT_MEMBER(value)
REFLECT_CLASS_END()

TEST_CASE(FindByNameReturnsSameInstanceAsReflect) {
    const auto& r = reflect::Reflect<RegistryLookup>();
    const auto* found = reflect::FindByName("RegistryLookup");
    REQUIRE(found != nullptr);
    REQUIRE(found == &r);
}

TEST_CASE(FindByHashReturnsSameInstanceAsReflect) {
    const auto& r = reflect::Reflect<RegistryLookup>();
    const auto* found = reflect::FindByHash(r.GetHash());
    REQUIRE(found != nullptr);
    REQUIRE(found == &r);
}

TEST_CASE(FindByNameReturnsNullForUnknownName) {
    REQUIRE(reflect::FindByName("NoSuchType") == nullptr);
}
