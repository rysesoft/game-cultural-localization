"""Concrete KeyedBatchTask strategies and task entry functions."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

from gcl.domain.envelope_codec import envelope, extract_json
from gcl.domain.errors import L10nError

from .base_task import KeyedBatchTask, KeyedCallSpec, call_keyed
from .prompts import (
    BATCH_CHARS, BATCH_ROWS, DEFAULT_SYSTEM, INSTRUCTIONS, _text_len, chunked_budget, ordered_unique, system_for,
)
from .vote_codec import everyday_check, normalize_vote

__layer__ = "application"
__pattern__ = "Concrete Template Methods"
__owns__ = "pass1, literal, roundtrip, jury, pairwise, revote, pass2 and blind pick task classes"


class TranslateTask(KeyedBatchTask):
    """Translate source rows with pass1 or literal system prompt."""

    def __init__(self, task_name: str = "pass1") -> None:
        if task_name not in ("pass1", "literal"):
            raise L10nError(f"translate_rows: unknown task '{task_name}'")
        self.task_name = task_name

    def build_system(self, locale: str, opts: Dict[str, Any]) -> str:
        return system_for(self.task_name, locale, opts.get("system"))

    def make_batches(self, items: Sequence[Any], opts: Dict[str, Any]) -> List[List[Any]]:
        bsize = opts.get("batch_size") or BATCH_ROWS[self.task_name]
        bchars = opts.get("max_chars") or BATCH_CHARS[self.task_name]
        return chunked_budget(list(items), bsize, bchars, _text_len("source"))

    def cache_tag(self, provider: Any, system: str, locale: str, opts: Dict[str, Any]) -> Any:
        return (
            self.task_name, getattr(provider, "model", "?"), system, INSTRUCTIONS[self.task_name],
            locale, opts.get("extra") or {}, int(opts.get("max_tokens", 4096)),
        )

    def run_batch(self, provider: Any, system: str, locale: str, batch: List[Any], opts: Dict[str, Any]) -> Dict[str, Any]:
        needs = {str(r.get("key")) for r in batch if str(r.get("source", "")).strip()}

        def ok(it: Dict[str, Any]) -> bool:
            t = it.get("target")
            return isinstance(t, str) and (bool(t.strip()) or str(it.get("key")) not in needs)

        spec = KeyedCallSpec(
            self.task_name, "rows", "rows", "key", ok, int(opts.get("max_tokens", 4096)),
            salvage_truncated=bool(opts.get("salvage_truncated", False)),
        )
        payload = {"locale": locale, **(opts.get("extra") or {})}
        got = call_keyed(provider, system, payload, batch, spec)
        return {k: str(v["target"]) for k, v in got.items()}


class BacktranslateTask(KeyedBatchTask):
    """Literal back translation task for roundtrip calque checks."""

    task_name = "roundtrip"

    def build_system(self, locale: str, opts: Dict[str, Any]) -> str:
        return system_for("roundtrip", locale, opts.get("system"))

    def make_batches(self, items: Sequence[Any], opts: Dict[str, Any]) -> List[List[Any]]:
        slim = [{"key": r["key"], "target": r["target"]} for r in items]
        return chunked_budget(slim, opts.get("batch_size") or BATCH_ROWS["roundtrip"], opts.get("max_chars") or BATCH_CHARS["roundtrip"], _text_len("target"))

    def cache_tag(self, provider: Any, system: str, locale: str, opts: Dict[str, Any]) -> Any:
        return ("roundtrip", getattr(provider, "model", "?"), system, INSTRUCTIONS["roundtrip"], locale, int(opts.get("max_tokens", 4096)))

    def item_cache_value(self, item: Any, opts: Dict[str, Any]) -> Any:
        return {"key": item["key"], "target": item["target"]}

    def run_batch(self, provider: Any, system: str, locale: str, batch: List[Any], opts: Dict[str, Any]) -> Dict[str, Any]:
        spec = KeyedCallSpec(
            "roundtrip", "rows", "rows", "key", lambda it: isinstance(it.get("back"), str),
            int(opts.get("max_tokens", 4096)), salvage_truncated=bool(opts.get("salvage_truncated", False)),
        )
        got = call_keyed(provider, system, {"locale": locale}, batch, spec)
        return {k: str(v["back"]) for k, v in got.items()}


class JuryScoreTask(KeyedBatchTask):
    """Blind target scoring task normalized through everyday_check."""

    task_name = "jury"

    def build_system(self, locale: str, opts: Dict[str, Any]) -> str:
        return system_for("jury", locale, opts.get("system"))

    def make_batches(self, items: Sequence[Any], opts: Dict[str, Any]) -> List[List[Any]]:
        return chunked_budget(list(items), opts.get("batch_size") or BATCH_ROWS["jury"], opts.get("max_chars") or BATCH_CHARS["jury"], _text_len("target"))

    def cache_tag(self, provider: Any, system: str, locale: str, opts: Dict[str, Any]) -> Any:
        return (
            "jury", getattr(provider, "model", "?"), system, INSTRUCTIONS["jury"],
            locale, opts.get("tier", "J1"), opts.get("extra") or {}, int(opts.get("max_tokens", 4096)),
        )

    def run_batch(self, provider: Any, system: str, locale: str, batch: List[Any], opts: Dict[str, Any]) -> Dict[str, Any]:
        spec = KeyedCallSpec(
            "jury", "entries", "votes", "key", lambda it: normalize_vote(it) is not None,
            int(opts.get("max_tokens", 4096)), salvage_truncated=bool(opts.get("salvage_truncated", False)),
        )
        payload = {"locale": locale, "tier": opts.get("tier", "J1"), **(opts.get("extra") or {})}
        got = call_keyed(provider, system, payload, batch, spec)
        targets = {str(e.get("key")): str(e.get("target", "")) for e in batch}
        return {k: everyday_check(normalize_vote(v), targets.get(k, "")) for k, v in got.items()}  # type: ignore[arg-type]


class PairwiseChoiceTask(KeyedBatchTask):
    """Forced choice A/B comparison task for critic calibration."""

    task_name = "pairwise"
    item_id_field = "id"

    def build_system(self, locale: str, opts: Dict[str, Any]) -> str:
        return system_for("pairwise", locale, opts.get("system"))

    def make_batches(self, items: Sequence[Any], opts: Dict[str, Any]) -> List[List[Any]]:
        return chunked_budget(list(items), opts.get("batch_size") or BATCH_ROWS["pairwise"], opts.get("max_chars") or BATCH_CHARS["pairwise"], _text_len("a", "b"))

    def cache_tag(self, provider: Any, system: str, locale: str, opts: Dict[str, Any]) -> Any:
        return ("pairwise", getattr(provider, "model", "?"), system, INSTRUCTIONS["pairwise"], locale, int(opts.get("max_tokens", 2048)))

    def run_batch(self, provider: Any, system: str, locale: str, batch: List[Any], opts: Dict[str, Any]) -> Dict[str, Any]:
        spec = KeyedCallSpec(
            "pairwise", "pairs", "choices", "id", lambda it: str(it.get("choice", "")).strip().lower() in ("a", "b"),
            int(opts.get("max_tokens", 2048)), salvage_truncated=bool(opts.get("salvage_truncated", False)),
        )
        got = call_keyed(provider, system, {"locale": locale}, batch, spec)
        return {k: str(v["choice"]).strip().lower() for k, v in got.items()}


class DeliberateManyTask(KeyedBatchTask):
    """Batched J3 deliberation re-vote task."""

    task_name = "deliberate_many"

    def build_system(self, locale: str, opts: Dict[str, Any]) -> str:
        return system_for("jury", locale, opts.get("system"))

    def make_batches(self, items: Sequence[Any], opts: Dict[str, Any]) -> List[List[Any]]:
        return chunked_budget(
            list(items), opts.get("batch_size") or BATCH_ROWS["deliberate"],
            opts.get("max_chars") or BATCH_CHARS["deliberate"], lambda pl: json.dumps(pl, ensure_ascii=False),
        )

    def cache_tag(self, provider: Any, system: str, locale: str, opts: Dict[str, Any]) -> Any:
        return ("deliberate_many", getattr(provider, "model", "?"), system, INSTRUCTIONS["deliberate_many"], locale, int(opts.get("max_tokens", 4096)))

    def run_batch(self, provider: Any, system: str, locale: str, batch: List[Any], opts: Dict[str, Any]) -> Dict[str, Any]:
        spec = KeyedCallSpec(
            "deliberate_many", "lines", "votes", "key", lambda it: normalize_vote(it) is not None,
            int(opts.get("max_tokens", 4096)), salvage_truncated=bool(opts.get("salvage_truncated", False)),
        )
        got = call_keyed(provider, system, {"locale": locale}, batch, spec)
        targets = opts.get("targets", {})
        return {k: everyday_check(normalize_vote(v), targets.get(k, "")) for k, v in got.items()}  # type: ignore[arg-type]


class Pass2CandidateTask(KeyedBatchTask):
    """Writer candidate generation task for Pass 2."""

    task_name = "pass2"

    def build_system(self, locale: str, opts: Dict[str, Any]) -> str:
        sys_tpl = opts.get("system")
        return sys_tpl if sys_tpl else DEFAULT_SYSTEM["pass1"].format(locale=locale)

    def make_batches(self, items: Sequence[Any], opts: Dict[str, Any]) -> List[List[Any]]:
        return chunked_budget(list(items), opts.get("batch_size") or BATCH_ROWS["pass2"], opts.get("max_chars") or BATCH_CHARS["pass2"], _text_len("source", "target"))

    def cache_tag(self, provider: Any, system: str, locale: str, opts: Dict[str, Any]) -> Any:
        return ("pass2", getattr(provider, "model", "?"), system, INSTRUCTIONS["pass2"], locale, int(opts.get("n", 3)), int(opts.get("max_tokens", 4096)))

    def run_batch(self, provider: Any, system: str, locale: str, batch: List[Any], opts: Dict[str, Any]) -> Dict[str, Any]:
        n = int(opts.get("n", 3))

        def ok(it: Dict[str, Any]) -> bool:
            c = it.get("candidates")
            return isinstance(c, list) and any(isinstance(x, str) and x.strip() for x in c)

        spec = KeyedCallSpec(
            "pass2", "rows", "rows", "key", ok, int(opts.get("max_tokens", 4096)),
            salvage_truncated=bool(opts.get("salvage_truncated", False)),
        )
        got = call_keyed(provider, system, {"locale": locale, "n_candidates": n}, batch, spec)
        return {k: ordered_unique(str(x) for x in v["candidates"] if isinstance(x, str) and x.strip())[:n] for k, v in got.items()}


class BlindPickTask(KeyedBatchTask):
    """Blind juror candidate selection task."""

    task_name = "pick"

    def build_system(self, locale: str, opts: Dict[str, Any]) -> str:
        return system_for("jury", locale, opts.get("system"))

    def make_batches(self, items: Sequence[Any], opts: Dict[str, Any]) -> List[List[Any]]:
        return chunked_budget(
            list(items), opts.get("batch_size") or BATCH_ROWS["pick"],
            opts.get("max_chars") or BATCH_CHARS["pick"],
            lambda it: "".join(str(c.get("text", "")) for c in it.get("candidates", [])),
        )

    def cache_tag(self, provider: Any, system: str, locale: str, opts: Dict[str, Any]) -> Any:
        return ("pick", getattr(provider, "model", "?"), system, INSTRUCTIONS["pick"], locale, int(opts.get("max_tokens", 2048)))

    def run_batch(self, provider: Any, system: str, locale: str, batch: List[Any], opts: Dict[str, Any]) -> Dict[str, Any]:
        ids = opts.get("ids", {})
        spec = KeyedCallSpec(
            "pick", "items", "picks", "key",
            lambda it: str(it.get("choice")) in ids.get(str(it.get("key")), set()),
            int(opts.get("max_tokens", 2048)), salvage_truncated=bool(opts.get("salvage_truncated", False)),
        )
        got = call_keyed(provider, system, {"locale": locale}, batch, spec)
        return {k: str(v["choice"]) for k, v in got.items()}


def translate_rows(provider: Any, rows: Sequence[Dict[str, Any]], locale: str, **kw: Any) -> Dict[str, str]:
    opts = {"max_tokens": 4096, **kw}
    return TranslateTask(str(opts.pop("task", "pass1"))).execute(provider, rows, locale, opts)


def backtranslate_rows(provider: Any, rows: Sequence[Dict[str, Any]], locale: str, **kw: Any) -> Dict[str, str]:
    return BacktranslateTask().execute(provider, rows, locale, {"max_tokens": 4096, **kw})


def score_entries(provider: Any, entries: Sequence[Dict[str, Any]], locale: str, **kw: Any) -> Dict[str, Dict[str, Any]]:
    return JuryScoreTask().execute(provider, entries, locale, {"max_tokens": 4096, "tier": "J1", **kw})


def pairwise_choices(provider: Any, pairs: Sequence[Dict[str, Any]], locale: str, **kw: Any) -> Dict[str, str]:
    return PairwiseChoiceTask().execute(provider, pairs, locale, {"max_tokens": 2048, **kw})


def revote(provider: Any, payload: Dict[str, Any], locale: str, **kw: Any) -> Dict[str, Any]:
    sys_prompt = system_for("jury", locale, kw.get("system"))
    max_tokens = int(kw.get("max_tokens", 1024))
    body = {**payload, "task": "deliberate", "locale": locale}
    for _attempt in range(2):
        res = provider.complete(sys_prompt, envelope(INSTRUCTIONS["deliberate"], body), max_tokens=max_tokens, json_mode=True)
        try:
            data = extract_json(res.text)
        except L10nError:
            continue
        vote = normalize_vote(data) if isinstance(data, dict) else None
        if vote is not None:
            return everyday_check(vote, str(payload.get("target", "")))
    raise L10nError(f"deliberate: model {getattr(provider, 'model', '?')} returned no valid vote for {payload.get('key')}")


def revote_many(provider: Any, payloads: Sequence[Dict[str, Any]], locale: str, **kw: Any) -> Dict[str, Dict[str, Any]]:
    targets = {str(pl["key"]): str(pl.get("target", "")) for pl in payloads}
    return DeliberateManyTask().execute(provider, payloads, locale, {"max_tokens": 4096, "targets": targets, **kw})


def pass2_candidates(provider: Any, rows: Sequence[Dict[str, Any]], locale: str, **kw: Any) -> Dict[str, List[str]]:
    return Pass2CandidateTask().execute(provider, rows, locale, {"n": 3, "max_tokens": 4096, **kw})


def pick_candidates(provider: Any, items: Sequence[Dict[str, Any]], locale: str, **kw: Any) -> Dict[str, str]:
    ids = {str(it["key"]): {str(c["id"]) for c in it["candidates"]} for it in items}
    return BlindPickTask().execute(provider, items, locale, {"max_tokens": 2048, "ids": ids, **kw})
