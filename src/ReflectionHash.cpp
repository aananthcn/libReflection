#include "ReflectionHash.hpp"

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace reflect::detail {
namespace {

std::uint64_t Fnv1a64(std::string_view data, std::uint64_t seed) {
    std::uint64_t hash = seed;
    constexpr std::uint64_t kFnvPrime = 1099511628211ull;
    for (unsigned char byte : data) {
        hash ^= static_cast<std::uint64_t>(byte);
        hash *= kFnvPrime;
    }
    return hash;
}

void AppendField(std::string& out, std::string_view label, std::string_view value) {
    out += label;
    out += '=';
    out += value;
    out += ';';
}

// Builds a canonical string describing r's own shape plus, for each member,
// the member's name/offset and its own already-computed hash (rather than
// recursing into the member's full member list) -- see docs/adr/0002.
std::string CanonicalDescription(const ClassReflection& r) {
    std::string out;
    AppendField(out, "name", r.GetName());
    AppendField(out, "type", r.GetType());
    AppendField(out, "size", std::to_string(r.GetSize()));
    AppendField(out, "count", std::to_string(r.GetCount()));

    if (r.IsEnum()) {
        AppendField(out, "enum", r.GetEnumName());
        AppendField(out, "bitflag", r.IsBitFlag() ? "1" : "0");
        std::vector<std::pair<std::string, std::int64_t>> values(
            r.GetEnumValues().begin(), r.GetEnumValues().end());
        std::sort(values.begin(), values.end());
        for (const auto& [key, value] : values) {
            AppendField(out, "v:" + key, std::to_string(value));
        }
    }

    for (const auto& member : r.GetMembers()) {
        AppendField(out, "member", member.GetName());
        AppendField(out, "member_offset", std::to_string(member.GetOffset()));
        for (auto word : member.GetHash().words) {
            AppendField(out, "member_hash", std::to_string(word));
        }
    }
    return out;
}

} // namespace

ClassHash ComputeHash(const ClassReflection& r) {
    const std::string canonical = CanonicalDescription(r);
    static constexpr std::uint64_t kSeeds[4] = {
        0xcbf29ce484222325ull,
        0x84222325cbf29ce4ull,
        0x9e3779b97f4a7c15ull,
        0x2545f4914f6cdd1dull,
    };
    ClassHash hash{};
    for (int i = 0; i < 4; ++i) {
        hash.words[i] = Fnv1a64(canonical, kSeeds[i]);
    }
    return hash;
}

void ValidateEnum(const ClassReflection& r) {
    if (!r.IsBitFlag()) {
        return;
    }
    for (const auto& [name, value] : r.GetEnumValues()) {
        (void)name;
        const auto unsigned_value = static_cast<std::uint64_t>(value);
        const bool is_zero_or_power_of_two = (unsigned_value & (unsigned_value - 1)) == 0;
        assert(is_zero_or_power_of_two && "bit-flag enum value must be 0 or a power of two");
        (void)is_zero_or_power_of_two;
    }
}

} // namespace reflect::detail
