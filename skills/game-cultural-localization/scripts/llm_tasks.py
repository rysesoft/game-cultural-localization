"""Facade delegating batched LLM tasks and model routing helpers to gcl layers."""

import sys
from pathlib import Path
from collections.abc import Callable, Sequence
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcl.application.tasks import (  # noqa: E402
    BATCH_CHARS, BATCH_ROWS, BATCH_WORKERS, DEFAULT_SYSTEM, EVERYDAY_CAP, EVERYDAY_CHECK, EVERYDAY_MIN_JURORS,
    INSTRUCTIONS, ISSUE_TYPES, KEYED_ATTEMPTS, REGISTERS, SPLIT_DEPTH, backtranslate_rows as _backtranslate_rows,
    chunked, chunked_budget, everyday_check, everyday_rule, normalize_vote, ordered_unique,
    pass2_candidates as _pass2_candidates, pairwise_choices as _pairwise_choices, pick_candidates as _pick_candidates,
    primes, revote as _revote, revote_many as _revote_many, score_entries as _score_entries, system_for,
    translate_rows as _translate_rows, word_count,
)
from gcl.application.tasks.base_task import KeyedCallSpec, call_keyed  # noqa: E402
from gcl.application.tasks.prompts import _text_len  # noqa: E402
from gcl.aspects.task_chain import run_batches_with_aspects  # noqa: E402
from gcl.composition.cli_wiring import add_model_args, default_budget_path, make_router  # noqa: E402
from gcl.infrastructure.persistence.memo_store import BatchMemo  # noqa: E402

def run_batches[T](
    batches: Sequence[T],
    fn: Callable[[T], dict[str, Any]],
    workers: int = 1,
    memo: BatchMemo | None = None,
    tag: Any = None,
    prime: bool = True,
) -> dict[str, Any]:
    """Run batch callable across threads through MemoizationTaskAspect and cache priming."""
    return run_batches_with_aspects(batches, fn, workers=workers, memo=memo, tag=tag, prime=prime)


def _call_keyed(
    provider: Any,
    system: str,
    task: str,
    base_payload: dict[str, Any],
    items: list[dict[str, Any]],
    list_field: str,
    reply_field: str,
    id_field: str,
    accept: Callable[[dict[str, Any]], bool],
    max_tokens: int,
    split_depth: int = SPLIT_DEPTH,
) -> dict[str, dict[str, Any]]:
    """Backward compatible wrapper delegating to gcl.application.tasks.base_task.call_keyed."""
    spec = KeyedCallSpec(task, list_field, reply_field, id_field, accept, max_tokens, split_depth)
    return call_keyed(provider, system, base_payload, items, spec)


def translate_rows(
    provider: Any, rows: Sequence[dict[str, Any]], locale: str, *, task: str = "pass1",
    system: str | None = None, batch_size: int | None = None, max_tokens: int = 4096,
    extra: dict[str, Any] | None = None, workers: int = 1, memo: BatchMemo | None = None,
    max_chars: int | None = None, item_memo: BatchMemo | None = None, salvage_truncated: bool = False,
) -> dict[str, str]:
    """Translate source rows with task 'pass1' or 'literal'; return key -> target."""
    return _translate_rows(
        provider, rows, locale, task=task, system=system, batch_size=batch_size,
        max_tokens=max_tokens, extra=extra, workers=workers, memo=memo, max_chars=max_chars,
        item_memo=item_memo, salvage_truncated=salvage_truncated,
    )


def backtranslate_rows(
    provider: Any, rows: Sequence[dict[str, Any]], locale: str, *, system: str | None = None,
    batch_size: int | None = None, max_tokens: int = 4096, workers: int = 1,
    memo: BatchMemo | None = None, max_chars: int | None = None,
    item_memo: BatchMemo | None = None, salvage_truncated: bool = False,
) -> dict[str, str]:
    """Back translate rows into English; return key -> back translation."""
    return _backtranslate_rows(
        provider, rows, locale, system=system, batch_size=batch_size,
        max_tokens=max_tokens, workers=workers, memo=memo, max_chars=max_chars,
        item_memo=item_memo, salvage_truncated=salvage_truncated,
    )


