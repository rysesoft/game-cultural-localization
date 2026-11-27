#!/usr/bin/env python3
"""Calibrate the jury members against the contrastive set (native vs robot lines).

For every member of the chosen tiers (each model is called once even when it sits in two tiers):
  primary    pairwise preference. The member sees (native, robot) blind, order seeded at random,
             and picks the more natural line. Accuracy = share of native picks. Phase A gate >= 0.85.
  secondary  absolute 1 to 5 scores. native mean should be above 4.5, robot mean below 3.
  observed   score distribution of the unknown (raw strong-model) lines.
Agreement: quadratic weighted Cohen's kappa between members of different families in one
tier (inter_family) and between models of the same family across tiers (intra_family).

The critic prompt (prompts/critic.<locale>.md) carries a seeded warm-up sample from the pack
and contrastive few-shots drawn from pairs held out of the evaluation. --compare-warmup runs
the whole evaluation with and without warm-up in one command.

Usage:
  python eval_critic.py ../langpack/tr-TR/contrastive.json --locale tr-TR [--tiers J1] [--compare-warmup] [--dry-run]

Exit codes: 0 every member reached the pairwise gate, 1 at least one member is below it,
2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, apply_config, emit_report, load_json_data,
    normalize_locale, resolve_input, run_main, __version__,
)
from build_context_map import ContextPack, load_context  # noqa: E402
from build_language_pack import LANGPACK_DIR  # noqa: E402
from llm_tasks import BatchMemo, add_model_args, default_budget_path, make_router, pairwise_choices, score_entries  # noqa: E402
from prompt_templates import render_contrastive, render_prompt  # noqa: E402
from warmup_loader import REGISTERS, load_warmup, render_warmup  # noqa: E402

TOOL = "eval_critic"
PAIRWISE_MIN = 0.85
NATIVE_MEAN_MIN = 4.5
ROBOT_MEAN_MAX = 3.0
DEFAULT_SEED = 1234
DEFAULT_SHOTS = 6


def weighted_kappa(a: Sequence[int], b: Sequence[int], k: int = 5) -> Optional[float]:
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
    if den == 0:
        return 1.0 if num == 0 else 0.0
    return round(1.0 - num / den, 4)


def load_pairs(path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Read contrastive.json and validate its pairs."""
    data = load_json_data(path)
    if not isinstance(data, dict) or not isinstance(data.get("pairs"), list):
        raise L10nError(f"{path}: contrastive set must be an object with a 'pairs' list")
    pairs = []
    for i, p in enumerate(data["pairs"]):
        if not isinstance(p, dict) or not all(isinstance(p.get(k), str) and p.get(k) for k in ("key", "native", "robot")):
            raise L10nError(f"{path}: pairs[{i}] needs non-empty key, native and robot strings")
        pairs.append(p)
    if not pairs:
        raise L10nError(f"{path}: the contrastive set has no pairs")
    return data, sorted(pairs, key=lambda p: p["key"])


