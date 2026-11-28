# Architecture Memory

This file is the permanent architectural memory of `game-cultural-localization`. Read it with `NAVIGATION.md` before changing code or adding features.

## 1. Layer Model and Dependency Rule

All core Python code lives under `skills/game-cultural-localization/scripts/gcl/` with zero third party dependencies (Python 3.9 standard library only). Outer files under `skills/game-cultural-localization/scripts/*.py` stay in place as thin CLI and backward compatibility facades.

Allowed dependency directions inside `gcl/` (arrows point to what a layer may import).

1. `domain` imports only `gcl.domain` and the standard library
2. `ports` imports `gcl.domain`, `gcl.ports` and the standard library
3. `aspects` imports `gcl.domain`, `gcl.ports`, `gcl.aspects` and the standard library
4. `application` imports `gcl.domain`, `gcl.ports`, `gcl.aspects`, `gcl.application` and the standard library (never `infrastructure`)
5. `infrastructure` imports `gcl.domain`, `gcl.ports`, `gcl.aspects`, `gcl.infrastructure` and the standard library (never `application`)
6. `composition` binds `application` use cases to `infrastructure` implementations for the CLI facades (nothing inside layers 1 to 5 imports `composition`)

## 2. Active Design Patterns

1. **Strategy and Registry** in `gcl.infrastructure.formats`, `gcl.infrastructure.tokens` and `gcl.infrastructure.providers.vendor_registry` (zero format or vendor `if/elif` chains in core code)
2. **Template Method** in `gcl.application.tasks.base_task.KeyedBatchTask` (single batch loop, key retry and split logic shared by all tasks)
3. **Chain of Responsibility** in `gcl.application.jury.escalation_chain` and `gcl.application.gates.lint_chain`
4. **Decorator and Interceptor (AOP)** in `gcl.aspects.call_chain` and `gcl.aspects.task_chain`
5. **Adapter** in `gcl.infrastructure.providers.adapters` and `gcl.infrastructure.persistence.context_views` (typed `RawVendorReply` eliminates tuple mismatch bugs)
6. **Abstract Factory and Builder** in `gcl.infrastructure.providers.factory` and `gcl.application.pipeline.builder`
7. **State** in `gcl.domain.line_state` (immutable line lifecycle transitions with accurate change counts)
8. **Specification** in `gcl.domain.specifications` (composable boolean rules for jury agreement, everyday word cap and lint filtering)
9. **Interface Segregation** in `gcl.ports.context` (`BlindContextView` vs `WriterContextView`)
10. **Observer / Event Bus** in `gcl.aspects.event_bus` (decoupled `budget.jsonl` and stage telemetry)
11. **Repository** in `gcl.infrastructure.persistence` (`AtomicJsonMemoRepository`, `SqliteTMRepository`)
12. **Facade** in top level `scripts/*.py` CLI entrypoints

## 3. Clean Code and Contract Limits

- Every non `__init__.py` module in `scripts/gcl/` declares `__layer__`, `__pattern__` and `__owns__` at module top level
- Maximum `350` physical lines per file inside `scripts/gcl/`
- Maximum `65` lines per function or method inside `scripts/gcl/`
- Maximum `7` parameters per function or method (excluding `self` and `cls`)
- Zero `sys.path.insert` calls inside `scripts/gcl/`
- Zero cyclic imports across `gcl.*`
- Blind jury, blind pick and deliberation modules may never import `WriterContextView` or writer adapters
- `tests/test_architecture_contracts.py` and `scripts/dev/verify_architecture.py` enforce these limits automatically
- Run `python scripts/dev/sync_navigation.py` whenever modules, classes or layers change under `scripts/gcl/`

## 4. House Rules That Stay Unchanged

- Keep zero external dependencies (Python 3.9+ stdlib only)
- Preserve CLI exit codes `0` clean, `1` findings, `2` usage or input error
- Preserve house punctuation style in all Markdown docs (no semicolons, no en or em dashes, no colons inside prose sentences)
- Never log or commit API keys, never modify a game project directory, run tests offline with `python -B -m unittest discover tests`
