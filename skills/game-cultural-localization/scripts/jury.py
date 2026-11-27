#!/usr/bin/env python3
"""Tiered mixed-family jury over a blind slice (J1 -> J2 -> J3), with the agreement rule of the brief (A4).

Every tier has three members from three model families (anthropic, google, deepseek). The
members read only the blind slice (key, context, target), never the source.

Agreement on the three scores of one tier
  pass      all scores >= pass_min (4) and max - min <= max_spread (1). Line score = the minimum
            (5 -> status pass, 4 -> status rewrite_light). Done.
  escalate  any score <= 3, or a spread of 2 or more -> next tier
  critical  any score <= critical_max (2) -> straight to J3, whatever the tier
At J3 an agreeing tier (spread <= 1) settles the line with its minimum score (3 -> rewrite,
<= 2 -> critical). A J3 disagreement goes to the deliberation round (deliberate.py) when it is
available, otherwise the line is 'unresolved' and reaches the developer with three rationales.

Budget caps (providers.config.json budget_caps): when more than 30 % of the batch would go to J2,
or more than 10 % to J3, the run stops and writes a report. The problem then lies in Pass 1 or
in the prompt, not in single lines.

Evidence per line: ban list hits (lqa_linter rules on the target), translation memory neighbours
(when a TM is attached) and, for lines that reach J3, the back-translation signal (needs the
source table, which only the harness reads).

Usage:
  python jury.py blind_tr-TR_01.json --locale tr-TR [--source-table pass1_tr-TR_01.json] [--no-deliberation] [--dry-run]

Exit codes: 0 every line settled, 1 the budget cap stopped the run or a line is unresolved,
2 usage or input error (source column in the slice, same family twice in a tier, missing key).
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, Row, add_common_args, add_input_argument, emit_report, load_json_data, load_table,
    apply_config, normalize_locale, resolve_input, run_main, __version__,
)
import lqa_linter  # noqa: E402
from build_context_map import load_context  # noqa: E402
from build_language_pack import LANGPACK_DIR, infer_register  # noqa: E402
from llm_tasks import BatchMemo, add_model_args, default_budget_path, make_router, score_entries  # noqa: E402
from prompt_templates import render_contrastive, render_prompt  # noqa: E402
from roundtrip_check import load_threshold, roundtrip_evidence  # noqa: E402
from warmup_loader import REGISTERS, load_warmup, render_warmup  # noqa: E402

TOOL = "jury"
TIERS = ("J1", "J2", "J3")
SOURCE_COLUMNS = ("en", "source", "src", "english")
CONTEXT_FIELDS = ("register", "category", "speaker", "archetype", "context")
STATUSES = ("pass", "rewrite_light", "rewrite", "critical", "unresolved")


# --------------------------------------------------------------------------- #
# Agreement rule (A4)
# --------------------------------------------------------------------------- #

def classify(scores: Sequence[int], agreement: Dict[str, int]) -> str:
    """'pass', 'critical' or 'escalate' for the three scores of one tier."""
    lo, hi = min(scores), max(scores)
    if lo <= agreement["critical_max"]:
        return "critical"
    if lo >= agreement["pass_min"] and hi - lo <= agreement["max_spread"]:
        return "pass"
    return "escalate"


def agrees(scores: Sequence[int], agreement: Dict[str, int]) -> bool:
    """True when the spread is within max_spread (used to settle a line at J3)."""
    return max(scores) - min(scores) <= agreement["max_spread"]


def status_for(score: int) -> str:
    """Line status from the settled score."""
    if score >= 5:
        return "pass"
    if score == 4:
        return "rewrite_light"
    if score == 3:
        return "rewrite"
    return "critical"


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #

def load_blind_slice(path: Path) -> Tuple[List[Dict[str, Any]], str]:
    """Entries {key, target, register, context...} of a blind slice; refuses any source column. Returns (entries, source_file)."""
    entries: List[Dict[str, Any]] = []
    source_file = path.name
    if path.suffix.lower() == ".json":
        data = load_json_data(path)
        raw = data.get("entries") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            raise L10nError(f"{path}: expected a blind slice with an 'entries' list")
        if isinstance(data, dict) and data.get("source_file"):
            source_file = str(data["source_file"])
        for i, e in enumerate(raw):
            if not isinstance(e, dict) or "key" not in e or not isinstance(e.get("target"), str):
                raise L10nError(f"{path}: entries[{i}] needs 'key' and a 'target' string")
            entries.append(dict(e))
    else:
        for r in load_table(path, "en", "target", "key", target_only=True):
            entries.append({"key": r.key, "target": r.dst, **{k: r.meta[k] for k in r.meta if k not in ("key", "target")}})
    leaked = sorted({k for e in entries for k in e if k.lower() in SOURCE_COLUMNS})
    if leaked:
        raise L10nError(f"{path}: the slice carries source column(s) {leaked}; the jury reads target-only blind slices (make_blind_slice.py)")
    seen = set()
    for e in entries:
        e["key"] = str(e["key"])
        if e["key"] in seen:
            raise L10nError(f"{path}: duplicate key '{e['key']}'")
        seen.add(e["key"])
        if e.get("register") not in REGISTERS:
            e["register"] = infer_register(str(e.get("category", "") or ""), e["target"], "game")
    if not entries:
        raise L10nError(f"{path}: the blind slice is empty")
    return entries, source_file


def juror_view(entry: Dict[str, Any]) -> Dict[str, Any]:
    """What a juror may see: key, target and context fields only."""
    view = {"key": entry["key"], "target": entry["target"]}
    for k in CONTEXT_FIELDS:
        if entry.get(k) not in (None, ""):
            view[k] = entry[k]
    return view


def ban_hits(entries: Sequence[Dict[str, Any]], locale: str) -> Dict[str, List[Dict[str, str]]]:
    """Locale rule hits (lqa_linter ban list) per key, target only."""
    rules = lqa_linter.load_rules(locale)
    ids = {r.id for r in rules}
    rows = [Row(e["key"], "", e["target"], {"category": e.get("category") or e.get("register", "")}) for e in entries]
    out: Dict[str, List[Dict[str, str]]] = {e["key"]: [] for e in entries}
    for f in lqa_linter.lint_rows(rows, rules, lqa_linter.LintOptions(locale=locale, check_untranslated=False)):
        if f.code in ids:
            out[f.key].append({"rule": f.code, "severity": f.severity, "message": f.message})
    return out


def build_system_prompt(locale: str, entries: Sequence[Dict[str, Any]], pack_dir: Optional[Path], *, warmup: bool, warmup_count: int,
                        shots: int, seed: int) -> Tuple[str, Dict[str, Any]]:
    """Critic prompt with the pack's seeded warm-up and contrastive few-shots. Returns (prompt, info)."""
    warm, contrast = "", ""
    info: Dict[str, Any] = {"warmup_lines": 0, "shots": 0, "langpack_version": None}
    if pack_dir is not None and pack_dir.is_dir():
        regs = sorted({e["register"] for e in entries}) or list(REGISTERS)
        if warmup and ((pack_dir / "warmup.jsonl").is_file() or (pack_dir / "local" / "warmup.jsonl").is_file()):
            sample = load_warmup(pack_dir, regs, warmup_count, seed)
            warm = render_warmup(sample)
            info["warmup_lines"] = len(sample)
        cfile = pack_dir / "contrastive.json"
        if shots and cfile.is_file():
            data = load_json_data(cfile)
            pairs = data.get("pairs", []) if isinstance(data, dict) else []
            contrast = render_contrastive(pairs, count=shots, seed=seed)
            info["shots"] = contrast.count("✓")
        mf = pack_dir / "manifest.json"
        if mf.is_file():
            info["langpack_version"] = load_json_data(mf).get("langpack_version")
    return render_prompt("critic", locale, warmup=warm, contrastive=contrast), info