def split_shots(pairs: Sequence[Dict[str, Any]], shots: int, limit: int, seed: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Hold out `shots` pairs for the few-shot block, evaluate on (at most `limit` of) the rest."""
    rng = random.Random(seed)
    order = list(range(len(pairs)))
    rng.shuffle(order)
    shots = min(shots, max(0, len(pairs) - 1))
    held = sorted(order[:shots])
    rest = sorted(order[shots:])
    if limit and limit < len(rest):
        rest = sorted(rng.sample(rest, limit))
    return [pairs[i] for i in held], [pairs[i] for i in rest]


def build_items(pairs: Sequence[Dict[str, Any]], seed: int) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]], Dict[str, Tuple[str, str]]]:
    """Pairwise items (seeded side order), their native side, absolute-score entries (seeded order) and entry -> (kind, pair key)."""
    rng = random.Random(seed)
    pw: List[Dict[str, Any]] = []
    native_side: Dict[str, str] = {}
    entries: List[Dict[str, Any]] = []
    meta: Dict[str, Tuple[str, str]] = {}
    for p in pairs:
        if rng.random() < 0.5:
            pw.append({"id": p["key"], "a": p["native"], "b": p["robot"]})
            native_side[p["key"]] = "a"
        else:
            pw.append({"id": p["key"], "a": p["robot"], "b": p["native"]})
            native_side[p["key"]] = "b"
        lines = [("native", p["native"]), ("robot", p["robot"])]
        for model, text in sorted((p.get("unknown") or {}).items()):
            if isinstance(text, str) and text.strip():
                lines.append((f"unknown:{model}", text))
        for kind, text in lines:
            eid = f"e{len(entries):05d}"
            entries.append({"key": eid, "target": text, "register": p.get("register", "")})
            meta[eid] = (kind, p["key"])
    rng.shuffle(entries)
    return pw, native_side, entries, meta


def _mean(xs: Sequence[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 4) if xs else None


def evaluate(router: Any, locale: str, tiers: Sequence[str], pairs: Sequence[Dict[str, Any]], shots_pairs: Sequence[Dict[str, Any]],
             *, warmup: bool, pack_dir: Optional[Path], seed: int, warmup_count: int, pairwise_min: float,
             langpack_version: Optional[str], workers: int = 1, store: Optional[Path] = None,
             context: Optional[ContextPack] = None) -> Dict[str, Any]:
    """Run the calibration once (with or without warm-up) and return the B3.6 report.

    With workers > 1 every distinct model is calibrated in its own thread and sends up to `workers`
    batches at once. Results are keyed, so the report does not depend on the worker count.
    With a store file every finished model is saved under a signature of model, tier, prompt and items.
    A failing model no longer throws away the others, and a rerun only calls the models that are missing.
    """
    regs = sorted({p.get("register") for p in pairs if p.get("register") in REGISTERS}) or list(REGISTERS)
    warm_text = ""
    if warmup and pack_dir is not None and ((pack_dir / "warmup.jsonl").is_file() or (pack_dir / "local" / "warmup.jsonl").is_file()):
        warm_text = render_warmup(load_warmup(pack_dir, regs, warmup_count, seed))
    system = render_prompt("critic", locale, warmup=warm_text, contrastive=render_contrastive(shots_pairs, count=len(shots_pairs), seed=seed))
    pw, native_side, entries, meta = build_items(pairs, seed)
    context_lines = 0
    if context is not None and context.text:  # jurors read the map and the neutral line fields, never the locale appendix
        system = context.system(system)
        context_lines = context.enrich(pw, "id")
        for e in entries:
            ctx = context.line(meta[e["key"]][1])
            if ctx:
                e["context"] = ctx
    unique: Dict[str, Tuple[str, Any]] = {}
    for tier in tiers:
        for m in router.jury(tier):
            unique.setdefault(m.model, (tier, m))  # a model in two tiers (deepseek-v4-pro in J2 and J3) is called once

    stored: Dict[str, Any] = load_json_data(store) if store is not None and Path(store).is_file() else {}
    lock = threading.Lock()
    # every finished batch is kept too, so a model stopped halfway (rate limit, provider queue) resumes where it stopped
    memo = BatchMemo(Path(store).with_name(Path(store).stem + ".batches.json")) if store is not None else None

    def signature(model: str, tier: str) -> str:
        blob = json.dumps({"model": model, "tier": tier, "system": system, "pairs": pw, "entries": entries}, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def calibrate(item: Tuple[str, Tuple[str, Any]]) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
        model, (tier, m) = item
        sig = signature(model, tier)
        if sig in stored:
            return model, stored[sig], None
        try:
            choices = pairwise_choices(m.provider, pw, locale, system=system, workers=workers, memo=memo)
            votes = score_entries(m.provider, entries, locale, tier=tier, system=system, workers=workers, memo=memo)
        except Exception as exc:  # noqa: BLE001  one failing model must not throw away the finished ones
            return model, None, f"{type(exc).__name__}: {exc}"
        result = {"choices": choices, "scores": {k: v["score"] for k, v in votes.items()}}
        if store is not None:
            with lock:
                stored[sig] = result
                tmp = Path(store).with_suffix(".tmp")
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(json.dumps(stored, ensure_ascii=False) + "\n", encoding="utf-8")
                tmp.replace(store)
        return model, result, None

    todo = list(unique.items())
    if int(workers) > 1 and len(todo) > 1:
        with ThreadPoolExecutor(max_workers=len(todo)) as ex:
            outcomes = list(ex.map(calibrate, todo))
    else:
        outcomes = [calibrate(it) for it in todo]
    failed = [(model, err) for model, _res, err in outcomes if err]
    if failed:
        hint = (f" Finished models are kept in {Path(store).name}, run the same command again to resume." if store is not None
                else " Pass --cache FILE to keep finished models for a rerun.")
        raise L10nError("calibration failed for " + ", ".join(m for m, _ in failed) + f" ({failed[0][1]})." + hint)
    cache: Dict[str, Dict[str, Any]] = {model: res for model, res, _err in outcomes if res is not None}
    members: List[Dict[str, Any]] = []
    for tier in tiers:
        for m in router.jury(tier):
            res = cache[m.model]
            correct = sum(1 for pid, side in native_side.items() if res["choices"][pid] == side)
            by_kind: Dict[str, List[int]] = {"native": [], "robot": [], "unknown": []}
            for eid, (kind, _key) in meta.items():
                by_kind["unknown" if kind.startswith("unknown:") else kind].append(res["scores"][eid])
            members.append({"tier": tier, "family": m.family, "model": m.model, "alias": m.alias,
                            "pairwise_accuracy": round(correct / len(native_side), 4), "native_mean": _mean(by_kind["native"]),
                            "robot_mean": _mean(by_kind["robot"]), "unknown_mean": _mean(by_kind["unknown"]), "n": len(native_side),
                            "unknown_distribution": {str(s): by_kind["unknown"].count(s) for s in range(1, 6)} if by_kind["unknown"] else {}})
    keys = sorted(meta)
    inter: List[float] = []
    intra: List[float] = []
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
    gate_passed = all(m["pairwise_accuracy"] >= pairwise_min for m in members)
    secondary = all((m["native_mean"] or 0) > NATIVE_MEAN_MIN and (m["robot_mean"] if m["robot_mean"] is not None else 5) < ROBOT_MEAN_MAX for m in members)
    return {"locale": locale, "langpack_version": langpack_version, "warmup": bool(warm_text), "warmup_lines": sum(1 for l in warm_text.splitlines() if l.startswith("- ")),
            "shots": len(shots_pairs), "seed": seed, "members": members,
            "context_map": context.source if context is not None and context.text else None, "context_lines": context_lines,
            "inter_family_kappa": _mean(inter), "intra_family_kappa": _mean(intra),
            "gate": {"pairwise_min": pairwise_min, "passed": gate_passed},
            "secondary": {"native_mean_min": NATIVE_MEAN_MIN, "robot_mean_max": ROBOT_MEAN_MAX, "passed": secondary}}


def _member_lines(rep: Dict[str, Any]) -> List[str]:
    out = []
    for m in rep["members"]:
        mark = "ok " if m["pairwise_accuracy"] >= rep["gate"]["pairwise_min"] else "LOW"
        out.append(f"  {mark} {m['tier']} {m['model']:<20} pairwise {m['pairwise_accuracy']:.2f}  native {m['native_mean']}  "
                   f"robot {m['robot_mean']}  unknown {m['unknown_mean']}  n {m['n']}")
    out.append(f"  kappa inter-family {rep['inter_family_kappa']}, intra-family {rep['intra_family_kappa']}")
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Calibrate jury members on the contrastive set (pairwise gate 0.85, absolute means, kappa)")
    add_input_argument(ap, "contrastive.json of the locale")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--tiers", default="J1,J2,J3", help="Comma separated jury tiers to evaluate (default J1,J2,J3)")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs, for the warm-up sample (default: the skill's langpack/)")
    ap.add_argument("--no-warmup", action="store_true", help="Evaluate without the warm-up block")
    ap.add_argument("--compare-warmup", action="store_true", help="Run with and without warm-up and report both plus the difference")
    ap.add_argument("--warmup-count", type=int, default=40, help="Warm-up lines in the prompt (default 40)")
    ap.add_argument("--shots", type=int, default=DEFAULT_SHOTS, help=f"Contrastive few-shot pairs held out of the evaluation (default {DEFAULT_SHOTS})")
    ap.add_argument("--limit", type=int, default=0, help="Evaluate a seeded subset of N pairs (default: all)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Seed for side order, subsets and warm-up (default {DEFAULT_SEED})")
    ap.add_argument("--pairwise-min", type=float, default=PAIRWISE_MIN, help=f"Pairwise accuracy gate (default {PAIRWISE_MIN})")
    ap.add_argument("--update-trust-card", action="store_true", help="Store the result in langpack/<locale>/trust_card.json under 'calibration'")
    ap.add_argument("--workers", type=int, default=4, help="Batches in flight per model, models run in parallel when above 1 (default 4, 1 = one call at a time)")
    ap.add_argument("--cache", default=None, help="JSON file that keeps every finished model; a rerun with the same pairs, seed and prompt only calls the missing models")
    ap.add_argument("--context-map", default=None, help="CONTEXT_MAP.md of the game, its line_notes.json next to it gives every pair its context")
    add_model_args(ap)
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    apply_config(args, {"context_map": None})
    locale, _v = normalize_locale(args.locale)
    tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]
    for t in tiers:
        if t not in ("J1", "J2", "J3"):
            raise L10nError(f"unknown tier '{t}'; known: J1, J2, J3")
    data, pairs = load_pairs(Path(args.input))
    pack_dir = (Path(args.langpack_dir) if args.langpack_dir else LANGPACK_DIR) / locale
    manifest = pack_dir / "manifest.json"
    version = load_json_data(manifest).get("langpack_version") if manifest.is_file() else None
    shots, evald = split_shots(pairs, args.shots, args.limit, args.seed)
    router = make_router(args, tiers, default_budget_path(Path(args.input)))
    if args.workers < 1:
        raise L10nError("--workers must be 1 or more")
    kw = {"pack_dir": pack_dir, "seed": args.seed, "warmup_count": args.warmup_count, "pairwise_min": args.pairwise_min, "langpack_version": version,
          "workers": args.workers, "store": Path(args.cache) if args.cache else None,
          "context": load_context(Path(args.context_map), locale) if args.context_map else None}
    if args.compare_warmup:
        with_w = evaluate(router, locale, tiers, evald, shots, warmup=True, **kw)
        without_w = evaluate(router, locale, tiers, evald, shots, warmup=False, **kw)
        delta = {f"{m['tier']}:{m['model']}": round(m["pairwise_accuracy"] - n["pairwise_accuracy"], 4)
                 for m, n in zip(with_w["members"], without_w["members"])}
        report: Dict[str, Any] = {"locale": locale, "langpack_version": version, "with_warmup": with_w, "without_warmup": without_w,
                                  "delta_pairwise": delta, "gate": with_w["gate"]}
        lines = [f"Critic calibration {locale}: {len(evald)} pairs, {len(shots)} held out as few-shots, warm-up compared",
                 "  with warm-up" if with_w["warmup"] else "  with warm-up (pack has no warm-up file, same as without)"]
        lines += _member_lines(with_w) + ["  without warm-up"] + _member_lines(without_w)
        lines.append("  pairwise delta (with - without) " + ", ".join(f"{k} {v:+.2f}" for k, v in delta.items()))
        gate = with_w["gate"]
    else:
        report = evaluate(router, locale, tiers, evald, shots, warmup=not args.no_warmup, **kw)
        lines = [f"Critic calibration {locale}: {len(evald)} pairs, {len(shots)} held out as few-shots, warm-up {'on' if report['warmup'] else 'off'}"]
        lines += _member_lines(report)
        gate = report["gate"]
    if args.update_trust_card:
        card = pack_dir / "trust_card.json"
        if not card.is_file():
            raise L10nError(f"{card} not found; build the pack first")
        trust = load_json_data(card)
        main_rep = report.get("with_warmup", report)
        trust["calibration"] = {"gate": main_rep["gate"], "secondary": main_rep["secondary"], "pairs": len(evald),
                                "members": [{k: m[k] for k in ("tier", "model", "pairwise_accuracy", "native_mean", "robot_mean")} for m in main_rep["members"]],
                                "inter_family_kappa": main_rep["inter_family_kappa"], "intra_family_kappa": main_rep["intra_family_kappa"],
                                "langpack_version": version, "source": Path(args.input).name,  # file name only, no local path in a shipped card
                                "context_map": main_rep.get("context_map"), "context_lines": main_rep.get("context_lines", 0)}
        card.write_text(json.dumps(trust, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    exit_code = EXIT_OK if gate["passed"] else EXIT_FINDINGS
    main_rep = report.get("with_warmup", report)
    if main_rep.get("context_map"):
        lines.append(f"  context map {main_rep['context_map']}, {main_rep['context_lines']} of {len(evald)} pairs with line context")
    lines.append(f"  Gate pairwise >= {gate['pairwise_min']} {'PASSED' if gate['passed'] else 'FAILED'}")
    for n in router.notes:
        lines.append(f"  NOTE: {n}")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, **report, "notes": router.notes, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
