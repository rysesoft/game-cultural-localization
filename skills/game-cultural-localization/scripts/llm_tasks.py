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

import hashlib
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import L10nError  # noqa: E402
from providers import envelope, extract_json  # noqa: E402
from providers.base import ProviderError  # noqa: E402

KEYED_ATTEMPTS = 3  # one call and up to two re-asks for missing ids, an empty or broken reply counts as a failed attempt
# Items still unanswered after every attempt are split in halves and asked again, at most twice (40, 20, 10).
# A long batch can make a model think until its reply is cut at the output limit, smaller halves fit. A
# provider error on the last attempt is not split, an outage must not fan out into many small calls.
SPLIT_DEPTH = 2

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

# The first question a juror asks of a line, set by the studio. Every word of it must be part of everyday use of the
# language. A correct but rare, bookish or dictionary word is what makes a translation sound translated. The answer
# weighs heavily. When at least EVERYDAY_MIN_JURORS jurors of a tier find such a word in the same line, the code caps
# every score of that tier at EVERYDAY_CAP, so the line never passes and J3 sends it to Pass 2 (everyday_rule).
# One juror alone does not cap. Measured on 385 tr-TR pairs with J1, a single flag sent 29 % of the studio's own lines
# up a tier (16 % without the check) for 2 more points on the literal lines, two flags 17 %.
EVERYDAY_CAP = 3
EVERYDAY_MIN_JURORS = 2
EVERYDAY_CHECK = ('First ask of every word of the line whether it belongs to everyday use of the target language. Would a native '
                  'speaker use it in daily life for this meaning, or read it in this kind of game text? A rare, bookish, archaic, '
                  'made up, word for word or dictionary choice is not everyday, even when it is correct. Proper names, placeholders, '
                  'tags and the game\'s own terms that the context map names are not judged this way. List the words of the line '
                  'that are not everyday in "odd_words", an empty list when there is none. This answer weighs heavily. When two of '
                  'the three jurors list a word of the same line, the line scores 3 at most. ')

INSTRUCTIONS: Dict[str, str] = {
    "pass1": 'Translate every row. Reply with {"rows": [{"key": "...", "target": "..."}]} and nothing else.',
    "literal": 'Translate every row literally. Reply with {"rows": [{"key": "...", "target": "..."}]} and nothing else.',
    "roundtrip": 'Back-translate every row into English. Reply with {"rows": [{"key": "...", "back": "..."}]} and nothing else.',
    "jury": (EVERYDAY_CHECK + 'Then score every entry. Reply with {"votes": [{"key": "...", "odd_words": ["..."], "score": 1-5, '
             '"issue_type": "translationese|register|tense|regional_leak|gender_leak|ui_verb|placeholder_grammar|terminology|other|none", '
             '"reason": "...", "suggested": "..."}]}. Use issue_type "none" and empty reason and suggested for score 5.'),
    "pairwise": 'For every pair reply with {"choices": [{"id": "...", "choice": "a" or "b"}]} and nothing else.',
    "pass2": ('Rewrite every row. A row may carry "odd_words", words the jurors found not everyday for a native speaker. Replace '
              'them with words a native uses every day, unless the context map names one as the game\'s own term. Reply with '
              '{"rows": [{"key": "...", "candidates": ["...", "...", "..."]}]}, exactly the requested number of different candidates '
              'per row, and nothing else.'),
    "pick": ('For every item choose the candidate a native player would find most natural for this context. Reply with '
             '{"picks": [{"key": "...", "choice": "<candidate id>"}]} and nothing else.'),
    "deliberate": ('You already scored this line ("own"). "others" are the anonymous votes of two other jurors and "evidence" is the '
                   'mechanical evidence package (ban list hits, closest approved translation memory lines, back-translation signal). '
                   'Weigh them and vote once more. You may keep or change your score. ' + EVERYDAY_CHECK + 'Reply with '
                   '{"odd_words": ["..."], "score": 1-5, "issue_type": "...", "reason": "...", "suggested": "..."} and nothing else.'),
    "deliberate_many": ('You already scored every line in "lines" ("own"). For each line "others" are the anonymous votes of two other '
                        'jurors and "evidence" is the mechanical evidence package (ban list hits, closest approved translation memory '
                        'lines, back-translation signal). Weigh them and vote once more on every line, each on its own. You may keep '
                        'or change your score. ' + EVERYDAY_CHECK + 'Reply with {"votes": [{"key": "...", "odd_words": ["..."], '
                        '"score": 1-5, "issue_type": "...", "reason": "...", "suggested": "..."}]}, one vote per line, and nothing else.'),
}


