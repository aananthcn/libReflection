#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace reflect {

/**
 * @brief Sentinel type/class name given to automatically-reflected
 * aggregates (docs/adr/0001-reflection-generation-strategy.md's
 * revision) that have no REFLECT_CLASS_BEGIN block, since nothing in a
 * compiled program records a struct's source name without one. Shared
 * between AggregateReflection.hpp (which sets it) and
 * ReflectionRegistry.cpp (which must NOT insert it into the by-name
 * registry -- every auto-reflected type would otherwise collide under
 * this one shared key).
 */
inline constexpr const char* kAutoAggregateTypeName = "<aggregate>";

/**
 * @brief 256-bit structural fingerprint of a reflected type's layout.
 *
 * Used to detect layout drift between independently-built processes that
 * share a struct definition over shared-memory IPC (see
 * docs/adr/0002-class-hash-algorithm.md and
 * docs/adr/0009-versioning-and-hash-purpose.md). Not a cryptographic hash.
 */
class ClassHash {
public:
    std::uint64_t words[4];

    bool operator==(const ClassHash& other) const noexcept {
        return words[0] == other.words[0] && words[1] == other.words[1] &&
               words[2] == other.words[2] && words[3] == other.words[3];
    }
    bool operator!=(const ClassHash& other) const noexcept { return !(*this == other); }
};

class ClassReflection {
public:
    using MemberList = std::vector<ClassReflection>;
    using EnumValues = std::unordered_map<std::string, std::int64_t>;

    /**
     * @brief Construct a new Class Reflection object
     */
    ClassReflection()
        : name("")
        , type("")
        , offset(0)
        , size(0)
        , count(1)
        , members(MemberList())
        , hash({0, 0, 0, 0})
        , enum_name("")
        , enum_values(EnumValues())
        , bit_flag(false)
    {
    }

public:
    // Accessors: the sanctioned read path for callers, see
    // docs/adr/0003-public-api-and-namespace.md. Fields stay public per
    // ARCHITECTURE.md, but going through these lets the internal
    // representation evolve without breaking callers.
    const std::string& GetClassName() const noexcept { return name; }
    const std::string& GetType() const noexcept { return type; }
    std::uint32_t GetOffset() const noexcept { return offset; }
    std::uint32_t GetSize() const noexcept { return size; }
    std::uint32_t GetCount() const noexcept { return count; }
    const MemberList& GetMembers() const noexcept { return members; }
    const ClassHash& GetHash() const noexcept { return hash; }
    const std::string& GetEnumName() const noexcept { return enum_name; }
    const EnumValues& GetEnumValues() const noexcept { return enum_values; }
    bool IsBitFlag() const noexcept { return bit_flag; }
    bool IsEnum() const noexcept { return !enum_name.empty(); }
    bool IsArray() const noexcept { return count > 1; }

    /**
     * @brief Look up a direct (non-recursive) member by name.
     * @return the member, or nullptr if no direct member has that name.
     */
    const ClassReflection* FindMember(std::string_view member_name) const noexcept;

public:
    std::string name;
    std::string type;
    std::uint32_t offset;
    std::uint32_t size;
    std::uint32_t count;
    MemberList members;
    ClassHash hash;
    std::string enum_name;
    EnumValues enum_values;
    bool bit_flag;
};

} // namespace reflect
