"""Contrastive critic calibration metrics, blind evaluation orchestration and kappa computation."""

import hashlib
import json
import random
import re
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from gcl.application.tasks.concrete_tasks import pairwise_choices, score_entries
from gcl.application.tasks.prompts import INSTRUCTIONS
from gcl.domain.errors import L10nError
from gcl.ports.storage import MemoRepository

__layer__ = "application"
__pattern__ = "Application Service and Strategy"
__owns__ = "weighted kappa, contrastive pair splitting, blind seat calibration and summary gates"

PAIRWISE_MIN = 0.85
NATIVE_MEAN_MIN = 4.5
ROBOT_MEAN_MAX = 3.0
DEFAULT_SEED = 1234
DEFAULT_SHOTS = 6
_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")
SHORT_WORDS = 3


@dataclass(frozen=True, slots=True)
class CriticEvalOptions:
    """Parameter object encapsulating critic calibration inputs and injected factories."""

    pairs: Sequence[dict[str, Any]]
    shots_pairs: Sequence[dict[str, Any]]
    warmup: bool
    seed: int
    pairwise_min: float
    langpack_version: str | None
    system_prompt: str
    warmup_lines: int = 0
    workers: int = 1
    store: Path | None = None
    memo: MemoRepository | None = None
    context: Any = None
    include_unknown: bool = False
    pairwise_fn: Callable[..., Any] | None = None
    score_fn: Callable[..., Any] | None = None


def weighted_kappa(a: Sequence[int], b: Sequence[int], k: int = 5) -> float | None:
    """Quadratic weighted Cohen's kappa for two raters on a 1..k scale (None without items)."""
    n = len(a)
    if n == 0 or n != len(b):
        return None
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[x - 1][y - 1] += 1
    ha = [sum(obs[i][j] for j in range(k)) for i in range(k)]
    hb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / float((k - 1) ** 2)
            num += w * obs[i][j]
            den += w * ha[i] * hb[j] / n
    return (1.0 if num == 0 else 0.0) if den == 0 else round(1.0 - num / den, 4)


def mixed_robot(pair: dict[str, Any]) -> bool:
    """True when robot text kept a quarter or more English source words verbatim."""
    src = {w.lower() for w in _LATIN_WORD.findall(str(pair.get("en", "")))}
    native = {w.lower() for w in _LATIN_WORD.findall(pair["native"])}
    robot = [w.lower() for w in _LATIN_WORD.findall(pair["robot"])]
    kept = [w for w in robot if w in src and w not in native]
    return len(kept) >= 3 and len(kept) >= 0.25 * max(1, len(robot))


def is_short(pair: dict[str, Any]) -> bool:
    return len(str(pair.get("en", "")).split()) <= SHORT_WORDS


