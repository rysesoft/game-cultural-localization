#!/usr/bin/env python3
"""Batched LLM task calls shared by the R&D tools (not a CLI).

Every task sends a user prompt built with providers.envelope(instruction, payload),
where payload["task"] names the task. The fake provider implements the same
tasks, so every tool runs offline with --dry-run.

Tasks and reply shapes
  pass1 / literal  rows[{key, source, register?, category?, speaker?}]  -> {"rows": [{key, target}]}
  roundtrip        rows[{key, target}]                                   -> {"rows": [{key, back}]}
  jury             entries[{key, target, register?, ...}], tier          -> {"votes": [{key, score, issue_type, reason, suggested}]}
  pairwise         pairs[{id, a, b}]                                     -> {"choices": [{id, choice: "a"|"b"}]}

Missing keys in a reply are asked for once more, then the call fails with L10nError.
The batched tasks take workers=N to send up to N batches at once (threads). Results are merged
by key in batch order, so the outcome does not depend on the worker count.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import L10nError  # noqa: E402
from providers import envelope, extract_json  # noqa: E402
from providers.base import ProviderError  # noqa: E402

KEYED_ATTEMPTS = 3  # one call and up to two re-asks for missing ids, an empty or broken reply counts as a failed attempt

T = TypeVar("T")

ISSUE_TYPES = ("translationese", "register", "tense", "regional_leak", "gender_leak", "ui_verb",
               "placeholder_grammar", "terminology", "other", "none")
REGISTERS = ("ui", "tutorial", "dialogue_casual", "dialogue_formal")

DEFAULT_SYSTEM: Dict[str, str] = {
    "pass1": ("You are a senior game localizer. Translate each source line into natural, native {locale} as a real player "
              "would say or read it. Keep every placeholder, tag and leading or trailing space exactly. Reply with JSON only."),
    "literal": ("Translate each English line into {locale} word for word. Keep the English word order and sentence structure, "
                "do not use idioms or everyday expressions, translate every word literally. Keep placeholders and tags. "
                "Reply with JSON only."),
    "roundtrip": ("Translate each {locale} line back into English as literally as possible, keeping its structure and word order. "
                  "Do not polish the English. Reply with JSON only."),
    "jury": ("You are a native {locale} gamer and LQA lead. You never see the source text. Score how natural each line sounds "
             "to a native player from 1 (broken) to 5 (native born). Reply with JSON only."),
    "pairwise": ("You are a native {locale} gamer. For each pair, choose the line a native speaker would more naturally write "
                 "or say. Reply with JSON only."),
}

INSTRUCTIONS: Dict[str, str] = {
    "pass1": 'Translate every row. Reply with {"rows": [{"key": "...", "target": "..."}]} and nothing else.',
    "literal": 'Translate every row literally. Reply with {"rows": [{"key": "...", "target": "..."}]} and nothing else.',
    "roundtrip": 'Back-translate every row into English. Reply with {"rows": [{"key": "...", "back": "..."}]} and nothing else.',
    "jury": ('Score every entry. Reply with {"votes": [{"key": "...", "score": 1-5, "issue_type": "translationese|register|tense|'
             'regional_leak|gender_leak|ui_verb|placeholder_grammar|terminology|other|none", "reason": "...", "suggested": "..."}]}. '
             'Use issue_type "none" and empty reason and suggested for score 5.'),
    "pairwise": 'For every pair reply with {"choices": [{"id": "...", "choice": "a" or "b"}]} and nothing else.',
    "pass2": ('Rewrite every row. Reply with {"rows": [{"key": "...", "candidates": ["...", "...", "..."]}]}, exactly the requested '
              'number of different candidates per row, and nothing else.'),
    "pick": ('For every item choose the candidate a native player would find most natural for this context. Reply with '
             '{"picks": [{"key": "...", "choice": "<candidate id>"}]} and nothing else.'),
    "deliberate": ('You already scored this line ("own"). "others" are the anonymous votes of two other jurors and "evidence" is the '
                   'mechanical evidence package (ban list hits, closest approved translation memory lines, back-translation signal). '
                   'Weigh them and vote once more. You may keep or change your score. Reply with {"score": 1-5, "issue_type": "...", '
                   '"reason": "...", "suggested": "..."} and nothing else.'),
}


def chunked(items: Sequence[T], size: int) -> Iterator[List[T]]:
    """Yield consecutive slices of at most `size` items."""
    size = max(1, int(size))
    for i in range(0, len(items), size):
        yield list(items[i:i + size])


def run_batches(batches: Sequence[T], fn: Callable[[T], Dict[str, Any]], workers: int = 1) -> Dict[str, Any]:
    """Call fn on every batch, at most `workers` at a time, and merge the dict results in batch order.

    Model calls spend most of their time waiting on the network, so threads give a near linear speed up.
    The first failing batch raises after the running ones finish.
    """
    out: Dict[str, Any] = {}
    if int(workers) <= 1 or len(batches) <= 1:
        for b in batches:
            out.update(fn(b))
        return out
    with ThreadPoolExecutor(max_workers=int(workers)) as ex:
        for res in ex.map(fn, batches):  # map yields in submission order, the merge stays deterministic
            out.update(res)
    return out


def system_for(task: str, locale: str, template: Optional[str] = None) -> str:
    """System prompt for a task: an explicit template (already rendered) or the built-in English default."""
    return template if template else DEFAULT_SYSTEM[task].format(locale=locale)


def _call_keyed(provider: Any, system: str, task: str, base_payload: Dict[str, Any], items: List[Dict[str, Any]],
                list_field: str, reply_field: str, id_field: str, accept: Callable[[Dict[str, Any]], bool],
                max_tokens: int) -> Dict[str, Dict[str, Any]]:
    """Call, re-ask for missing ids up to KEYED_ATTEMPTS in total, return id -> reply item.

    A provider error that survived the transport retries (for example a 200 reply without choices)
    and a reply that is not JSON both count as a failed attempt instead of ending the whole run.
    """
    got: Dict[str, Dict[str, Any]] = {}
    pending = items
    last_error = ""
    for _attempt in range(KEYED_ATTEMPTS):
        payload = dict(base_payload)
        payload["task"] = task
        payload[list_field] = pending
        try:
            res = provider.complete(system, envelope(INSTRUCTIONS[task], payload), max_tokens=max_tokens, json_mode=True)
        except ProviderError as exc:
            last_error = str(exc)
            continue
        try:
            data = extract_json(res.text)
        except L10nError:
            data = {}
        for item in (data.get(reply_field) or []) if isinstance(data, dict) else []:
            if isinstance(item, dict) and str(item.get(id_field)) in {str(p[id_field]) for p in pending} and accept(item):
                got[str(item[id_field])] = item
        pending = [p for p in pending if str(p[id_field]) not in got]
        if not pending:
            return got
    model = getattr(provider, "model", "?")
    raise L10nError(f"{task}: model {model} returned no valid answer for {len(pending)} item(s), first ids "
                    + ", ".join(str(p[id_field]) for p in pending[:5]) + (f" (last error: {last_error})" if last_error else ""))


def translate_rows(provider: Any, rows: Sequence[Dict[str, Any]], locale: str, *, task: str = "pass1",
                   system: Optional[str] = None, batch_size: int = 30, max_tokens: int = 4096,
                   extra: Optional[Dict[str, Any]] = None, workers: int = 1) -> Dict[str, str]:
    """Translate rows [{key, source, ...}] with task 'pass1' or 'literal'; return key -> target."""
    if task not in ("pass1", "literal"):
        raise L10nError(f"translate_rows: unknown task '{task}'")
    sys_prompt = system_for(task, locale, system)

    def one(batch: List[Dict[str, Any]]) -> Dict[str, str]:
        got = _call_keyed(provider, sys_prompt, task, {"locale": locale, **(extra or {})}, batch, "rows", "rows", "key",
                          lambda it: isinstance(it.get("target"), str), max_tokens)
        return {k: str(v["target"]) for k, v in got.items()}
    return run_batches(list(chunked(list(rows), batch_size)), one, workers)


def backtranslate_rows(provider: Any, rows: Sequence[Dict[str, Any]], locale: str, *, system: Optional[str] = None,
                       batch_size: int = 30, max_tokens: int = 4096, workers: int = 1) -> Dict[str, str]:
    """Back-translate rows [{key, target}] into English; return key -> back translation."""
    sys_prompt = system_for("roundtrip", locale, system)

    def one(batch: List[Dict[str, Any]]) -> Dict[str, str]:
        got = _call_keyed(provider, sys_prompt, "roundtrip", {"locale": locale}, batch, "rows", "rows", "key",
                          lambda it: isinstance(it.get("back"), str), max_tokens)
        return {k: str(v["back"]) for k, v in got.items()}
    return run_batches(list(chunked([{"key": r["key"], "target": r["target"]} for r in rows], batch_size)), one, workers)


def normalize_vote(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Coerce a raw vote into {score:int 1-5, issue_type, reason, suggested}; None when the score is unusable."""
    raw = item.get("score")
    try:
        score = int(raw) if not isinstance(raw, bool) and float(raw) == int(float(raw)) else None
    except (TypeError, ValueError):
        score = None
    if score is None or not 1 <= score <= 5:
        return None
    it = str(item.get("issue_type") or ("none" if score == 5 else "other"))
    if it not in ISSUE_TYPES:
        it = "other"
    if score == 5:
        it = "none"
    return {"score": score, "issue_type": it, "reason": str(item.get("reason") or ""), "suggested": str(item.get("suggested") or "")}


