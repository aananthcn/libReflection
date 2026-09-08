#include "ReflectionRegistry.hpp"

#include <cstddef>
#include <mutex>
#include <string>
#include <unordered_map>

namespace reflect {
namespace {

struct ClassHashHasher {
    std::size_t operator()(const ClassHash& hash) const noexcept {
        return static_cast<std::size_t>(
            hash.words[0] ^ hash.words[1] ^ hash.words[2] ^ hash.words[3]);
    }
};

// Function-local static: thread-safe, exactly-once initialization
// (C++11 "magic statics"), no static-init-order concerns. See
// docs/adr/0008-thread-safety-and-registry.md.
struct Registry {
    std::mutex mutex;
    std::unordered_map<ClassHash, const ClassReflection*, ClassHashHasher> by_hash;
    std::unordered_map<std::string, const ClassReflection*> by_name;
};

Registry& GetRegistry() {
    static Registry registry;
    return registry;
}

} // namespace

namespace detail {

void RegisterInGlobalRegistry(const ClassReflection& reflection) {
    Registry& registry = GetRegistry();
    std::lock_guard<std::mutex> lock(registry.mutex);
    // emplace() is a no-op if the key is already present -- harmless,
    // since re-registering the same type yields the same content.
    registry.by_hash.emplace(reflection.GetHash(), &reflection);
    // Automatically-reflected aggregates (docs/adr/0001's revision) all
    // share the sentinel name kAutoAggregateTypeName -- indexing them
    // by name would make every such type silently collide under that
    // one key. FindByName only ever resolves macro-registered types;
    // FindByHash still works for both.
    if (reflection.GetName() != kAutoAggregateTypeName) {
        registry.by_name.emplace(reflection.GetName(), &reflection);
    }
}

} // namespace detail

const ClassReflection* FindByHash(const ClassHash& hash) {
    Registry& registry = GetRegistry();
    std::lock_guard<std::mutex> lock(registry.mutex);
    auto it = registry.by_hash.find(hash);
    return it == registry.by_hash.end() ? nullptr : it->second;
}

const ClassReflection* FindByName(std::string_view type_name) {
    Registry& registry = GetRegistry();
    std::lock_guard<std::mutex> lock(registry.mutex);
    auto it = registry.by_name.find(std::string(type_name));
    return it == registry.by_name.end() ? nullptr : it->second;
}

} // namespace reflect
