# GCL Core Architecture Rules

Read `../../../../docs/architecture/ARCHITECTURE_MEMORY.md` and `../../../../docs/architecture/NAVIGATION.md` before modifying any file inside `scripts/gcl/`.

## Mandatory Constraints Inside This Folder

- Declare `__layer__`, `__pattern__` and `__owns__` at the top of every non `__init__.py` module.
- Follow downward only imports. `domain` imports only `domain`. `ports` imports `domain` and `ports`. `aspects` imports `domain`, `ports` and `aspects`. `application` never imports `infrastructure`. `infrastructure` never imports `application`.
- Never import top level CLI scripts (such as `jury`, `orchestrator_stub`, `l10n_common`) from inside `gcl/`.
- Never call `sys.path.insert` inside `gcl/`.
- Never import `WriterContextView` or writer adapters inside `gcl/application/jury/` or blind picker tasks.
- Never hardcode vendor names in `gcl/infrastructure/providers/factory.py` (register vendors in `vendor_registry.py`).
- Keep every module at or below `350` lines, every function at or below `65` lines and every signature at or below `7` parameters.
- Prefer frozen dataclasses over mutable `Dict[str, Any]` bags for internal workflows.
- After editing any file here, run `python skills/game-cultural-localization/scripts/dev/sync_navigation.py` and `python -B -m unittest discover tests`.
