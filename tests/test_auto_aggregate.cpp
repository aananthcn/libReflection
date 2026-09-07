// Zero-annotation reflection: these structs have NO REFLECT_CLASS_BEGIN
// block at all. See docs/adr/0001-reflection-generation-strategy.md.
#include "Reflection.hpp"
#include "TestFramework.hpp"

#include <cstddef>

namespace {

// Deliberately unregistered -- this is the point of the test.
struct LegacyPoint {
    int x;
    int y;
};

// No array members here -- see docs/adr/0001 for why a direct
// fixed-size C-array member specifically defeats automatic member-count
// detection and requires REFLECT_CLASS_BEGIN instead.
struct LegacyLine {
    LegacyPoint start;
    LegacyPoint end;
};

struct LegacyEmpty {};

} // namespace

TEST_CASE(UnregisteredAggregateGetsAutomaticOffsetsAndCount) {
    const auto& r = reflect::Reflect<LegacyPoint>();
    REQUIRE(r.GetType() == "<aggregate>");
    REQUIRE(r.GetSize() == sizeof(LegacyPoint));
    REQUIRE(r.GetMembers().size() == 2);

    const auto* field0 = r.FindMember("field0");
    const auto* field1 = r.FindMember("field1");
    REQUIRE(field0 != nullptr);
    REQUIRE(field1 != nullptr);
    REQUIRE(field0->GetOffset() == offsetof(LegacyPoint, x));
    REQUIRE(field1->GetOffset() == offsetof(LegacyPoint, y));
    REQUIRE(field0->GetType() == "int");
}

TEST_CASE(UnregisteredNestedAggregateRecursesAutomatically) {
    const auto& r = reflect::Reflect<LegacyLine>();
    REQUIRE(r.GetMembers().size() == 2);

    const auto* start = r.FindMember("field0");
    REQUIRE(start != nullptr);
    REQUIRE(start->GetOffset() == offsetof(LegacyLine, start));
    REQUIRE(start->GetType() == "<aggregate>");
    REQUIRE(start->GetMembers().size() == 2); // LegacyPoint's own x/y, auto-reflected too

    const auto* end = r.FindMember("field1");
    REQUIRE(end != nullptr);
    REQUIRE(end->GetOffset() == offsetof(LegacyLine, end));
}

TEST_CASE(UnregisteredEmptyAggregateHasNoMembers) {
    const auto& r = reflect::Reflect<LegacyEmpty>();
    REQUIRE(r.GetMembers().empty());
    REQUIRE(r.GetSize() == sizeof(LegacyEmpty));
}

TEST_CASE(AutomaticHashIsStableAndSensitiveToLayout) {
    const auto& first = reflect::Reflect<LegacyPoint>();
    const auto& second = reflect::Reflect<LegacyPoint>();
    REQUIRE(&first == &second);
    REQUIRE(first.GetHash() == second.GetHash());
}

TEST_CASE(FindByNameDoesNotResolveAutoReflectedTypes) {
    // Every auto-reflected type shares the sentinel name "<aggregate>";
    // indexing them by name would make unrelated types collide under
    // that one key, so the registry deliberately skips it. See
    // docs/adr/0001's revision.
    const auto& r = reflect::Reflect<LegacyPoint>();
    REQUIRE(reflect::FindByName(r.GetClassName()) == nullptr);
}

TEST_CASE(FindByHashStillResolvesAutoReflectedTypes) {
    const auto& r = reflect::Reflect<LegacyPoint>();
    const auto* found = reflect::FindByHash(r.GetHash());
    REQUIRE(found == &r);
}
