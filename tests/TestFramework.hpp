#pragma once

// Minimal in-repo test harness -- see docs/adr/0007-testing-strategy.md
// for why this exists instead of a vendored framework.

#include <functional>
#include <iostream>
#include <string>
#include <vector>

namespace reflect_test {

struct TestCase {
    std::string name;
    std::function<void()> fn;
};

inline std::vector<TestCase>& Registry() {
    static std::vector<TestCase> tests;
    return tests;
}

struct Registrar {
    Registrar(std::string name, std::function<void()> fn) {
        Registry().push_back({std::move(name), std::move(fn)});
    }
};

inline int& FailureCount() {
    static int failures = 0;
    return failures;
}

} // namespace reflect_test

#define TEST_CASE(Name)                                                      \
    static void Name();                                                      \
    static ::reflect_test::Registrar registrar_##Name(#Name, Name);          \
    static void Name()

#define REQUIRE(expr)                                                        \
    do {                                                                     \
        if (!(expr)) {                                                       \
            std::cerr << "REQUIRE failed: " #expr " at " << __FILE__ << ":"  \
                       << __LINE__ << "\n";                                  \
            ++::reflect_test::FailureCount();                                \
        }                                                                    \
    } while (0)
