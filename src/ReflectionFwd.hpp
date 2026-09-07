#pragma once

#include "ClassReflection.hpp"

// Forward declaration only, so headers that need to call Reflect<T>()
// from inside another template's body (see AggregateReflection.hpp)
// don't have to wait for TypeInfo.hpp's full definition -- the actual
// call is dependent on a template parameter, so the compiler only needs
// this declaration visible at the point of definition; the real
// definition (in TypeInfo.hpp) just needs to be visible by the time
// user code actually instantiates it.
namespace reflect {

template <typename T>
const ClassReflection& Reflect();

} // namespace reflect
