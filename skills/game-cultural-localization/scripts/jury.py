#!/usr/bin/env python3
"""Tiered mixed-family jury CLI facade delegating to gcl.application.jury."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_context_map import load_context  # noqa: E402
from build_language_pack import LANGPACK_DIR, infer_register  # noqa: E402
from gcl.application.jury import (  # noqa: E402
    CONTEXT_FIELDS, SOURCE_COLUMNS, STATUSES, TIERS, Deliberator, EscalationTally, _tier_votes, agrees, classify,
    juror_view, run_jury as _run_jury, status_for,
)
from gcl.infrastructure.persistence.context_views import BlindContextAdapter  # noqa: E402
from llm_tasks import BatchMemo, add_model_args, default_budget_path, make_router, score_entries  # noqa: E402
from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, Row, add_common_args, add_input_argument, apply_config, emit_report,
    load_json_data, load_table, normalize_locale, resolve_input, run_main, __version__,
)
import lqa_linter  # noqa: E402
from prompt_templates import render_contrastive, render_prompt  # noqa: E402
from roundtrip_check import load_threshold, roundtrip_evidence  # noqa: E402
from warmup_loader import REGISTERS, load_warmup, render_warmup  # noqa: E402

TOOL = "jury"


def load_blind_slice(path: Path) -> Tuple[List[Dict[str, Any]], str]:
    """Entries {key, target, register, context...} of a blind slice; refuses any source column."""
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


def ban_hits(entries: Sequence[Dict[str, Any]], locale: str) -> Dict[str, List[Dict[str, str]]]:
    """Locale rule hits per key (target only)."""
    rules = lqa_linter.load_rules(locale)
    ids = {r.id for r in rules}
    rows = [Row(e["key"], "", e["target"], {"category": e.get("category") or e.get("register", "")}) for e in entries]
    out: Dict[str, List[Dict[str, str]]] = {e["key"]: [] for e in entries}
    for f in lqa_linter.lint_rows(rows, rules, lqa_linter.LintOptions(locale=locale, check_untranslated=False)):
        if f.code in ids:
            out[f.key].append({"rule": f.code, "severity": f.severity, "message": f.message})
    return out


def build_system_prompt(
    locale: str, entries: Sequence[Dict[str, Any]], pack_dir: Optional[Path], *, warmup: bool, warmup_count: int, shots: int, seed: int,
) -> Tuple[str, Dict[str, Any]]:
    """Build critic prompt with language pack warm-up and contrastive few-shots."""
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


def run_jury(
    entries: Sequence[Dict[str, Any]], locale: str, router: Any, *, system: str, batch_size: Optional[int] = None,
    budget_caps: bool = True, tm_lookup: Optional[Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = None,
    roundtrip_fn: Optional[Callable[[Sequence[Dict[str, Any]]], Dict[str, Dict[str, Any]]]] = None,
    deliberator: Optional[Deliberator] = None, workers: int = 1, tally: Optional[EscalationTally] = None, memo: Any = None,
) -> Dict[str, Any]:
    """Run J1-J3 escalation chain via gcl.application.jury.run_jury with target-only ban hits."""
    return _run_jury(
        entries, locale, router, system=system, batch_size=batch_size, budget_caps=budget_caps,
        tm_lookup=tm_lookup, roundtrip_fn=roundtrip_fn, deliberator=deliberator,
        workers=workers, tally=tally, memo=memo, ban_hits_fn=ban_hits, score_fn=score_entries,
    )


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
    ap.add_argument("--batch-size", type=int, default=None, help="Lines per model call (default 100, with a character budget so long letters never pile up in one call)")
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
    system, info = build_system_prompt(locale, entries, pack_dir, warmup=not args.no_warmup, warmup_count=args.warmup_count, shots=args.shots, seed=args.seed)
    if args.context_map:
        ctx = BlindContextAdapter(load_context(Path(args.context_map), locale))
        info["context_map"] = ctx.source_name
        info["context_lines"] = ctx.enrich_entries(entries)
        system = ctx.build_system(system)
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
        from gcl.application.jury.deliberation import make_deliberator
        deliberator = make_deliberator(router, locale, system)
    try:
        res = run_jury(entries, locale, router, system=system, batch_size=args.batch_size, budget_caps=not args.no_budget_caps,
                       roundtrip_fn=roundtrip_fn, deliberator=deliberator, tm_lookup=tm_lookup, workers=args.workers, memo=memo)
    finally:
        if tm is not None:
            tm.close()
    return write_report(args, locale, out, source_file, info, router, res)


def write_report(args: Any, locale: str, out: Path, source_file: str, info: Dict[str, Any], router: Any, res: Dict[str, Any]) -> int:
    """Write the verdict file and print summary; return exit code."""
    doc = {
        "locale": locale, "source_file": source_file, "langpack_version": info.get("langpack_version"),
        "prompt": {"warmup_lines": info.get("warmup_lines", 0), "shots": info.get("shots", 0),
                   "context_map": info.get("context_map"), "context_lines": info.get("context_lines", 0)},
        "stats": res["stats"], "halted": res["halted"], "verdicts": res["verdicts"], "pending": res["pending"], "notes": router.notes,
    }
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
