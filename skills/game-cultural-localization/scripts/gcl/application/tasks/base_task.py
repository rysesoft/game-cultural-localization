"""Template Method base class and keyed retry/split driver for LLM batch tasks."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from gcl.aspects.task_chain import run_batches_with_aspects
from gcl.domain.envelope_codec import envelope, extract_json
from gcl.domain.errors import L10nError, ProviderError
from gcl.ports.storage import MemoRepository

from .prompts import INSTRUCTIONS, KEYED_ATTEMPTS, SPLIT_DEPTH, primes

__layer__ = "application"
__pattern__ = "Template Method"
__owns__ = "missing key re-ask loop, binary half split retry and KeyedBatchTask base"


@dataclass(frozen=True)
class KeyedCallSpec:
    """Parameter object describing one keyed JSON task request/reply contract."""

    task: str
    list_field: str
    reply_field: str
    id_field: str
    accept: Callable[[Dict[str, Any]], bool]
    max_tokens: int
    split_depth: int = SPLIT_DEPTH


def _try_keyed_attempt(
    provider: Any,
    system: str,
    base_payload: Dict[str, Any],
    pending: List[Dict[str, Any]],
    spec: KeyedCallSpec,
) -> Tuple[Dict[str, Dict[str, Any]], bool, str]:
    payload = {**base_payload, "task": spec.task, spec.list_field: pending}
    try:
        res = provider.complete(system, envelope(INSTRUCTIONS[spec.task], payload), max_tokens=spec.max_tokens, json_mode=True)
    except ProviderError as exc:
        return {}, True, str(exc)
    err = ""
    try:
        data = extract_json(res.text)
    except L10nError:
        data = {}
        err = (
            f"reply is not valid JSON after {getattr(res, 'output_tokens', '?')} output tokens, "
            "a reply cut off at the output limit looks like this"
        )
    valid_ids = {str(p[spec.id_field]) for p in pending}
    got: Dict[str, Dict[str, Any]] = {}
    for item in (data.get(spec.reply_field) or []) if isinstance(data, dict) else []:
        if isinstance(item, dict) and str(item.get(spec.id_field)) in valid_ids and spec.accept(item):
            got[str(item[spec.id_field])] = item
    return got, False, err


def call_keyed(
    provider: Any,
    system: str,
    base_payload: Dict[str, Any],
    items: List[Dict[str, Any]],
    spec: KeyedCallSpec,
) -> Dict[str, Dict[str, Any]]:
    """Call provider with missing key retries and half splitting on non provider failures."""
    got: Dict[str, Dict[str, Any]] = {}
    pending = items
    last_error = ""
    provider_failed = False
    for _attempt in range(KEYED_ATTEMPTS):
        found, provider_failed, last_error = _try_keyed_attempt(provider, system, base_payload, pending, spec)
        got.update(found)
        pending = [p for p in pending if str(p[spec.id_field]) not in got]
        if not pending:
            return got
    if not provider_failed and spec.split_depth > 0 and len(pending) > 1:
        mid = len(pending) // 2
        half_spec = KeyedCallSpec(
            spec.task, spec.list_field, spec.reply_field, spec.id_field,
            spec.accept, spec.max_tokens, spec.split_depth - 1,
        )
        for half in (pending[:mid], pending[mid:]):
            got.update(call_keyed(provider, system, base_payload, half, half_spec))
        return got
    model = getattr(provider, "model", "?")
    first_ids = ", ".join(str(p[spec.id_field]) for p in pending[:5])
    suffix = f" (last error: {last_error})" if last_error else ""
    raise L10nError(f"{spec.task}: model {model} returned no valid answer for {len(pending)} item(s), first ids {first_ids}{suffix}")


class KeyedBatchTask(ABC):
    """Template Method executing chunked, memoized, cache primed LLM batch tasks."""

    task_name: str = ""

    @abstractmethod
    def build_system(self, locale: str, opts: Dict[str, Any]) -> str:
        """Return formatted system prompt for this task."""

    @abstractmethod
    def make_batches(self, items: Sequence[Any], opts: Dict[str, Any]) -> List[List[Any]]:
        """Partition items respecting row count and character budgets."""

    @abstractmethod
    def cache_tag(self, provider: Any, system: str, locale: str, opts: Dict[str, Any]) -> Any:
        """Build deterministic cache key tuple for MemoRepository."""

    @abstractmethod
    def run_batch(self, provider: Any, system: str, locale: str, batch: List[Any], opts: Dict[str, Any]) -> Dict[str, Any]:
        """Execute one batch against provider and extract normalized dict outputs."""

    def execute(self, provider: Any, items: Sequence[Any], locale: str, opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run Template Method pipeline across batches via run_batches_with_aspects."""
        cfg = dict(opts or {})
        sys_prompt = self.build_system(locale, cfg)
        batches = self.make_batches(items, cfg)
        tag = self.cache_tag(provider, sys_prompt, locale, cfg)
        workers = int(cfg.get("workers", 1))
        memo: Optional[MemoRepository] = cfg.get("memo")
        return run_batches_with_aspects(
            batches,
            lambda b: self.run_batch(provider, sys_prompt, locale, b, cfg),
            workers=workers,
            memo=memo,
            tag=tag,
            prime=primes(provider),
        )
