#pragma once

// Automatic reflection for plain aggregates (structs with public members,
// no user-declared constructors, no virtual functions, no bases beyond
// what C++20 aggregates allow) that have NOT been given an explicit
// REFLECT_CLASS_BEGIN block. Member offsets, sizes, types, and count are
// derived purely from the type itself via structured bindings -- zero
// annotation, and nothing to keep in sync, since it's recomputed from T
// on every build rather than hand-maintained alongside it.
// See docs/adr/0001-reflection-generation-strategy.md.
//
// What this CANNOT recover, fundamentally (not an implementation gap):
//   - The type's own name and each member's name as source identifiers.
//     Nothing in a compiled C++ program records a data member's name;
//     it's erased at compile time. Auto-reflected types get
//     type/name = "<aggregate>" and members get positional names
//     ("field0", "field1", ...). Use REFLECT_CLASS_BEGIN/REFLECT_MEMBER
//     for real names.
//   - Enum value names -- REFLECT_ENUM_BEGIN is still required for enums
//     (enums are not aggregates, so they never take this path anyway).
// Known unsupported shapes (a clear compile error, never silent wrong
// data):
//   - More than kMaxAggregateFields members -- see the static_assert in
//     CountAggregateFields below.
//   - Any DIRECT fixed-size C-array member (e.g. `int flags[3];`).
//     Detecting member count works by probing how many "universal,
//     convertible-to-anything" placeholder arguments T can be
//     constructed from; a nested *class* member is always filled as one
//     whole placeholder (verified empirically -- both brace-init and
//     C++20 parenthesized aggregate-init agree on the count), but an
//     array member can't be the target of a user-defined conversion at
//     all (arrays aren't a legal conversion-operator return type), so
//     brace-init's elision rules and paren-init's no-elision rules
//     disagree about how many placeholders it consumes. We cross-check
//     both counting methods and refuse (via static_assert, not a wrong
//     answer) whenever they disagree, which happens precisely when a
//     direct array member is present. Give such a type a
//     REFLECT_CLASS_BEGIN block instead -- fixed-size arrays are fully
//     supported there (docs/adr/0004).
//   - Members that are bit-fields: taking a bit-field's address (needed
//     here to compute its offset) is ill-formed, so such a type will
//     fail to compile through this path. Give it a REFLECT_CLASS_BEGIN
//     block instead.

#include "AggregateTie.generated.hpp"
#include "ClassReflection.hpp"
#include "ReflectionFwd.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <tuple>
#include <type_traits>
#include <utility>

