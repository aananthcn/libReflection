#include "ClassReflection.hpp"

namespace reflect {

const ClassReflection* ClassReflection::FindMember(std::string_view member_name) const noexcept {
    for (const auto& member : members) {
        if (member.name == member_name) {
            return &member;
        }
    }
    return nullptr;
}

} // namespace reflect
