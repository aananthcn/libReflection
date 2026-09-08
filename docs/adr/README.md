# Architecture Decision Records — libReflection

ARCHITECTURE.md states the foundational requirements but leaves many
implementation questions open. Before writing any code, this directory
answers each open question as a short ADR. Read them in order — later
ADRs assume earlier decisions.

| # | Decision | Status |
|---|----------|--------|
| [0001](0001-reflection-generation-strategy.md) | How reflection metadata gets generated (automatic aggregate reflection by default, `REFLECT_CLASS_BEGIN` as the escape hatch) | Decided (user); revised |
| [0002](0002-class-hash-algorithm-and-purpose.md) | ClassHash algorithm & purpose (shared-memory IPC layout-drift detection) | Decided (algorithm); purpose confirmed by user |
| [0003](0003-public-api-and-namespace.md) | Namespace & public accessor API | Decided |
| [0004](0004-member-representation-scope.md) | What member kinds are reflectable in v1 | Decided |
| [0005](0005-enum-and-bitflag-reflection.md) | Enum & bit-flag reflection semantics | Decided |
| [0006](0006-build-system-and-qnx-portability.md) | CMake structure & QNX SDP 8.0 portability | Decided |
| [0007](0007-testing-strategy.md) | Test framework, and why `tests/` is scoped exactly to the unit suite | Decided |
| [0008](0008-thread-safety-and-registry.md) | Registry & thread-safety model | Decided |
| [0009](0009-library-versioning.md) | Library versioning (`version.txt` format & CMake wiring) | Decided |
| [0010](0010-header-and-macro-sketch.md) | Concrete header/macro sketch | Decided |
| [0011](0011-tutorials-and-their-purpose.md) | `tutorials/`'s purpose and its standalone-CMake-project structure | Decided; revised twice |
| [0012](0012-generated-reflection-names.md) | Text-scanning generator for real names (aggregates only) | **REVERTED** — wrong founding assumption |
| [0013](0013-dwarf-based-reflection-generation.md) | DWARF-based reflection generation (reaches private members too) | **Implemented and verified** — see `tutorials/01_hello_world/` |
| [0014](0014-aggregate-tie-code-generation.md) | `tools/generate_aggregate_tie.py` → `src/AggregateTie.generated.hpp`, and why the aggregate field cap starts at 64 | Decided |

Only 0001 was a question put to the user (it fixes the shape of the
public annotation API that all downstream code will depend on). The
rest are implementation-detail decisions made unilaterally, each with
its reasoning recorded so it can be revisited if wrong.
