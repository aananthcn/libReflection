#include "TestFramework.hpp"

int main() {
    for (const auto& test : reflect_test::Registry()) {
        std::cout << "[ RUN      ] " << test.name << "\n";
        test.fn();
    }

    const int failures = reflect_test::FailureCount();
    if (failures == 0) {
        std::cout << "All " << reflect_test::Registry().size() << " test case(s) passed.\n";
        return 0;
    }
    std::cerr << failures << " assertion(s) failed.\n";
    return 1;
}