# --------------------------------------------------------------------------- #
# Jury run
# --------------------------------------------------------------------------- #
Deliberator = Callable[[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]], Optional[Dict[str, Any]]]


@dataclass
class EscalationTally:
    """Lines the jury judged so far in a run and how many of them went on to J2 and J3.

    The budget caps read the whole run, not one batch. Measured per batch, one critical line in a short last
    batch of 3 lines was 33 % and stopped a run of 53 lines where it was 2 %, and 6 critical lines in one batch
    of 50 stopped a whole game before its other batches started.
    """
    lines: int = 0
    to_j2: int = 0
    to_j3: int = 0


def _tier_votes(router: Any, tier: str, entries: Sequence[Dict[str, Any]], locale: str, system: str, batch_size: int,
                workers: int = 1, memo: Any = None) -> Dict[str, List[Dict[str, Any]]]:
    """Votes of the three members of one tier. With workers > 1 the members run at the same time and each
    sends up to `workers` batches at once. Votes are appended in member order, the result does not change."""
    members = router.jury(tier)
    fams = [m.family for m in members]
    if len(set(fams)) != len(fams):
        raise L10nError(f"jury {tier} has two members from the same family ({', '.join(fams)})")
    view = [juror_view(e) for e in entries]
    out: Dict[str, List[Dict[str, Any]]] = {e["key"]: [] for e in entries}

    def one(m: Any) -> Dict[str, Dict[str, Any]]:
        return score_entries(m.provider, view, locale, tier=tier, system=system, batch_size=batch_size, workers=workers, memo=memo)
    if int(workers) > 1 and len(members) > 1:
        with ThreadPoolExecutor(max_workers=len(members)) as ex:
            results = list(ex.map(one, members))
    else:
        results = [one(m) for m in members]
    for m, votes in zip(members, results):
        for key, v in votes.items():
            out[key].append({"key": key, "tier": tier, "member": m.index, "family": m.family, "model": m.provider.model, **v})
    return out