def split_shots(pairs: Sequence[dict[str, Any]], shots: int, limit: int, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Hold out shots pairs for few-shot block and sample up to limit evaluation pairs."""
    rng = random.Random(seed)
    order = list(range(len(pairs)))
    rng.shuffle(order)
    shots = min(shots, max(0, len(pairs) - 1))
    held = sorted(order[:shots])
    rest = sorted(order[shots:])
    if limit and limit < len(rest):
        rest = sorted(rng.sample(rest, limit))
    return [pairs[i] for i in held], [pairs[i] for i in rest]


def build_items(
    pairs: Sequence[dict[str, Any]], seed: int, *, include_unknown: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, str], list[dict[str, Any]], dict[str, tuple[str, str]]]:
    """Build pairwise comparisons and shuffled absolute-score entries."""
    rng = random.Random(seed)
    pw: list[dict[str, Any]] = []
    native_side: dict[str, str] = {}
    entries: list[dict[str, Any]] = []
    meta: dict[str, tuple[str, str]] = {}
    for p in pairs:
        if rng.random() < 0.5:
            pw.append({"id": p["key"], "a": p["native"], "b": p["robot"]})
            native_side[p["key"]] = "a"
        else:
            pw.append({"id": p["key"], "a": p["robot"], "b": p["native"]})
            native_side[p["key"]] = "b"
        lines = [("native", p["native"]), ("robot", p["robot"])]
        if include_unknown:
            for model, text in sorted((p.get("unknown") or {}).items()):
                if isinstance(text, str) and text.strip():
                    lines.append((f"unknown:{model}", text))
        for kind, text in lines:
            eid = f"e{len(entries):05d}"
            entries.append({"key": eid, "target": text, "register": p.get("register", "")})
            meta[eid] = (kind, p["key"])
    rng.shuffle(entries)
    return pw, native_side, entries, meta


def _mean(xs: Sequence[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def _seat_signature(model: str, tier: str, system: str, pw: Sequence[dict[str, Any]], entries: Sequence[dict[str, Any]]) -> str:
    blob = json.dumps(
        {"model": model, "tier": tier, "system": system, "pairs": list(pw), "entries": list(entries),
         "instructions": [INSTRUCTIONS["pairwise"], INSTRUCTIONS["jury"]]},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_stored_map(store: Path | None) -> dict[str, Any]:
    if store is None or not Path(store).is_file():
        return {}
    data = json.loads(Path(store).read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {}


def _calibrate_models(
    router: Any, locale: str, todo: Sequence[tuple[str, tuple[str, Any]]],
    pw: Sequence[dict[str, Any]], entries: Sequence[dict[str, Any]], opts: CriticEvalOptions,
) -> dict[str, dict[str, Any]]:
    stored = _load_stored_map(opts.store)
    lock = threading.Lock()
    memo = opts.memo

    def one(item: tuple[str, tuple[str, Any]]) -> tuple[str, dict[str, Any] | None, str | None]:
        model, (tier, m) = item
        sig = _seat_signature(model, tier, opts.system_prompt, pw, entries)
        if sig in stored:
            return model, stored[sig], None
        try:
            pw_provider = router.for_model(m.alias, tier, task_role="pairwise") if hasattr(router, "for_model") else m.provider
        except TypeError:
            pw_provider = m.provider
        try:
            choices = (opts.pairwise_fn or pairwise_choices)(pw_provider, pw, locale, system=opts.system_prompt, workers=opts.workers, memo=memo)
            votes = (opts.score_fn or score_entries)(m.provider, entries, locale, tier=tier, system=opts.system_prompt, workers=opts.workers, memo=memo)
        except Exception as exc:  # noqa: BLE001
            return model, None, f"{type(exc).__name__}: {exc}"
        result = {"choices": choices, "scores": {k: v["score"] for k, v in votes.items()}}
        if opts.store is not None:
            with lock:
                stored[sig] = result
                tmp = Path(opts.store).with_suffix(".tmp")
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(json.dumps(stored, ensure_ascii=False) + "\n", encoding="utf-8")
                tmp.replace(opts.store)
        return model, result, None

    if int(opts.workers) > 1 and len(todo) > 1:
        with ThreadPoolExecutor(max_workers=len(todo)) as ex:
            outcomes = list(ex.map(one, todo))
    else:
        outcomes = [one(it) for it in todo]
    failed = [(m, err) for m, _r, err in outcomes if err]
    if failed:
        hint = (f" Finished models are kept in {Path(opts.store).name}, run the same command again to resume."
                if opts.store is not None else " Pass --cache FILE to keep finished models for a rerun.")
        raise L10nError("calibration failed for " + ", ".join(m for m, _ in failed) + f" ({failed[0][1]})." + hint)
    return {m: res for m, res, _err in outcomes if res is not None}


def _member_metrics(
    tiers: Sequence[str], router: Any, cache: dict[str, dict[str, Any]],
    native_side: dict[str, str], meta: dict[str, tuple[str, str]], pairs: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    short_ids = [p["key"] for p in pairs if is_short(p)]
    long_ids = [p["key"] for p in pairs if not is_short(p)]
    members: list[dict[str, Any]] = []
    for tier in tiers:
        for m in router.jury(tier):
            res = cache[m.model]
            hit = {pid: res["choices"][pid] == side for pid, side in native_side.items()}
            by_kind: dict[str, list[int]] = {"native": [], "robot": [], "unknown": []}
            for eid, (kind, _key) in meta.items():
                by_kind["unknown" if kind.startswith("unknown:") else kind].append(res["scores"][eid])
            members.append({
                "tier": tier, "family": m.family, "model": m.model, "alias": m.alias,
                "pairwise_accuracy": round(sum(hit.values()) / len(native_side), 4),
                "pairwise_short": round(sum(hit[k] for k in short_ids) / len(short_ids), 4) if short_ids else None,
                "pairwise_long": round(sum(hit[k] for k in long_ids) / len(long_ids), 4) if long_ids else None,
                "native_mean": _mean(by_kind["native"]), "robot_mean": _mean(by_kind["robot"]),
                "unknown_mean": _mean(by_kind["unknown"]), "n": len(native_side),
                "unknown_distribution": {str(s): by_kind["unknown"].count(s) for s in range(1, 6)} if by_kind["unknown"] else {},
            })
    return members


def _kappa_summary(members: Sequence[dict[str, Any]], cache: dict[str, dict[str, Any]], keys: Sequence[str]) -> tuple[float | None, float | None]:
    inter: list[float] = []
    intra: list[float] = []
    for x, y in combinations(members, 2):
        if x["model"] == y["model"]:
            continue
        k = weighted_kappa([cache[x["model"]]["scores"][e] for e in keys], [cache[y["model"]]["scores"][e] for e in keys])
        if k is None:
            continue
        if x["family"] != y["family"] and x["tier"] == y["tier"]:
            inter.append(k)
        elif x["family"] == y["family"]:
            intra.append(k)
    return _mean(inter), _mean(intra)


def run_critic_evaluation(router: Any, locale: str, tiers: Sequence[str], opts: CriticEvalOptions) -> dict[str, Any]:
    """Run blind calibration across distinct jury models and compute agreement gates."""
    pw, native_side, entries, meta = build_items(opts.pairs, opts.seed, include_unknown=opts.include_unknown)
    context_lines = 0
    ctx = opts.context
    if ctx is not None and ctx.text:
        context_lines = ctx.enrich(pw, "id")
        for e in entries:
            cfields = ctx.line(meta[e["key"]][1])
            if cfields:
                e["context"] = cfields
    unique: dict[str, tuple[str, Any]] = {}
    for tier in tiers:
        for m in router.jury(tier):
            unique.setdefault(m.model, (tier, m))
    cache = _calibrate_models(router, locale, list(unique.items()), pw, entries, opts)
    members = _member_metrics(tiers, router, cache, native_side, meta, opts.pairs)
    inter_k, intra_k = _kappa_summary(members, cache, sorted(meta))
    gate_passed = all(m["pairwise_accuracy"] >= opts.pairwise_min for m in members)
    secondary = all(
        (m["native_mean"] or 0) > NATIVE_MEAN_MIN and (m["robot_mean"] if m["robot_mean"] is not None else 5) < ROBOT_MEAN_MAX
        for m in members
    )
    return {
        "locale": locale, "langpack_version": opts.langpack_version, "warmup": opts.warmup and opts.warmup_lines > 0,
        "warmup_lines": opts.warmup_lines, "shots": len(opts.shots_pairs), "seed": opts.seed, "members": members,
        "context_map": ctx.source if ctx is not None and ctx.text else None, "context_lines": context_lines,
        "inter_family_kappa": inter_k, "intra_family_kappa": intra_k,
        "gate": {"pairwise_min": opts.pairwise_min, "passed": gate_passed},
        "secondary": {"native_mean_min": NATIVE_MEAN_MIN, "robot_mean_max": ROBOT_MEAN_MAX, "passed": secondary},
    }