def score_entries(
    provider: Any, entries: Sequence[dict[str, Any]], locale: str, *, tier: str = "J1",
    system: str | None = None, batch_size: int | None = None, max_tokens: int = 4096,
    extra: dict[str, Any] | None = None, workers: int = 1, memo: BatchMemo | None = None,
    max_chars: int | None = None, item_memo: BatchMemo | None = None, salvage_truncated: bool = False,
) -> dict[str, dict[str, Any]]:
    """Ask one jury member to score target only entries; return key -> normalized vote."""
    return _score_entries(
        provider, entries, locale, tier=tier, system=system, batch_size=batch_size,
        max_tokens=max_tokens, extra=extra, workers=workers, memo=memo, max_chars=max_chars,
        item_memo=item_memo, salvage_truncated=salvage_truncated,
    )


def pairwise_choices(
    provider: Any, pairs: Sequence[dict[str, Any]], locale: str, *, system: str | None = None,
    batch_size: int | None = None, max_tokens: int = 2048, workers: int = 1,
    memo: BatchMemo | None = None, max_chars: int | None = None,
    item_memo: BatchMemo | None = None, salvage_truncated: bool = False,
) -> dict[str, str]:
    """Ask one member which side of each pair is more natural; return id -> 'a' | 'b'."""
    return _pairwise_choices(
        provider, pairs, locale, system=system, batch_size=batch_size,
        max_tokens=max_tokens, workers=workers, memo=memo, max_chars=max_chars,
        item_memo=item_memo, salvage_truncated=salvage_truncated,
    )


def revote(provider: Any, payload: dict[str, Any], locale: str, *, system: str | None = None, max_tokens: int = 1024) -> dict[str, Any]:
    """Run one deliberation re-vote and return a normalized vote."""
    return _revote(provider, payload, locale, system=system, max_tokens=max_tokens)


def revote_many(
    provider: Any, payloads: Sequence[dict[str, Any]], locale: str, *, system: str | None = None,
    batch_size: int | None = None, max_chars: int | None = None, max_tokens: int = 4096,
    workers: int = 1, memo: BatchMemo | None = None, item_memo: BatchMemo | None = None,
    salvage_truncated: bool = False,
) -> dict[str, dict[str, Any]]:
    """Run deliberation re-votes for many disputed lines at once."""
    return _revote_many(
        provider, payloads, locale, system=system, batch_size=batch_size,
        max_chars=max_chars, max_tokens=max_tokens, workers=workers, memo=memo,
        item_memo=item_memo, salvage_truncated=salvage_truncated,
    )


def pass2_candidates(
    provider: Any, rows: Sequence[dict[str, Any]], locale: str, *, n: int = 3,
    system: str | None = None, batch_size: int | None = None, max_tokens: int = 4096,
    workers: int = 1, memo: BatchMemo | None = None, max_chars: int | None = None,
    item_memo: BatchMemo | None = None, salvage_truncated: bool = False,
) -> dict[str, list[str]]:
    """Ask Pass 2 writer model for n candidates per flagged row."""
    return _pass2_candidates(
        provider, rows, locale, n=n, system=system, batch_size=batch_size,
        max_tokens=max_tokens, workers=workers, memo=memo, max_chars=max_chars,
        item_memo=item_memo, salvage_truncated=salvage_truncated,
    )


def pick_candidates(
    provider: Any, items: Sequence[dict[str, Any]], locale: str, *, system: str | None = None,
    batch_size: int | None = None, max_tokens: int = 2048, workers: int = 1,
    memo: BatchMemo | None = None, max_chars: int | None = None,
    item_memo: BatchMemo | None = None, salvage_truncated: bool = False,
) -> dict[str, str]:
    """Run blind choice among Pass 2 candidates."""
    return _pick_candidates(
        provider, items, locale, system=system, batch_size=batch_size,
        max_tokens=max_tokens, workers=workers, memo=memo, max_chars=max_chars,
        item_memo=item_memo, salvage_truncated=salvage_truncated,
    )


__all__ = [
    "BATCH_CHARS", "BATCH_ROWS", "BATCH_WORKERS", "BatchMemo", "DEFAULT_SYSTEM", "EVERYDAY_CAP",
    "EVERYDAY_CHECK", "EVERYDAY_MIN_JURORS", "INSTRUCTIONS", "ISSUE_TYPES", "KEYED_ATTEMPTS",
    "REGISTERS", "SPLIT_DEPTH", "_call_keyed", "_text_len", "add_model_args", "backtranslate_rows",
    "chunked", "chunked_budget", "default_budget_path", "everyday_check", "everyday_rule", "make_router",
    "normalize_vote", "ordered_unique", "pass2_candidates", "pairwise_choices", "pick_candidates",
    "primes", "revote", "revote_many", "run_batches", "score_entries", "system_for", "translate_rows",
    "word_count",
]