def chunked(items: Sequence[T], size: int) -> Iterator[List[T]]:
    """Yield consecutive slices of at most `size` items."""
    size = max(1, int(size))
    for i in range(0, len(items), size):
        yield list(items[i:i + size])


# Rows per model call. Every call resends the system prompt (the context map, the warm-up lines and the few-shots,
# up to about 48000 tokens for Pass 1), so fewer and larger calls cost less. On the 13 language run of 2026-11-27
# one provider saw 2696 requests and 69M tokens in a day with 30 rows per Pass 1 call and 40 per jury call. A row
# limit alone would put a hundred long letters into one call, so every batch also has a character budget.
BATCH_ROWS = {"pass1": 100, "literal": 100, "roundtrip": 100, "jury": 100, "pairwise": 50, "pass2": 30, "pick": 50, "deliberate": 25}
BATCH_CHARS = {"pass1": 20000, "literal": 20000, "roundtrip": 20000, "jury": 24000, "pairwise": 24000, "pass2": 10000, "pick": 24000,
               "deliberate": 16000}


BATCH_WORKERS = 64  # calls in flight per step with --batch, they wait for their job and cost no rate limit


def chunked_budget(items: Sequence[T], size: int, max_chars: int, text_of: Callable[[T], str]) -> List[List[T]]:
    """Consecutive slices of at most `size` items whose texts add up to at most `max_chars` characters.

    An item longer than the budget goes alone. The order of the items is kept, so the merged result does not change.
    """
    size, max_chars = max(1, int(size)), max(1, int(max_chars))
    out: List[List[T]] = []
    cur: List[T] = []
    used = 0
    for it in items:
        n = len(text_of(it))
        if cur and (len(cur) >= size or used + n > max_chars):
            out.append(cur)
            cur, used = [], 0
        cur.append(it)
        used += n
    if cur:
        out.append(cur)
    return out


def _text_len(*fields: str) -> Callable[[Dict[str, Any]], str]:
    def text_of(item: Dict[str, Any]) -> str:
        return "".join(str(item.get(f, "")) for f in fields)
    return text_of


def primes(provider: Any) -> bool:
    """Whether a wave of calls to this provider starts with one call alone to write the prompt cache.

    A batch API provider gathers the calls into one job, a call alone first would cost a whole job's wait.
    """
    return not getattr(provider, "batched", False)


