"""Template Method base class and keyed retry/split driver for LLM batch tasks."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from collections.abc import Callable, Sequence
from typing import Any

from gcl.aspects.task_chain import run_batches_with_aspects
from gcl.domain.envelope_codec import envelope, extract_json, salvage_keyed_items
from gcl.domain.errors import L10nError, PermanentProviderError, ProviderError
from gcl.ports.storage import MemoRepository

from .prompts import INSTRUCTIONS, KEYED_ATTEMPTS, SPLIT_DEPTH, primes

__layer__ = "application"
__pattern__ = "Template Method"
__owns__ = "missing key re-ask loop, binary half split retry and KeyedBatchTask base"


@dataclass(frozen=True, slots=True)
class KeyedCallSpec:
    """Parameter object describing one keyed JSON task request/reply contract."""

    task: str
    list_field: str
    reply_field: str
    id_field: str
    accept: Callable[[dict[str, Any]], bool]
    max_tokens: int
    split_depth: int = SPLIT_DEPTH
    salvage_truncated: bool = False


def _try_keyed_attempt(
    provider: Any,
    system: str,
    base_payload: dict[str, Any],
    pending: list[dict[str, Any]],
    spec: KeyedCallSpec,
) -> tuple[dict[str, dict[str, Any]], Any, str]:
    payload = {**base_payload, "task": spec.task, spec.list_field: pending}
    try:
        res = provider.complete(system, envelope(INSTRUCTIONS[spec.task], payload), max_tokens=spec.max_tokens, json_mode=True)
    except PermanentProviderError as exc:
        return {}, "permanent", str(exc)
    except ProviderError as exc:
        return {}, "transient", str(exc)
    err = ""
    try:
        data = extract_json(res.text)
    except L10nError:
        recovered = salvage_keyed_items(res.text, spec.reply_field) if spec.salvage_truncated else []
        data = {spec.reply_field: recovered} if recovered else {}
        err = (
            f"reply is not valid JSON after {getattr(res, 'output_tokens', '?')} output tokens, "
            "a reply cut off at the output limit looks like this"
        )
    valid_ids = {str(p[spec.id_field]) for p in pending}
    got: dict[str, dict[str, Any]] = {}
    for item in (data.get(spec.reply_field) or []) if isinstance(data, dict) else []:
        if isinstance(item, dict) and str(item.get(spec.id_field)) in valid_ids and spec.accept(item):
            got[str(item[spec.id_field])] = item
    return got, False, err


def call_keyed(
    provider: Any,
    system: str,
    base_payload: dict[str, Any],
    items: list[dict[str, Any]],
    spec: KeyedCallSpec,
) -> dict[str, dict[str, Any]]:
    """Call provider with missing key retries and half splitting on non provider failures."""
    got: dict[str, dict[str, Any]] = {}
    pending = items
    last_error = ""
    provider_failed: Any = False
    for _attempt in range(KEYED_ATTEMPTS):
        found, provider_failed, last_error = _try_keyed_attempt(provider, system, base_payload, pending, spec)
        got.update(found)
        pending = [p for p in pending if str(p[spec.id_field]) not in got]
        if not pending:
            return got
        if provider_failed == "permanent":
            break
    if not provider_failed and spec.split_depth > 0 and len(pending) > 1:
        mid = len(pending) // 2
        half_spec = KeyedCallSpec(
            spec.task, spec.list_field, spec.reply_field, spec.id_field,
            spec.accept, spec.max_tokens, spec.split_depth - 1, spec.salvage_truncated,
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
    item_id_field: str = "key"

    def item_cache_value(self, item: Any, opts: dict[str, Any]) -> Any:
        """Projection stored inside item level memo key; override when payloads omit fields."""
        return item

    def _partition_item_memo(
        self, item_memo: MemoRepository | None, tag: Any, items: Sequence[Any], cfg: dict[str, Any],
    ) -> tuple[dict[str, Any], list[Any], dict[str, str]]:
        if item_memo is None:
            return {}, list(items), {}
        cached: dict[str, Any] = {}
        pending: list[Any] = []
        key_map: dict[str, str] = {}
        id_field = self.item_id_field
        for it in items:
            iid = str(it[id_field])
            ckey = item_memo.make_key(tag, iid, self.item_cache_value(it, cfg))
            hit = item_memo.get(ckey)
            if hit is not None:
                cached[iid] = hit
            else:
                pending.append(it)
                key_map[iid] = ckey
        return cached, pending, key_map

    @staticmethod
    def _store_item_memo(item_memo: MemoRepository, key_map: dict[str, str], fresh: dict[str, Any]) -> None:
        to_write = {key_map[k]: v for k, v in fresh.items() if k in key_map}
        if not to_write:
            return
        if hasattr(item_memo, "put_many"):
            item_memo.put_many(to_write)
        else:
            for ck, val in to_write.items():
                item_memo.put(ck, val)

    def execute(self, provider: Any, items: Sequence[Any], locale: str, opts: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run Template Method pipeline across batches via run_batches_with_aspects and item_memo."""
        cfg = dict(opts or {})
        sys_prompt = self.build_system(locale, cfg)
        tag = self.cache_tag(provider, sys_prompt, locale, cfg)
        item_memo: MemoRepository | None = cfg.get("item_memo")
        cached, pending_items, key_map = self._partition_item_memo(item_memo, tag, items, cfg)
        if not pending_items:
            return cached
        batches = self.make_batches(pending_items, cfg)
        workers = int(cfg.get("workers", 1))
        memo: MemoRepository | None = cfg.get("memo")
        fresh = run_batches_with_aspects(
            batches,
            lambda b: self.run_batch(provider, sys_prompt, locale, b, cfg),
            workers=workers,
            memo=memo,
            tag=tag,
            prime=primes(provider),
        )
        if item_memo is not None and fresh:
            self._store_item_memo(item_memo, key_map, fresh)
        if not cached:
            return fresh
        merged = {**cached, **fresh}
        id_field = self.item_id_field
        return {str(it[id_field]): merged[str(it[id_field])] for it in items if str(it[id_field]) in merged}

    @abstractmethod
    def build_system(self, locale: str, opts: dict[str, Any]) -> str:
        """Return formatted system prompt for this task."""

    @abstractmethod
    def make_batches(self, items: Sequence[Any], opts: dict[str, Any]) -> list[list[Any]]:
        """Partition items respecting row count and character budgets."""

    @abstractmethod
    def cache_tag(self, provider: Any, system: str, locale: str, opts: dict[str, Any]) -> Any:
        """Build deterministic cache key tuple for MemoRepository."""

    @abstractmethod
    def run_batch(self, provider: Any, system: str, locale: str, batch: list[Any], opts: dict[str, Any]) -> dict[str, Any]:
        """Execute one batch against provider and extract normalized dict outputs."""
