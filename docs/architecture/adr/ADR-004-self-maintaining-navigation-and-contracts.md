# ADR 004. Self Maintaining Navigation and AST Fitness Contracts

## Context

Manual architecture notes drift whenever developers or AI agents rename files, add classes or take shortcuts across layer boundaries.

## Decision

Enforce a four lock governance loop. Module headers (`__layer__`, `__pattern__`, `__owns__`) feed an AST generator `scripts/dev/sync_navigation.py` that builds `docs/architecture/NAVIGATION.md`. An AST contract checker `scripts/dev/verify_architecture.py` runs inside `tests/test_architecture_contracts.py` and CI. Antigravity lifecycle hooks in `.agents/hooks.json` inject architecture memory at `SessionStart` and verify contracts plus navigation sync on `Stop`.

## Consequences

Any stale navigation index or SOLID/layer violation fails CI and blocks agent stop termination until reconciled.
