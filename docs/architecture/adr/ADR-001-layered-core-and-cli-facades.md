# ADR 001. Layered Core Package and CLI Facades

## Context

`l10n_common.py` grew above 1,100 lines and `orchestrator_stub.py` mixed CLI flags, prompt building, pipeline orchestration and reporting in 659 lines. Moving scripts out of `scripts/*.py` directly would break `SKILL.md`, `CLI_REFERENCE.md` and external automation.

## Decision

Introduce a 5 layer package `skills/game-cultural-localization/scripts/gcl/` (`domain`, `ports`, `aspects`, `application`, `infrastructure`, plus `composition`) and convert top level `scripts/*.py` entrypoints into thin facades that parse CLI flags, wire dependencies through `composition` and re-export public symbols needed by existing callers and tests.

## Consequences

1. All 20 existing CLI script paths, `--help`, `--version` and exit codes remain 100 percent backward compatible.
2. Core business rules depend only on abstractions in `gcl.ports`, never on concrete vendor SDKs, SQLite or file parsers.