class BatchMemo:
    """Finished batch answers in a JSON file, so a stopped run resumes at the batch where it stopped.

    The key is a sha256 of the task, the model, the system prompt and the batch itself, so a changed prompt
    or batch never reuses an old answer. Thread safe, the file is replaced atomically after every batch.
    The first calibration with the context map lost the finished batches of four models when Google's
    spend limit and a DeepSeek queue stopped them halfway, this keeps every one of them.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self.hits = 0
        self._data: Dict[str, Any] = {}
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise L10nError(f"{self.path}: batch cache is not valid JSON ({exc.msg}), delete it to start over")
            self._data = data if isinstance(data, dict) else {}

    @staticmethod
    def key(*parts: Any) -> str:
        return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            value = self._data.get(key)
            if value is not None:
                self.hits += 1
            return value

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(self.path)

    def __len__(self) -> int:
        return len(self._data)


def run_batches(batches: Sequence[T], fn: Callable[[T], Dict[str, Any]], workers: int = 1,
                memo: Optional[BatchMemo] = None, tag: Any = None, prime: bool = True) -> Dict[str, Any]:
    """Call fn on every batch, at most `workers` at a time, and merge the dict results in batch order.

    Model calls spend most of their time waiting on the network, so threads give a near linear speed up.
    The first failing batch raises after the running ones finish. With a memo every finished batch is kept
    under (tag, batch) and a rerun answers it from the file without a model call.

    With `prime` the first batch runs alone before the others start. All batches of a wave share the system
    prompt, and parallel first calls each write it to the prompt cache (1.25x the input price at Anthropic)
    because none of them can read what the others are still writing. On 2026-11-27 eight parallel first calls
    all paid the write and the Sonnet cache hit rate was 61 percent. One call first writes it once.
    """
    call = fn
    if memo is not None:
        def call(b: T) -> Dict[str, Any]:
            k = memo.key(tag, b)
            hit = memo.get(k)
            if hit is not None:
                return hit
            res = fn(b)
            memo.put(k, res)
            return res
    out: Dict[str, Any] = {}
    if int(workers) <= 1 or len(batches) <= 1:
        for b in batches:
            out.update(call(b))
        return out
    rest = list(batches)
    if prime:
        out.update(call(rest.pop(0)))
    with ThreadPoolExecutor(max_workers=int(workers)) as ex:
        for res in ex.map(call, rest):  # map yields in submission order, the merge stays deterministic
            out.update(res)
    return out


def system_for(task: str, locale: str, template: Optional[str] = None) -> str:
    """System prompt for a task: an explicit template (already rendered) or the built-in English default."""
    return template if template else DEFAULT_SYSTEM[task].format(locale=locale)


def _call_keyed(provider: Any, system: str, task: str, base_payload: Dict[str, Any], items: List[Dict[str, Any]],
                list_field: str, reply_field: str, id_field: str, accept: Callable[[Dict[str, Any]], bool],
                max_tokens: int, split_depth: int = SPLIT_DEPTH) -> Dict[str, Dict[str, Any]]:
    """Call, re-ask for missing ids up to KEYED_ATTEMPTS in total, return id -> reply item.

    A provider error that survived the transport retries (for example a 200 reply without choices)
    and a reply that is not JSON both count as a failed attempt instead of ending the whole run.
    Items still missing after that are asked again in two halves (SPLIT_DEPTH levels at most).
    """
    got: Dict[str, Dict[str, Any]] = {}
    pending = items
    last_error = ""
    provider_failed = False
    for _attempt in range(KEYED_ATTEMPTS):
        payload = dict(base_payload)
        payload["task"] = task
        payload[list_field] = pending
        try:
            res = provider.complete(system, envelope(INSTRUCTIONS[task], payload), max_tokens=max_tokens, json_mode=True)
        except ProviderError as exc:
            last_error = str(exc)
            provider_failed = True
            continue
        provider_failed = False
        try:
            data = extract_json(res.text)
        except L10nError:
            data = {}
            last_error = (f"reply is not valid JSON after {getattr(res, 'output_tokens', '?')} output tokens, "
                          "a reply cut off at the output limit looks like this")
        for item in (data.get(reply_field) or []) if isinstance(data, dict) else []:
            if isinstance(item, dict) and str(item.get(id_field)) in {str(p[id_field]) for p in pending} and accept(item):
                got[str(item[id_field])] = item
        pending = [p for p in pending if str(p[id_field]) not in got]
        if not pending:
            return got
    if not provider_failed and split_depth > 0 and len(pending) > 1:
        mid = len(pending) // 2
        for half in (pending[:mid], pending[mid:]):
            got.update(_call_keyed(provider, system, task, base_payload, half, list_field, reply_field, id_field, accept,
                                   max_tokens, split_depth - 1))
        return got
    model = getattr(provider, "model", "?")
    raise L10nError(f"{task}: model {model} returned no valid answer for {len(pending)} item(s), first ids "
                    + ", ".join(str(p[id_field]) for p in pending[:5]) + (f" (last error: {last_error})" if last_error else ""))


def translate_rows(provider: Any, rows: Sequence[Dict[str, Any]], locale: str, *, task: str = "pass1",
                   system: Optional[str] = None, batch_size: Optional[int] = None, max_tokens: int = 4096,
                   extra: Optional[Dict[str, Any]] = None, workers: int = 1, memo: Optional[BatchMemo] = None,
                   max_chars: Optional[int] = None) -> Dict[str, str]:
    """Translate rows [{key, source, ...}] with task 'pass1' or 'literal'; return key -> target.

    An empty target for a row with a source counts as no answer and is asked again. On 2026-11-27 a Pass 1 reply
    gave two zh-Hant rows an empty target, the jury never saw them and the game would have shown nothing.
    """
    if task not in ("pass1", "literal"):
        raise L10nError(f"translate_rows: unknown task '{task}'")
    sys_prompt = system_for(task, locale, system)

    def one(batch: List[Dict[str, Any]]) -> Dict[str, str]:
        needs = {str(r.get("key")) for r in batch if str(r.get("source", "")).strip()}

        def ok(it: Dict[str, Any]) -> bool:
            t = it.get("target")
            return isinstance(t, str) and (bool(t.strip()) or str(it.get("key")) not in needs)
        got = _call_keyed(provider, sys_prompt, task, {"locale": locale, **(extra or {})}, batch, "rows", "rows", "key", ok, max_tokens)
        return {k: str(v["target"]) for k, v in got.items()}
    tag = (task, getattr(provider, "model", "?"), sys_prompt, INSTRUCTIONS[task], locale, extra or {}, max_tokens)
    batches = chunked_budget(list(rows), batch_size or BATCH_ROWS[task], max_chars or BATCH_CHARS[task], _text_len("source"))
    return run_batches(batches, one, workers, memo, tag, prime=primes(provider))


def backtranslate_rows(provider: Any, rows: Sequence[Dict[str, Any]], locale: str, *, system: Optional[str] = None,
                       batch_size: Optional[int] = None, max_tokens: int = 4096, workers: int = 1, memo: Optional[BatchMemo] = None,
                       max_chars: Optional[int] = None) -> Dict[str, str]:
    """Back-translate rows [{key, target}] into English; return key -> back translation."""
    sys_prompt = system_for("roundtrip", locale, system)

    def one(batch: List[Dict[str, Any]]) -> Dict[str, str]:
        got = _call_keyed(provider, sys_prompt, "roundtrip", {"locale": locale}, batch, "rows", "rows", "key",
                          lambda it: isinstance(it.get("back"), str), max_tokens)
        return {k: str(v["back"]) for k, v in got.items()}
    tag = ("roundtrip", getattr(provider, "model", "?"), sys_prompt, INSTRUCTIONS["roundtrip"], locale, max_tokens)
    batches = chunked_budget([{"key": r["key"], "target": r["target"]} for r in rows], batch_size or BATCH_ROWS["roundtrip"],
                             max_chars or BATCH_CHARS["roundtrip"], _text_len("target"))
    return run_batches(batches, one, workers, memo, tag, prime=primes(provider))


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
    odd = item.get("odd_words") or []
    if isinstance(odd, str):
        odd = re.split(r"[,;\n]", odd)
    words = [str(w).strip() for w in odd if isinstance(w, (str, int, float)) and str(w).strip()] if isinstance(odd, list) else []
    return {"score": score, "issue_type": it, "reason": str(item.get("reason") or ""), "suggested": str(item.get("suggested") or ""),
            "odd_words": words}


def everyday_check(vote: Dict[str, Any], target: str) -> Dict[str, Any]:
    """Keep the words of a normalized vote that the line really holds (in place), the score is left to everyday_rule.

    A word a model made up or took from another line never counts, and placeholders or tags are no words.
    """
    low = str(target).casefold()
    words: List[str] = []
    for w in vote.get("odd_words") or []:
        w = str(w).strip().strip("\"'.,!?")
        if w and any(ch.isalpha() for ch in w) and not any(ch in w for ch in "{}<>%[]") and w.casefold() in low and w not in words:
            words.append(w)
    vote["odd_words"] = words[:10]
    return vote


def everyday_rule(votes: Sequence[Dict[str, Any]]) -> bool:
    """The weight of the everyday word check on the votes of one tier for one line (in place).

    When at least EVERYDAY_MIN_JURORS jurors found a word that is not everyday, every score of the tier is capped at
    EVERYDAY_CAP and every reason names the words, so the line never passes and an agreeing J3 sends it to Pass 2.
    The words of a single juror stay in its vote as evidence. Returns True when the cap applied.
    """
    flaggers = [v for v in votes if v.get("odd_words")]
    if len(flaggers) < EVERYDAY_MIN_JURORS:
        return False
    words = list(dict.fromkeys(w for v in flaggers for w in v["odd_words"]))
    note = f"{len(flaggers)} jurors found words a native would not use every day ({', '.join(words)})"
    for v in votes:
        if v["score"] > EVERYDAY_CAP:
            v["score"] = EVERYDAY_CAP
            if v.get("issue_type") in (None, "none"):
                v["issue_type"] = "translationese"
        reason = str(v.get("reason") or "")
        v["reason"] = f"{reason.rstrip('. ')}. {note}" if reason.strip() else note
    return True


def score_entries(provider: Any, entries: Sequence[Dict[str, Any]], locale: str, *, tier: str = "J1",
                  system: Optional[str] = None, batch_size: Optional[int] = None, max_tokens: int = 4096,
                  extra: Optional[Dict[str, Any]] = None, workers: int = 1, memo: Optional[BatchMemo] = None,
                  max_chars: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    """Ask one jury member to score target-only entries [{key, target, ...}]; return key -> normalized vote."""
    sys_prompt = system_for("jury", locale, system)

    def one(batch: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        got = _call_keyed(provider, sys_prompt, "jury", {"locale": locale, "tier": tier, **(extra or {})}, batch, "entries", "votes", "key",
                          lambda it: normalize_vote(it) is not None, max_tokens)
        targets = {str(e.get("key")): str(e.get("target", "")) for e in batch}
        return {k: everyday_check(normalize_vote(v), targets.get(k, "")) for k, v in got.items()}  # type: ignore[arg-type]
    tag = ("jury", getattr(provider, "model", "?"), sys_prompt, INSTRUCTIONS["jury"], locale, tier, extra or {}, max_tokens)
    batches = chunked_budget(list(entries), batch_size or BATCH_ROWS["jury"], max_chars or BATCH_CHARS["jury"], _text_len("target"))
    return run_batches(batches, one, workers, memo, tag, prime=primes(provider))


def pairwise_choices(provider: Any, pairs: Sequence[Dict[str, Any]], locale: str, *, system: Optional[str] = None,
                     batch_size: Optional[int] = None, max_tokens: int = 2048, workers: int = 1, memo: Optional[BatchMemo] = None,
                     max_chars: Optional[int] = None) -> Dict[str, str]:
    """Ask one member which side of each pair [{id, a, b}] is more natural; return id -> 'a' | 'b'."""
    sys_prompt = system_for("pairwise", locale, system)

    def one(batch: List[Dict[str, Any]]) -> Dict[str, str]:
        got = _call_keyed(provider, sys_prompt, "pairwise", {"locale": locale}, batch, "pairs", "choices", "id",
                          lambda it: str(it.get("choice", "")).strip().lower() in ("a", "b"), max_tokens)
        return {k: str(v["choice"]).strip().lower() for k, v in got.items()}
    tag = ("pairwise", getattr(provider, "model", "?"), sys_prompt, INSTRUCTIONS["pairwise"], locale, max_tokens)
    batches = chunked_budget(list(pairs), batch_size or BATCH_ROWS["pairwise"], max_chars or BATCH_CHARS["pairwise"], _text_len("a", "b"))
    return run_batches(batches, one, workers, memo, tag, prime=primes(provider))


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
            return everyday_check(vote, str(payload.get("target", "")))
    raise L10nError(f"deliberate: model {getattr(provider, 'model', '?')} returned no valid vote for {payload.get('key')}")


def revote_many(provider: Any, payloads: Sequence[Dict[str, Any]], locale: str, *, system: Optional[str] = None,
                batch_size: Optional[int] = None, max_chars: Optional[int] = None, max_tokens: int = 4096, workers: int = 1,
                memo: Optional[BatchMemo] = None) -> Dict[str, Dict[str, Any]]:
    """The deliberation re-votes of one juror for many disputed lines, several lines per call; key -> normalized vote.

    Each payload is what revote() sends for one line. Until 3.1.0 every disputed line and juror was its own request,
    the 675 Pass 2 lines of the Lithuanian run of 2026-11-27 came after hundreds of them.
    """
    sys_prompt = system_for("jury", locale, system)
    targets = {str(pl["key"]): str(pl.get("target", "")) for pl in payloads}

    def one(batch: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        got = _call_keyed(provider, sys_prompt, "deliberate_many", {"locale": locale}, batch, "lines", "votes", "key",
                          lambda it: normalize_vote(it) is not None, max_tokens)
        return {k: everyday_check(normalize_vote(v), targets.get(k, "")) for k, v in got.items()}  # type: ignore[arg-type]
    tag = ("deliberate_many", getattr(provider, "model", "?"), sys_prompt, INSTRUCTIONS["deliberate_many"], locale, max_tokens)
    batches = chunked_budget(list(payloads), batch_size or BATCH_ROWS["deliberate"], max_chars or BATCH_CHARS["deliberate"],
                             lambda pl: json.dumps(pl, ensure_ascii=False))
    return run_batches(batches, one, workers, memo, tag, prime=primes(provider))


def pass2_candidates(provider: Any, rows: Sequence[Dict[str, Any]], locale: str, *, n: int = 3, system: Optional[str] = None,
                     batch_size: Optional[int] = None, max_tokens: int = 4096, workers: int = 1, memo: Optional[BatchMemo] = None,
                     max_chars: Optional[int] = None) -> Dict[str, List[str]]:
    """Ask the Pass 2 model for n candidates per row [{key, source, target, ...}]; returns key -> distinct non-empty candidates."""
    sys_prompt = system or DEFAULT_SYSTEM["pass1"].format(locale=locale)

    def ok(it: Dict[str, Any]) -> bool:
        c = it.get("candidates")
        return isinstance(c, list) and any(isinstance(x, str) and x.strip() for x in c)

    def one(batch: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        got = _call_keyed(provider, sys_prompt, "pass2", {"locale": locale, "n_candidates": n}, batch, "rows", "rows", "key", ok, max_tokens)
        return {k: ordered_unique(str(x) for x in v["candidates"] if isinstance(x, str) and x.strip())[:n] for k, v in got.items()}
    tag = ("pass2", getattr(provider, "model", "?"), sys_prompt, INSTRUCTIONS["pass2"], locale, n, max_tokens)
    batches = chunked_budget(list(rows), batch_size or BATCH_ROWS["pass2"], max_chars or BATCH_CHARS["pass2"], _text_len("source", "target"))
    return run_batches(batches, one, workers, memo, tag, prime=primes(provider))


def pick_candidates(provider: Any, items: Sequence[Dict[str, Any]], locale: str, *, system: Optional[str] = None,
                    batch_size: Optional[int] = None, max_tokens: int = 2048, workers: int = 1, memo: Optional[BatchMemo] = None,
                    max_chars: Optional[int] = None) -> Dict[str, str]:
    """Blind choice among candidates: items [{key, context..., candidates: [{id, text}]}] -> key -> chosen id."""
    sys_prompt = system_for("jury", locale, system)
    ids = {str(it["key"]): {str(c["id"]) for c in it["candidates"]} for it in items}

    def one(batch: List[Dict[str, Any]]) -> Dict[str, str]:
        got = _call_keyed(provider, sys_prompt, "pick", {"locale": locale}, batch, "items", "picks", "key",
                          lambda it: str(it.get("choice")) in ids.get(str(it.get("key")), set()), max_tokens)
        return {k: str(v["choice"]) for k, v in got.items()}
    tag = ("pick", getattr(provider, "model", "?"), sys_prompt, INSTRUCTIONS["pick"], locale, max_tokens)
    batches = chunked_budget(list(items), batch_size or BATCH_ROWS["pick"], max_chars or BATCH_CHARS["pick"],
                             lambda it: "".join(str(c.get("text", "")) for c in it.get("candidates", [])))
    return run_batches(batches, one, workers, memo, tag, prime=primes(provider))


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
    ap.add_argument("--batch", action="store_true",
                    help="Send the calls of Anthropic and Google models through their batch APIs at half the price. A reply comes "
                         "when its job ends, usually within an hour, at most a day. DeepSeek stays real time")


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
    batch = bool(getattr(args, "batch", False))
    router = Router(cfg, dry_run=bool(getattr(args, "dry_run", False)),
                    scenario=FakeScenario.load(Path(args.fake_scenario)) if getattr(args, "fake_scenario", None) else None,
                    budget_log=budget, batch=batch)
    router.require(roles)
    if batch and hasattr(args, "workers"):
        # a job takes the calls that wait together, so every batch of a step must be in flight at once
        args.workers = max(int(args.workers or 1), BATCH_WORKERS)
    return router
