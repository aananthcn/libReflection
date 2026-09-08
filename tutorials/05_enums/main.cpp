// Enums, end to end. Enums are never aggregates, so automatic
// reflection has no path to them at all -- and docs/adr/0013's
// DWARF-based generator is about class members, not enum value names,
// so it doesn't cover them either. That leaves two options, and this
// tutorial shows both:
//
//   Part A -- REFLECT_ENUM_BEGIN: the library's supported path. One
//             hand-written line per value, registered into the same
//             reflect::Reflect<T>() machinery as every other type.
//
//   Part B -- a zero-annotation C++20 trick: recover an enumerator's
//             name straight from __PRETTY_FUNCTION__, no macro and no
//             table. Not part of libReflection -- just plain C++ --
//             but it's the natural thing to reach for when all you
//             need is enum <-> string and you don't want the upkeep
//             of a REFLECT_ENUM_VALUE list.
#include <Reflection.hpp>

#include <cstdint>
#include <iostream>
#include <string_view>
#include <type_traits>
#include <utility>


// =====================================================================
// Part A: REFLECT_ENUM_BEGIN -- the library's supported enum path.
// =====================================================================

enum class LogLevel { Debug, Info, Warning, Error };
REFLECT_ENUM_BEGIN(LogLevel)
    REFLECT_ENUM_VALUE(Debug)
    REFLECT_ENUM_VALUE(Info)
    REFLECT_ENUM_VALUE(Warning)
    REFLECT_ENUM_VALUE(Error)
REFLECT_ENUM_END()

static void macro_enum_reflection() {
    const auto& level = reflect::Reflect<LogLevel>();
    std::cout << "Part A -- reflect::Reflect<LogLevel>():\n";
    std::cout << "  '" << level.GetClassName() << "' has "
              << level.GetEnumValues().size() << " named values\n";
    for (const auto& [name, value] : level.GetEnumValues()) {
        std::cout << "    " << name << " = " << value << "\n";
    }
    std::cout << "  lookup by name: Warning = "
              << level.GetEnumValues().at("Warning") << "\n";

    // Macro-registered types also resolve by name, unlike auto-reflected
    // ones (see tutorials/01_hello_world).
    std::cout << "  FindByName(\"LogLevel\") found it: " << std::boolalpha
              << (reflect::FindByName("LogLevel") == &level) << "\n";
}


// =====================================================================
// Part B: zero-annotation enum <-> string in plain C++20.
// =====================================================================

// A plain (unscoped) enum leaks its enumerators into the surrounding
// scope and implicitly converts to an integer, so `std::cout << Stop`
// just works -- and so does `int n = Go;`, often by accident. The
// underlying type is unspecified here.
enum Signal { Stop, Caution, Go };

// The modern alternative is a *scoped* enum (`enum class`) with a
// fixed underlying type: names must be qualified (`Direction::North`),
// there is no implicit conversion to int, and the storage size is
// pinned to one byte. C++20 then adds `using enum`, which pulls the
// enumerators into one scope unqualified without losing that safety.
enum class Direction : std::uint8_t { North, East, South, West };

// Underlying integer of a scoped enumerator. (C++23 would let us drop
// this helper for std::to_underlying.)
template <typename E>
constexpr auto to_underlying(E e) noexcept {
    return static_cast<std::underlying_type_t<E>>(e);
}

// Compile-time enumerator -> string. A function template parameterised
// on the enumerator *value* bakes that value's source spelling into
// __PRETTY_FUNCTION__ (a GCC/Clang builtin; std::source_location::
// function_name() is the C++20 standard-blessed equivalent), which we
// slice back out at compile time. No macro or table on the enum
// itself; works for both scoped and unscoped enums. A value that
// names no enumerator (a cast that missed) comes back as "<unknown>".
template <auto Value>
constexpr std::string_view enum_str() {
    // GCC:   "...enum_str() [with auto Value = Direction::West; std::string_view = ...]"
    // Clang: "...enum_str() [Value = Direction::West]"
    std::string_view p = __PRETTY_FUNCTION__;
    auto start = p.find("Value = ") + 8;           // just past "Value = "
    auto end = p.find_first_of(";]", start);       // stop at GCC's ";" or the closing "]"
    p = p.substr(start, end - start);
    if (p.empty() || p.front() == '(' || p.front() == '-' ||
        (p.front() >= '0' && p.front() <= '9')) {
        return "<unknown>";                        // compiler rendered "(Direction)7" etc.
    }
    if (auto sep = p.rfind("::"); sep != std::string_view::npos) {
        p.remove_prefix(sep + 2);                  // strip a "Direction::" qualifier
    }
    return p;
}

// Runtime value -> string: fold over the candidate underlying values
// [0, N) and return the first whose value matches. This is the piece
// you would actually call at runtime, e.g. when logging an enum.
template <typename E, std::size_t... I>
constexpr std::string_view enum_str_scan(E value, std::index_sequence<I...>) {
    std::string_view name = "<unknown>";
    (void)(((static_cast<E>(I) == value ? (name = enum_str<static_cast<E>(I)>(), true)
                                        : false)) || ...);
    return name;
}
template <typename E>
constexpr std::string_view name_of(E value) {
    return enum_str_scan(value, std::make_index_sequence<8>{});
}

static void zero_annotation_enum_strings() {
    std::cout << "\nPart B -- enum_str / name_of, no annotation:\n";

    std::cout << "  classic unscoped enum:\n";
    for (Signal s : {Stop, Caution, Go}) {
        std::cout << "    " << name_of(s) << " = " << s << "\n";
    }

    std::cout << "  C++20 scoped enum (fixed uint8_t storage, "
              << sizeof(Direction) << " byte):\n";
    {
        using enum Direction;  // C++20: enumerators visible unqualified, in this block only
        for (Direction d : {North, East, South, West}) {
            std::cout << "    " << name_of(d) << " = " << +to_underlying(d) << "\n";
        }
    }

    // The names are available at compile time, too:
    static_assert(enum_str<Direction::West>() == "West");
    static_assert(name_of(Signal::Caution) == "Caution");

    // A value that names no enumerator round-trips safely:
    std::cout << "    name_of(Direction{7}) = " << name_of(Direction{7}) << "\n";
}


int main() {
    macro_enum_reflection();
    zero_annotation_enum_strings();
    return 0;
}
