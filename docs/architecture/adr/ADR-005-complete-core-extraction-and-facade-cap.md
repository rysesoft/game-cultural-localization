# ADR 005. Complete Core Extraction and CLI Facade Cap

## Context

Even after introducing layered packages under `scripts/gcl/`, large procedural modules remained in the outer `scripts/` layer (`build_context_map.py`, `font_glyph_scanner.py`, `build_language_pack.py`, `orchestrator_stub.py`, `eval_critic.py` and `report_changes.py`), leaving cross cutting transport retry, item memoization and subprocess font checks outside the core container.

## Decision

Move every remaining domain aggregate, port adapter, transport/task aspect, Unity project/C# trace scanner, font parser, corpus reader, critic calibrator, change reporter, language pack service and pipeline wiring module inside `scripts/gcl/` and enforce `MAX_FACADE_LINES = 260` on all outer `scripts/*.py` CLI entrypoints (excluding `*.workflow.py`) inside `verify_architecture.py`.

## Consequences

All core logic lives strictly under the six directional `gcl` layers with automated AST enforcement of layer boundaries, zero circular imports, `350` line module limits, `260` line CLI facade limits, Python 3.15 native typing and universal `slots=True` dataclasses.
