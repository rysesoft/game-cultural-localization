#!/usr/bin/env python3
"""Build the contrastive set (native, robot, unknown) of a language pack from a professional reference table.

For every reference row (key, en, native target):
  native   the professional translation (the only human signal)
  robot    a deliberately literal translation by the 'literal' model with prompts/literal.md
  unknown  raw translations by strong models (default: the 'pass1' model), unlabeled, observation only

Pairs where the robot line equals the native line, or where the robot line broke a
placeholder, carry no contrast and are left out (counted in 'dropped').

Output (B3.5):
  {"locale": "tr-TR", "source_ref": "loc_work/reference/...", "pairs": [
     {"key", "en", "native", "robot", "unknown": {"<model id>": "..."}, "register", "speaker", "archetype"}]}

Usage:
  python build_contrastive_set.py loc_work/reference/tr.csv --locale tr-TR [--out ../langpack/tr-TR/contrastive.json] [--limit 300]
  python build_contrastive_set.py ref.csv --locale tr-TR --out c.json --dry-run

Exit codes: 0 set written, 1 set written but fewer usable pairs than --min-pairs,
2 usage or input error (missing column, unknown locale, missing API key).
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, compare_placeholders, emit_report,
    extract_placeholders, load_table, normalize_locale, resolve_input, run_main, __version__,
)
from build_language_pack import LANGPACK_DIR, infer_register, norm_text  # noqa: E402
from llm_tasks import add_model_args, default_budget_path, make_router, translate_rows  # noqa: E402
from prompt_templates import render_prompt  # noqa: E402

TOOL = "build_contrastive_set"
DEFAULT_MIN_PAIRS = 30
DEFAULT_SEED = 1234


def load_reference_rows(path: Path, locale: str, src_field: str = "en", dst_field: Optional[str] = None,
                        key_field: str = "key") -> List[Dict[str, Any]]:
    """Reference rows {key, en, native, register, speaker, archetype}; the target column is probed when not given."""
    candidates = [dst_field] if dst_field else [locale, "dst", "target", locale.split("-")[0]]
    rows = None
    last: Optional[L10nError] = None
    for col in candidates:
        try:
            rows = load_table(path, src_field, col, key_field)
            break
        except L10nError as exc:
            last = exc
    if rows is None:
        raise L10nError(f"{path}: no target column for {locale} (tried {', '.join(str(c) for c in candidates)}), pass --dst-field") from last
    out = []
    for r in rows:
        if not r.src.strip() or not r.dst.strip():
            continue
        category = str(r.meta.get("register") or r.meta.get("category") or "")
        out.append({"key": r.key, "en": r.src, "native": r.dst, "register": infer_register(category, r.dst, "game"),
                    "speaker": str(r.meta.get("speaker") or ""), "archetype": str(r.meta.get("archetype") or "")})
    return out


def select_rows(rows: Sequence[Dict[str, Any]], limit: int, seed: int) -> List[Dict[str, Any]]:
    """Seeded subset of at most `limit` rows, kept in input order (0 = all rows)."""
    if not limit or limit >= len(rows):
        return list(rows)
    idx = sorted(random.Random(seed).sample(range(len(rows)), limit))
    return [rows[i] for i in idx]


def build_contrastive(rows: Sequence[Dict[str, Any]], locale: str, robot_provider: Any, unknown_providers: Dict[str, Any],
                      batch_size: int = 30) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Generate robot and unknown lines and assemble the pairs. Returns (pairs, stats)."""
    src_rows = [{"key": r["key"], "source": r["en"], "register": r["register"]} for r in rows]
    robot = translate_rows(robot_provider, src_rows, locale, task="literal", system=render_prompt("literal", locale), batch_size=batch_size)
    unknown: Dict[str, Dict[str, str]] = {}
    for model_id, prov in unknown_providers.items():
        unknown[model_id] = translate_rows(prov, src_rows, locale, task="pass1", batch_size=batch_size)
    pairs: List[Dict[str, Any]] = []
    dropped = {"robot_equals_native": 0, "robot_broke_placeholders": 0}
    for r in rows:
        rb = robot[r["key"]]
        if norm_text(rb) == norm_text(r["native"]):
            dropped["robot_equals_native"] += 1
            continue
        if compare_placeholders(extract_placeholders(r["en"]), extract_placeholders(rb)):
            dropped["robot_broke_placeholders"] += 1
            continue
        pairs.append({"key": r["key"], "en": r["en"], "native": r["native"], "robot": rb,
                      "unknown": {m: unknown[m][r["key"]] for m in unknown}, "register": r["register"],
                      "speaker": r["speaker"], "archetype": r["archetype"]})
    stats = {"rows": len(rows), "pairs": len(pairs), "dropped": dropped,
             "robot_model": getattr(robot_provider, "model", "?"), "unknown_models": list(unknown_providers)}
    return pairs, stats


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Build contrastive.json (native / robot / unknown lines) from a professional reference table")
    add_input_argument(ap, "Reference table with key, en and the professional target (CSV / TSV / JSON / PO)")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--out", default=None, help="Output JSON (default: langpack/<locale>/contrastive.json)")
    ap.add_argument("--src-field", default="en", help="Source column (default en)")
    ap.add_argument("--dst-field", default=None, help="Professional target column (default: the locale code, then dst, target)")
    ap.add_argument("--key-field", default="key", help="Key column (default key)")
    ap.add_argument("--unknown-models", default=None, help="Comma separated model aliases for the unknown lines (default: the pass1 model)")
    ap.add_argument("--no-unknown", action="store_true", help="Skip the unknown lines")
    ap.add_argument("--limit", type=int, default=0, help="Use a seeded subset of N rows (default: all)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Seed of --limit (default {DEFAULT_SEED})")
    ap.add_argument("--batch-size", type=int, default=30, help="Rows per model call (default 30)")
    ap.add_argument("--min-pairs", type=int, default=DEFAULT_MIN_PAIRS, help=f"Exit 1 when fewer usable pairs result (default {DEFAULT_MIN_PAIRS})")
    add_model_args(ap)
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    locale, _v = normalize_locale(args.locale)
    out = Path(args.out) if args.out else LANGPACK_DIR / locale / "contrastive.json"
    rows = load_reference_rows(Path(args.input), locale, args.src_field, args.dst_field, args.key_field)
    if not rows:
        raise L10nError(f"{args.input}: no row has both an English source and a target")
    router = make_router(args, ["literal"] + ([] if args.no_unknown else ["pass1"]), default_budget_path(out))
    unknown: Dict[str, Any] = {}
    if not args.no_unknown:
        aliases = [a.strip() for a in args.unknown_models.split(",") if a.strip()] if args.unknown_models else [router.config.role_model("pass1").alias]
        for alias in aliases:
            prov = router.for_model(alias, "pass1")
            unknown[prov.model] = prov
    selected = select_rows(rows, args.limit, args.seed)
    pairs, stats = build_contrastive(selected, locale, router.for_role("literal"), unknown, args.batch_size)
    payload_file = {"locale": locale, "source_ref": str(args.input), "seed": args.seed, "limit": args.limit,
                    "generated_with": {"robot": stats["robot_model"], "unknown": stats["unknown_models"], "prompt": "prompts/literal.md"},
                    "pairs": pairs}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload_file, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    short = len(pairs) < args.min_pairs
    exit_code = EXIT_FINDINGS if short else EXIT_OK
    lines = [f"Contrastive set {locale}: {out} ({len(pairs)} pairs from {len(selected)} rows)",
             f"  robot model {stats['robot_model']}, unknown models {', '.join(stats['unknown_models']) or 'none'}",
             f"  dropped: identical {stats['dropped']['robot_equals_native']}, broken placeholders {stats['dropped']['robot_broke_placeholders']}"]
    if short:
        lines.append(f"  WARN: fewer than {args.min_pairs} usable pairs")
    for n in router.notes:
        lines.append(f"  NOTE: {n}")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "locale": locale, "out": str(out), "stats": stats, "notes": router.notes, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