def run_jury(entries: Sequence[Dict[str, Any]], locale: str, router: Any, *, system: str, batch_size: int = 40,
             budget_caps: bool = True, tm_lookup: Optional[Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = None,
             roundtrip_fn: Optional[Callable[[Sequence[Dict[str, Any]]], Dict[str, Dict[str, Any]]]] = None,
             deliberator: Optional[Deliberator] = None, workers: int = 1, tally: Optional[EscalationTally] = None,
             memo: Any = None) -> Dict[str, Any]:
    """Run J1 to J3 (+ deliberation) and return {'verdicts', 'pending', 'halted', 'stats'}.

    The budget caps compare the lines sent to J2 or J3 with every line judged in the run so far (tally, kept by
    the caller across batches, a fresh one for a single slice). A cap stops the run only when this batch sends
    lines to that tier, at least budget_caps.min_judged lines were judged and at least min_escalated lines are
    over the cap, a small sample never stops a run. The tally is updated before the function returns.
    memo (llm_tasks.BatchMemo) keeps every finished batch of votes, a rerun answers them from the file.

    workers > 1 runs the members of a tier and the disputed J3 lines of the deliberation round in parallel.
    """
    cfg = router.config
    agreement = {k: int(v) for k, v in cfg.agreement.items()}
    caps = cfg.budget_caps
    by_key = {e["key"]: e for e in entries}
    order = [e["key"] for e in entries]
    total = len(order)
    votes: Dict[str, List[Dict[str, Any]]] = {k: [] for k in order}
    bans = ban_hits(entries, locale)
    evidence: Dict[str, Dict[str, Any]] = {k: {"ban_hits": bans[k], "tm_neighbors": tm_lookup(by_key[k]) if tm_lookup else [],
                                               "roundtrip": {"applied": False, "reason": "not_needed"}} for k in order}
    settled: Dict[str, Dict[str, Any]] = {}
    halted: Optional[Dict[str, Any]] = None
    stats: Dict[str, Any] = {"lines": total}

    def settle(key: str, tier: str, score: int, status: str, rationales: Sequence[str], extra: Optional[Dict[str, Any]] = None) -> None:
        settled[key] = {"key": key, "final_tier": tier, "score": score, "status": status, "votes": votes[key],
                        "evidence": evidence[key], "rationales": list(rationales), **(extra or {})}

    tally = tally if tally is not None else EscalationTally()
    min_judged = int(caps.get("min_judged", 0))
    min_escalated = int(caps.get("min_escalated", 0))

    def cap_check(stage: str, keys: Sequence[str], limit: float) -> Optional[Dict[str, Any]]:
        stats[f"to_{stage}_ratio"] = round(len(keys) / total, 4) if total else 0.0
        count = (tally.to_j2 if stage == "J2" else tally.to_j3) + len(keys)
        judged = tally.lines + total
        ratio = round(count / judged, 4) if judged else 0.0
        stats[f"run_to_{stage}_ratio"] = ratio
        if budget_caps and keys and ratio > limit and judged >= min_judged and count >= min_escalated:
            return {"stage": stage, "ratio": ratio, "cap": limit, "lines": count, "judged": judged, "keys": list(keys),
                    "reason": f"{count} of {judged} lines judged in this run would go to {stage} ({ratio:.0%} > {limit:.0%}), "
                              f"check Pass 1 or the prompt. Lines of this batch that would go there: {', '.join(list(keys)[:10])}"
                              + (f" and {len(keys) - 10} more" if len(keys) > 10 else "")}
        return None

    # J1 ------------------------------------------------------------------- #
    tv = _tier_votes(router, "J1", entries, locale, system, batch_size, workers, memo)
    to_j2: List[str] = []
    to_j3: List[str] = []
    for k in order:
        votes[k].extend(tv[k])
        scores = [v["score"] for v in tv[k]]
        c = classify(scores, agreement)
        if c == "pass":
            settle(k, "J1", min(scores), status_for(min(scores)), [v["reason"] for v in tv[k]])
        elif c == "critical":
            to_j3.append(k)
        else:
            to_j2.append(k)
    stats["J1"] = {"lines": total, "settled": total - len(to_j2) - len(to_j3), "to_J2": len(to_j2), "critical_to_J3": len(to_j3)}
    halted = cap_check("J2", to_j2, float(caps["escalate_j2_ratio"])) or cap_check("J3", to_j3, float(caps["escalate_j3_ratio"]))
    # J2 ------------------------------------------------------------------- #
    if halted is None and to_j2:
        tv = _tier_votes(router, "J2", [by_key[k] for k in to_j2], locale, system, batch_size, workers, memo)
        moved = 0
        for k in to_j2:
            votes[k].extend(tv[k])
            scores = [v["score"] for v in tv[k]]
            if classify(scores, agreement) == "pass":
                settle(k, "J2", min(scores), status_for(min(scores)), [v["reason"] for v in tv[k]])
            else:
                to_j3.append(k)
                moved += 1
        stats["J2"] = {"lines": len(to_j2), "settled": len(to_j2) - moved, "to_J3": moved}
        to_j3 = [k for k in order if k in set(to_j3)]
        halted = cap_check("J3", to_j3, float(caps["escalate_j3_ratio"]))
    # J3 ------------------------------------------------------------------- #
    if halted is None and to_j3:
        if roundtrip_fn is not None:
            for k, ev in roundtrip_fn([by_key[k] for k in to_j3]).items():
                if k in evidence:
                    evidence[k]["roundtrip"] = ev
        tv = _tier_votes(router, "J3", [by_key[k] for k in to_j3], locale, system, batch_size, workers, memo)
        for k in to_j3:
            votes[k].extend(tv[k])
        open_keys = [k for k in to_j3 if not agrees([v["score"] for v in tv[k]], agreement)]
        # every disputed line deliberates on its own, so the lines can run side by side
        if deliberator is not None and open_keys:
            if int(workers) > 1 and len(open_keys) > 1:
                with ThreadPoolExecutor(max_workers=int(workers)) as ex:
                    outcomes = dict(zip(open_keys, ex.map(lambda key: deliberator(by_key[key], tv[key], evidence[key]), open_keys)))
            else:
                outcomes = {key: deliberator(by_key[key], tv[key], evidence[key]) for key in open_keys}
        else:
            outcomes = {}
        disputed = 0
        for k in to_j3:
            j3 = tv[k]
            scores = [v["score"] for v in j3]
            if agrees(scores, agreement):
                settle(k, "J3", min(scores), status_for(min(scores)), [v["reason"] for v in j3])
                continue
            disputed += 1
            result = outcomes.get(k)
            if result is None:
                settle(k, "J3", min(scores), "unresolved", [v["reason"] for v in j3])
            else:
                votes[k].extend(result.get("revotes", []))
                settle(k, "deliberation", int(result["score"]), str(result["status"]), result.get("rationales", []),
                       {"deliberation": result["deliberation"]} if "deliberation" in result else None)
        stats["J3"] = {"lines": len(to_j3), "agreed": len(to_j3) - disputed, "disputed": disputed}
    tally.lines += total
    tally.to_j2 += int(stats["J1"]["to_J2"])
    tally.to_j3 += len(to_j3)
    pending = [k for k in order if k not in settled]
    verdicts = [settled[k] for k in order if k in settled]
    stats["status"] = {s: sum(1 for v in verdicts if v["status"] == s) for s in STATUSES}
    stats["final_tier"] = {t: sum(1 for v in verdicts if v["final_tier"] == t) for t in TIERS + ("deliberation",)}
    return {"verdicts": verdicts, "pending": pending, "halted": halted, "stats": stats}


def load_source_rows(path: Path, src_field: str, dst_field: Optional[str], key_field: str) -> Dict[str, str]:
    """key -> English source from the harness-side table (never shown to jurors)."""
    for col in ([dst_field] if dst_field else ["dst", "target"]):
        try:
            return {r.key: r.src for r in load_table(path, src_field, col, key_field)}
        except L10nError:
            continue
    return {r.key: r.dst for r in load_table(path, src_field, src_field, key_field, target_only=True)}


def default_out(inp: Path) -> Path:
    m = re.match(r"blind_(.+)\.json$", inp.name)
    return inp.with_name(f"verdicts_{m.group(1)}.json") if m else inp.with_name(inp.stem + ".verdicts.json")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Tiered mixed-family jury (J1, J2, J3) over a blind slice, B3.4 verdicts")
    add_input_argument(ap, "Blind slice (make_blind_slice.py output, target only)")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--out", default=None, help="Verdict file (default: verdicts_<locale>_<batch>.json next to the slice)")
    ap.add_argument("--source-table", default=None, help="Harness-side table with the English source, enables the back-translation evidence for J3 lines")
    ap.add_argument("--src-field", default=None, help="Source column of --source-table (default en, or src_field of --config)")
    ap.add_argument("--dst-field", default=None, help="Target column of --source-table (default: dst_field of --config, else dst, then target)")
    ap.add_argument("--key-field", default=None, help="Key column of --source-table (default key, or key_field of --config)")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs, for warm-up and contrastive few-shots (default: the skill's langpack/)")
    ap.add_argument("--no-warmup", action="store_true", help="Leave the warm-up block out of the critic prompt")
    ap.add_argument("--warmup-count", type=int, default=40, help="Warm-up lines in the prompt (default 40)")
    ap.add_argument("--shots", type=int, default=6, help="Contrastive few-shot pairs from the pack (default 6)")
    ap.add_argument("--seed", type=int, default=1234, help="Seed of the warm-up and few-shot sample (default 1234)")
    ap.add_argument("--batch-size", type=int, default=40, help="Lines per model call (default 40)")
    ap.add_argument("--no-budget-caps", action="store_true", help="Do not stop when the J2 or J3 escalation ratio is above the cap")
    ap.add_argument("--no-deliberation", action="store_true", help="Leave J3 disagreements unresolved instead of running the deliberation round")
    ap.add_argument("--tm", default=None, help="Translation memory (tm.py SQLite) for the evidence: closest approved lines")
    ap.add_argument("--workers", type=int, default=4, help="Batches in flight per member, the three members of a tier and the disputed lines run in parallel (default 4, 1 = one call at a time)")
    ap.add_argument("--context-map", default=None, help="CONTEXT_MAP.md of the game, its line_notes.json next to it gives every line its context")
    ap.add_argument("--cache", default=None, help="JSON file that keeps every finished batch of votes, the same command resumes where a stopped run ended")
    add_model_args(ap)
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    apply_config(args, {"context_map": None, "src_field": "en", "dst_field": None, "key_field": "key"})
    locale, _v = normalize_locale(args.locale)
    inp = Path(args.input)
    entries, source_file = load_blind_slice(inp)
    out = Path(args.out) if args.out else default_out(inp)
    if args.workers < 1:
        raise L10nError("--workers must be 1 or more")
    router = make_router(args, list(TIERS), default_budget_path(out))
    pack_dir = (Path(args.langpack_dir) if args.langpack_dir else LANGPACK_DIR) / locale
    system, info = build_system_prompt(locale, entries, pack_dir, warmup=not args.no_warmup, warmup_count=args.warmup_count,
                                       shots=args.shots, seed=args.seed)
    if args.context_map:  # jurors read the map and the neutral line fields, never the locale appendix
        ctx = load_context(Path(args.context_map), locale)
        info["context_map"] = ctx.source
        info["context_lines"] = ctx.enrich(entries)
        system = ctx.system(system)
    memo = BatchMemo(Path(args.cache)) if args.cache else None
    roundtrip_fn = None
    if args.source_table:
        sources = load_source_rows(Path(args.source_table), args.src_field, args.dst_field, args.key_field)
        threshold, _src = load_threshold(locale, pack_dir.parent)
        rt = router.config.roundtrip
        router.require(["roundtrip"])

        def roundtrip_fn(lines: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
            rows = [{"key": e["key"], "en": sources.get(e["key"], ""), "target": e["target"], "register": e["register"]} for e in lines]
            return roundtrip_evidence(rows, locale, router.for_role("roundtrip"), min_words=int(rt["min_words"]),
                                      registers=rt["registers"], threshold=threshold, workers=args.workers, memo=memo)
    tm = None
    tm_lookup = None
    if args.tm:
        from tm import TranslationMemory
        if not Path(args.tm).is_file():
            raise L10nError(f"--tm file not found: {args.tm}")
        tm = TranslationMemory(Path(args.tm))
        src_by_key = load_source_rows(Path(args.source_table), args.src_field, args.dst_field, args.key_field) if args.source_table else {}

        def tm_lookup(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
            src = src_by_key.get(entry["key"], "")
            return tm.neighbors(locale, src if src else entry["target"], on="src" if src else "dst",
                                category=str(entry.get("category") or ""), speaker=str(entry.get("speaker") or ""), exclude_key=entry["key"])
    deliberator = None
    if not args.no_deliberation:
        from deliberate import make_deliberator  # local import: deliberate.py imports this module
        deliberator = make_deliberator(router, locale, system)
    try:
        res = run_jury(entries, locale, router, system=system, batch_size=args.batch_size, budget_caps=not args.no_budget_caps,
                       roundtrip_fn=roundtrip_fn, deliberator=deliberator, tm_lookup=tm_lookup, workers=args.workers, memo=memo)
    finally:
        if tm is not None:
            tm.close()
    return write_report(args, locale, out, source_file, info, router, res)


def write_report(args: Any, locale: str, out: Path, source_file: str, info: Dict[str, Any], router: Any, res: Dict[str, Any]) -> int:
    """Write the verdict file and print the summary; returns the exit code."""
    doc = {"locale": locale, "source_file": source_file, "langpack_version": info.get("langpack_version"),
           "prompt": {"warmup_lines": info.get("warmup_lines", 0), "shots": info.get("shots", 0),
                      "context_map": info.get("context_map"), "context_lines": info.get("context_lines", 0)},
           "stats": res["stats"], "halted": res["halted"], "verdicts": res["verdicts"], "pending": res["pending"], "notes": router.notes}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    st = res["stats"]
    unresolved = st["status"]["unresolved"]
    exit_code = EXIT_FINDINGS if (res["halted"] or unresolved) else EXIT_OK
    lines = [f"Jury {locale}: {st['lines']} lines -> {out}"]
    lines.append("  status " + ", ".join(f"{k} {v}" for k, v in st["status"].items()))
    lines.append("  settled at " + ", ".join(f"{k} {v}" for k, v in st["final_tier"].items()))
    for key in ("to_J2_ratio", "to_J3_ratio"):
        if key in st:
            lines.append(f"  {key.replace('_', ' ')} {st[key]:.0%}")
    if res["halted"]:
        lines.append(f"  STOPPED at {res['halted']['stage']}. {res['halted']['reason']}. {len(res['pending'])} lines pending")
    if unresolved:
        lines.append(f"  {unresolved} unresolved line(s) go to the developer with three rationales")
    for n in router.notes:
        lines.append(f"  NOTE: {n}")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "out": str(out), **{k: doc[k] for k in ("locale", "stats", "halted", "pending")},
               "notes": router.notes, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
