# 0009 — Library Versioning (version.txt)

**Status:** Confirmed by user. Formerly titled
"version.txt vs. ClassHash, Intended Use Case" and split across this
file and [0002](0002-class-hash-algorithm-and-purpose.md) — the
`ClassHash`-purpose half moved to 0002 (now the single ADR for
everything `ClassHash`), leaving this file for `version.txt` alone,
its own, unrelated concept.

## Context

`version.txt` is the library's own release version — unrelated to any
reflected user type or to `ClassHash` (a per-type structural
fingerprint; see [0002](0002-class-hash-algorithm-and-purpose.md) for
what that's for and why it's a wholly separate concept from a release
version number). ARCHITECTURE.md requires a `version.txt` but doesn't
say its exact format or how it's consumed.

**Why it's bumped, in practice:** each bump marks a specific snapshot
of this codebase that was actually handed to a downstream user or team
— e.g. the `0.8.0` bump that shipped to the SerLib team. It's the
project's own record of "what did person/team X actually receive,
and when" — not a semantic-versioning signal about API compatibility.
This is also why [0006](0006-build-system-and-qnx-portability.md)'s
`release/scripts/create-release-source-bundle.sh` names its output
`libReflection-<version>.zip` directly from this file: the version
bump and the snapshot that gets shared are meant to happen together,
one identifying the other after the fact.

## Decision

`version.txt` holds a bare `MAJOR.MINOR.PATCH` string (e.g. `0.1.0` —
no `v` prefix, per user confirmation), the single source of truth for
the library's version. `CMakeLists.txt` reads it via
`file(STRINGS ...)` and requires an exact `^[0-9]+\.[0-9]+\.[0-9]+$`
match (`FATAL_ERROR` otherwise) to feed
`project(Reflection VERSION ...)`; the same string is also embedded
verbatim as `reflect::kVersionString` for display/telemetry. (This
file and its CMake wiring are otherwise a
[0006](0006-build-system-and-qnx-portability.md) build-system
decision — documented here instead, in the one ADR specifically about
versioning, rather than duplicated across both.)

## Consequences

- A malformed `version.txt` fails the CMake configure step immediately
  with a clear message, rather than silently producing a garbage
  version string.
- `reflect::kVersionString` and the CMake project version are always
  in sync, since both are derived from the same `file(STRINGS ...)`
  read of `version.txt` — no separate place to update and forget.
