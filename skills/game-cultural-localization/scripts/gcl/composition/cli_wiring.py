"""Composition root for model CLI flags, budget paths and Router instantiation."""

from pathlib import Path
from collections.abc import Sequence
from typing import Any

from gcl.application.tasks.prompts import BATCH_WORKERS
from gcl.infrastructure.paths import SCRIPTS_DIR
from gcl.infrastructure.providers import FakeScenario, Router, load_providers_config

__layer__ = "composition"
__pattern__ = "Composition Root"
__owns__ = "CLI model router construction, batch worker scaling and budget path defaults"


def add_model_args(ap: Any) -> None:
    """Attach standard model config, dry run, budget log, --batch and --flex CLI arguments."""
    ap.add_argument("--providers-config", default=None, help="providers.config.json (default: the bundled one)")
    ap.add_argument("--dry-run", action="store_true", help="Use the offline fake provider (no API key, no network)")
    ap.add_argument("--fake-scenario", help="Fake provider scenario JSON (with --dry-run)")
    ap.add_argument("--budget-log", default=None, help="budget.jsonl that receives one line per model call")
    ap.add_argument(
        "--batch", action="store_true",
        help="Send the calls of Anthropic and Google models through their batch APIs at half the price. A reply comes "
             "when its job ends, usually within an hour, at most a day. DeepSeek stays real time",
    )
    ap.add_argument(
        "--flex", action="store_true",
        help="Use the Google Gemini flex service tier at half the standard token price",
    )


def default_budget_path(out: Path) -> Path:
    """Return budget.jsonl sibling path or langpack/.cache location."""
    langpack = (SCRIPTS_DIR.parent / "langpack").resolve()
    resolved = Path(out).resolve()
    try:
        resolved.relative_to(langpack)
        return langpack / ".cache" / "budget.jsonl"
    except ValueError:
        return resolved.parent / "budget.jsonl"


def make_router(args: Any, roles: Sequence[str], budget_default: Path | None = None) -> Router:
    """Build configured Router, enforce role API keys and scale workers in batch mode."""
    cfg = load_providers_config(Path(args.providers_config) if getattr(args, "providers_config", None) else None)
    budget = Path(args.budget_log) if getattr(args, "budget_log", None) else budget_default
    batch = bool(getattr(args, "batch", False))
    flex = bool(getattr(args, "flex", False))
    scenario = FakeScenario.load(Path(args.fake_scenario)) if getattr(args, "fake_scenario", None) else None
    router = Router(cfg, dry_run=bool(getattr(args, "dry_run", False)), scenario=scenario, budget_log=budget, batch=batch, flex=flex)
    router.require(roles)
    if batch and hasattr(args, "workers"):
        args.workers = max(int(args.workers or 1), BATCH_WORKERS)
    return router