namespace reflect::detail {

// A "universal type", implicitly convertible to anything, used only in
// an unevaluated context to probe how many members T can be
// brace-initialized with. Standard technique (also used by e.g.
// Boost.PFR) -- never defined, never actually converted at runtime.
struct UniversalType {
    template <typename T>
    constexpr operator T() const noexcept;
};

template <typename T, std::size_t... Is>
constexpr auto IsBraceConstructible(std::index_sequence<Is...>)
    -> decltype(void(T{(static_cast<void>(Is), UniversalType{})...}), std::true_type{});

template <typename T, std::size_t...>
constexpr std::false_type IsBraceConstructible(...);

template <typename T, std::size_t N>
inline constexpr bool kIsBraceConstructibleWithN =
    decltype(IsBraceConstructible<T>(std::make_index_sequence<N>{}))::value;

// C++20 parenthesized aggregate init (P0960) performs no brace elision,
// so it counts members completely differently from brace-init whenever
// a direct array member is involved -- see the file-level comment above
// for why comparing the two is exactly the signal we need.
template <typename T, std::size_t... Is>
constexpr auto IsParenConstructible(std::index_sequence<Is...>)
    -> decltype(void(T((static_cast<void>(Is), UniversalType{})...)), std::true_type{});

template <typename T, std::size_t...>
constexpr std::false_type IsParenConstructible(...);

template <typename T, std::size_t N>
inline constexpr bool kIsParenConstructibleWithN =
    decltype(IsParenConstructible<T>(std::make_index_sequence<N>{}))::value;

template <typename T, std::size_t N>
struct BraceOk { static constexpr bool value = kIsBraceConstructibleWithN<T, N>; };

template <typename T, std::size_t N>
struct ParenOk { static constexpr bool value = kIsParenConstructibleWithN<T, N>; };

inline constexpr std::size_t kMaxAggregateFields = 64;

// Binary search for the largest N in [Lo, Hi] for which Pred<T, N>::value
// holds. Aggregate initialization accepts *up to* the real member count
// (remaining members are value-initialized) and fails above it ("too
// many initializers"), so that largest N is the member count Pred sees.
template <template <typename, std::size_t> class Pred, typename T, std::size_t Lo, std::size_t Hi>
struct FieldCountSearch {
    static constexpr std::size_t kMid = Lo + (Hi - Lo + 1) / 2;
    static constexpr std::size_t value = Pred<T, kMid>::value
        ? FieldCountSearch<Pred, T, kMid, Hi>::value
        : FieldCountSearch<Pred, T, Lo, kMid - 1>::value;
};

template <template <typename, std::size_t> class Pred, typename T, std::size_t N>
struct FieldCountSearch<Pred, T, N, N> {
    static constexpr std::size_t value = N;
};

template <typename T>
constexpr std::size_t CountAggregateFields() {
    // A struct with zero data members is a separate edge case: T{u} for
    // a single universal-conversion argument u can be resolved as
    // copy-initialization (u converts to T "as a whole") rather than
    // "too many initializers for 0 members", so brace/paren counting
    // would spuriously disagree here even though there's no array
    // involved. std::is_empty_v is the standard, purpose-built trait
    // for exactly this shape, so short-circuit through it first.
    if constexpr (std::is_empty_v<T>) {
        return 0;
    } else {
        static_assert(
            !kIsBraceConstructibleWithN<T, kMaxAggregateFields + 1>,
            "aggregate has more than kMaxAggregateFields members -- give it an "
            "explicit REFLECT_CLASS_BEGIN block, or raise kMaxAggregateFields "
            "in AggregateReflection.hpp and regenerate AggregateTie.generated.hpp "
            "via tools/generate_aggregate_tie.py");

        constexpr std::size_t kBraceCount = FieldCountSearch<BraceOk, T, 0, kMaxAggregateFields>::value;
        constexpr std::size_t kParenCount = FieldCountSearch<ParenOk, T, 0, kMaxAggregateFields>::value;
        static_assert(
            kBraceCount == kParenCount,
            "T's automatic member count is ambiguous -- this happens for "
            "aggregates with a direct fixed-size C-array member. Give it an "
            "explicit REFLECT_CLASS_BEGIN block instead of relying on "
            "automatic aggregate reflection (see docs/adr/0001)");
        return kBraceCount;
    }
}

template <typename T>
ClassReflection DescribeAggregate() {
    ClassReflection r;
    r.name = r.type = kAutoAggregateTypeName;
    r.size = static_cast<std::uint32_t>(sizeof(T));
    r.count = 1;

    T probe{};
    constexpr std::size_t kFieldCount = CountAggregateFields<T>();
    auto fields = TieMembers(probe, std::integral_constant<std::size_t, kFieldCount>{});

    [&]<std::size_t... Is>(std::index_sequence<Is...>) {
        (
            [&] {
                using MemberT = std::remove_reference_t<decltype(std::get<Is>(fields))>;
                ClassReflection m = reflect::Reflect<MemberT>();
                m.name = "field" + std::to_string(Is);
                m.offset = static_cast<std::uint32_t>(
                    reinterpret_cast<const unsigned char*>(&std::get<Is>(fields)) -
                    reinterpret_cast<const unsigned char*>(&probe));
                r.members.push_back(std::move(m));
            }(),
            ...
        );
    }(std::make_index_sequence<kFieldCount>{});

    return r;
}

} // namespace reflect::detail
