#include "Reflection.hpp"
#include "TestFramework.hpp"

namespace {

enum class Color { Red, Green, Blue };

enum class Flags : unsigned {
    None = 0,
    A = 1,
    B = 2,
    C = 4,
};

} // namespace

REFLECT_ENUM_BEGIN(Color)
    REFLECT_ENUM_VALUE(Red)
    REFLECT_ENUM_VALUE(Green)
    REFLECT_ENUM_VALUE(Blue)
REFLECT_ENUM_END()

REFLECT_BITFLAG_ENUM_BEGIN(Flags)
    REFLECT_ENUM_VALUE(None)
    REFLECT_ENUM_VALUE(A)
    REFLECT_ENUM_VALUE(B)
    REFLECT_ENUM_VALUE(C)
REFLECT_ENUM_END()

TEST_CASE(PlainEnumValuesRoundTrip) {
    const auto& r = reflect::Reflect<Color>();
    REQUIRE(r.IsEnum());
    REQUIRE(!r.IsBitFlag());
    REQUIRE(r.GetEnumValues().at("Red") == 0);
    REQUIRE(r.GetEnumValues().at("Green") == 1);
    REQUIRE(r.GetEnumValues().at("Blue") == 2);
}

TEST_CASE(BitFlagEnumIsMarkedAndValuesArePowersOfTwo) {
    const auto& r = reflect::Reflect<Flags>();
    REQUIRE(r.IsBitFlag());
    REQUIRE(r.GetEnumValues().at("None") == 0);
    REQUIRE(r.GetEnumValues().at("A") == 1);
    REQUIRE(r.GetEnumValues().at("B") == 2);
    REQUIRE(r.GetEnumValues().at("C") == 4);
}

namespace {

struct Widget {
    Color tint;
    Flags flags;
};

} // namespace

REFLECT_CLASS_BEGIN(Widget)
    REFLECT_MEMBER(tint)
    REFLECT_MEMBER(flags)
REFLECT_CLASS_END()

TEST_CASE(EnumMemberEmbedsFullEnumReflection) {
    const auto& r = reflect::Reflect<Widget>();
    const auto* tint = r.FindMember("tint");
    REQUIRE(tint != nullptr);
    REQUIRE(tint->IsEnum());
    REQUIRE(tint->GetEnumValues().at("Blue") == 2);
}