def score_entries(provider: Any, entries: Sequence[Dict[str, Any]], locale: str, *, tier: str = "J1",
                  system: Optional[str] = None, batch_size: int = 40, max_tokens: int = 4096,
                  extra: Optional[Dict[str, Any]] = None, workers: int = 1) -> Dict[str, Dict[str, Any]]:
    """Ask one jury member to score target-only entries [{key, target, ...}]; return key -> normalized vote."""
    sys_prompt = system_for("jury", locale, system)

    def one(batch: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        got = _call_keyed(provider, sys_prompt, "jury", {"locale": locale, "tier": tier, **(extra or {})}, batch, "entries", "votes", "key",
                          lambda it: normalize_vote(it) is not None, max_tokens)
        return {k: normalize_vote(v) for k, v in got.items()}  # type: ignore[misc]
    return run_batches(list(chunked(list(entries), batch_size)), one, workers)


def pairwise_choices(provider: Any, pairs: Sequence[Dict[str, Any]], locale: str, *, system: Optional[str] = None,
                     batch_size: int = 20, max_tokens: int = 2048, workers: int = 1) -> Dict[str, str]:
    """Ask one member which side of each pair [{id, a, b}] is more natural; return id -> 'a' | 'b'."""
    sys_prompt = system_for("pairwise", locale, system)

    def one(batch: List[Dict[str, Any]]) -> Dict[str, str]:
        got = _call_keyed(provider, sys_prompt, "pairwise", {"locale": locale}, batch, "pairs", "choices", "id",
                          lambda it: str(it.get("choice", "")).strip().lower() in ("a", "b"), max_tokens)
        return {k: str(v["choice"]).strip().lower() for k, v in got.items()}
    return run_batches(list(chunked(list(pairs), batch_size)), one, workers)


def revote(provider: Any, payload: Dict[str, Any], locale: str, *, system: Optional[str] = None, max_tokens: int = 1024) -> Dict[str, Any]:
    """One deliberation re-vote; asked twice at most, then L10nError. Returns a normalized vote."""
    sys_prompt = system_for("jury", locale, system)
    body = dict(payload)
    body["task"] = "deliberate"
    body["locale"] = locale
    for _attempt in range(2):
        res = provider.complete(sys_prompt, envelope(INSTRUCTIONS["deliberate"], body), max_tokens=max_tokens, json_mode=True)
        try:
            data = extract_json(res.text)
        except L10nError:
            continue
        vote = normalize_vote(data) if isinstance(data, dict) else None
        if vote is not None:
            return vote
    raise L10nError(f"deliberate: model {getattr(provider, 'model', '?')} returned no valid vote for {payload.get('key')}")


def pass2_candidates(provider: Any, rows: Sequence[Dict[str, Any]], locale: str, *, n: int = 3, system: Optional[str] = None,
                     batch_size: int = 10, max_tokens: int = 4096, workers: int = 1) -> Dict[str, List[str]]:
    """Ask the Pass 2 model for n candidates per row [{key, source, target, ...}]; returns key -> distinct non-empty candidates."""
    sys_prompt = system or DEFAULT_SYSTEM["pass1"].format(locale=locale)

    def ok(it: Dict[str, Any]) -> bool:
        c = it.get("candidates")
        return isinstance(c, list) and any(isinstance(x, str) and x.strip() for x in c)

    def one(batch: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        got = _call_keyed(provider, sys_prompt, "pass2", {"locale": locale, "n_candidates": n}, batch, "rows", "rows", "key", ok, max_tokens)
        return {k: ordered_unique(str(x) for x in v["candidates"] if isinstance(x, str) and x.strip())[:n] for k, v in got.items()}
    return run_batches(list(chunked(list(rows), batch_size)), one, workers)


def pick_candidates(provider: Any, items: Sequence[Dict[str, Any]], locale: str, *, system: Optional[str] = None,
                    batch_size: int = 20, max_tokens: int = 2048, workers: int = 1) -> Dict[str, str]:
    """Blind choice among candidates: items [{key, context..., candidates: [{id, text}]}] -> key -> chosen id."""
    sys_prompt = system_for("jury", locale, system)
    ids = {str(it["key"]): {str(c["id"]) for c in it["candidates"]} for it in items}

    def one(batch: List[Dict[str, Any]]) -> Dict[str, str]:
        got = _call_keyed(provider, sys_prompt, "pick", {"locale": locale}, batch, "items", "picks", "key",
                          lambda it: str(it.get("choice")) in ids.get(str(it.get("key")), set()), max_tokens)
        return {k: str(v["choice"]) for k, v in got.items()}
    return run_batches(list(chunked(list(items), batch_size)), one, workers)


def word_count(text: str) -> int:
    """Whitespace word count (CJK text without spaces counts 1 word per 2 characters)."""
    words = text.split()
    if len(words) <= 1 and len(text.strip()) > 4 and any("぀" <= ch <= "鿿" or "가" <= ch <= "힯" for ch in text):
        return max(1, len(text.strip()) // 2)
    return len(words)


def ordered_unique(items: Iterable[T]) -> List[T]:
    """Deduplicate while keeping the first occurrence order."""
    seen: List[T] = []
    for it in items:
        if it not in seen:
            seen.append(it)
    return seen


# --------------------------------------------------------------------------- #
# Shared CLI plumbing for every model calling tool
# --------------------------------------------------------------------------- #

def add_model_args(ap: Any) -> None:
    """Attach --providers-config, --dry-run, --fake-scenario and --budget-log."""
    ap.add_argument("--providers-config", default=None, help="providers.config.json (default: the bundled one)")
    ap.add_argument("--dry-run", action="store_true", help="Use the offline fake provider (no API key, no network)")
    ap.add_argument("--fake-scenario", help="Fake provider scenario JSON (with --dry-run)")
    ap.add_argument("--budget-log", default=None, help="budget.jsonl that receives one line per model call")


def default_budget_path(out: Path) -> Path:
    """budget.jsonl next to an output file, or in langpack/.cache when the output lives in the bundled langpack folder."""
    from l10n_common import SCRIPTS_DIR
    langpack = (SCRIPTS_DIR.parent / "langpack").resolve()
    out = Path(out).resolve()
    try:
        out.relative_to(langpack)
        return langpack / ".cache" / "budget.jsonl"
    except ValueError:
        return out.parent / "budget.jsonl"


def make_router(args: Any, roles: Sequence[str], budget_default: Optional[Path] = None) -> Any:
    """Router from the standard model arguments; checks the API keys of `roles` unless --dry-run."""
    from providers import FakeScenario, Router, load_providers_config
    cfg = load_providers_config(Path(args.providers_config) if getattr(args, "providers_config", None) else None)
    budget = Path(args.budget_log) if getattr(args, "budget_log", None) else budget_default
    router = Router(cfg, dry_run=bool(getattr(args, "dry_run", False)),
                    scenario=FakeScenario.load(Path(args.fake_scenario)) if getattr(args, "fake_scenario", None) else None,
                    budget_log=budget)
    router.require(roles)
    return router
