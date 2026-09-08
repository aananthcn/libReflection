#include "Reflection.hpp"
#include "TestFramework.hpp"

#include <cstddef>

namespace {

struct Vec3 {
    float x;
    float y;
    float z;
};

} // namespace

REFLECT_CLASS_BEGIN(Vec3)
    REFLECT_MEMBER(x)
    REFLECT_MEMBER(y)
    REFLECT_MEMBER(z)
REFLECT_CLASS_END()

TEST_CASE(BasicMemberOffsetsAndCount) {
    const auto& r = reflect::Reflect<Vec3>();
    REQUIRE(r.GetName() == "Vec3");
    REQUIRE(r.GetMembers().size() == 3);
    REQUIRE(r.GetSize() == sizeof(Vec3));

    const auto* y = r.FindMember("y");
    REQUIRE(y != nullptr);
    REQUIRE(y->GetOffset() == offsetof(Vec3, y));
    REQUIRE(y->GetType() == "float");

    REQUIRE(r.FindMember("does_not_exist") == nullptr);
}

namespace {

struct Transform {
    Vec3 position;
    Vec3 scale;
    int flags[4];
};

} // namespace

REFLECT_CLASS_BEGIN(Transform)
    REFLECT_MEMBER(position)
    REFLECT_MEMBER(scale)
    REFLECT_MEMBER(flags)
REFLECT_CLASS_END()

TEST_CASE(NestedStructMemberEmbedsFullReflection) {
    const auto& r = reflect::Reflect<Transform>();
    const auto* position = r.FindMember("position");
    REQUIRE(position != nullptr);
    REQUIRE(position->GetType() == "Vec3");
    REQUIRE(position->GetOffset() == offsetof(Transform, position));
    REQUIRE(position->GetMembers().size() == 3);
    REQUIRE(position->FindMember("z") != nullptr);
}

TEST_CASE(FixedSizeArrayMemberReportsCount) {
    const auto& r = reflect::Reflect<Transform>();
    const auto* flags = r.FindMember("flags");
    REQUIRE(flags != nullptr);
    REQUIRE(flags->IsArray());
    REQUIRE(flags->GetCount() == 4);
    REQUIRE(flags->GetSize() == sizeof(int) * 4);
}

namespace {

struct WithPointer {
    int value;
    WithPointer* next;
};

} // namespace

REFLECT_CLASS_BEGIN(WithPointer)
    REFLECT_MEMBER(value)
    REFLECT_MEMBER(next)
REFLECT_CLASS_END()

TEST_CASE(PointerMemberIsOpaqueLeafNotRecursed) {
    const auto& r = reflect::Reflect<WithPointer>();
    const auto* next = r.FindMember("next");
    REQUIRE(next != nullptr);
    REQUIRE(next->GetMembers().empty());
    REQUIRE(next->GetSize() == sizeof(WithPointer*));
}
