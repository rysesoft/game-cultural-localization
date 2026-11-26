#!/usr/bin/env python3
"""Validate a native-ear critique file against the fixed critique schema.

Schema (critique_<locale>_<batch>.json):
{
  "locale": "de-DE",
  "source_file": "blind_de-DE_01.json",
  "entries": [
    {"key": "...", "score": 1-5, "issue_type": "translationese|register|tense|regional_leak|gender_leak|ui_verb|placeholder_grammar|terminology|other",
     "reason": "...", "suggested": "..."}
  ],
  "summary": {"total": N, "flagged": N, "critical": N}
}
Only entries with score < 5 are listed.  "critical" counts entries with score <= 2.

With --slice <blind_slice.json|csv>, every key must exist in the slice and the
"suggested" text must keep placeholder and rich-text tag parity with the slice's
target (so the critic cannot break tokens).  Exit 0 valid, 1 invalid, 2 usage.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, PLACEHOLDER_STYLES, TAG_STYLES, L10nError, add_common_args, add_input_argument, resolve_input, compare_placeholders,
    compare_tags, emit_report, extract_placeholders, extract_tags, load_config, load_json_data, load_table,
    normalize_locale, pick, run_main, __version__,
)

TOOL = "validate_critique"
ISSUE_TYPES = ("translationese", "register", "tense", "regional_leak", "gender_leak", "ui_verb", "placeholder_grammar", "terminology", "other")


def load_slice_targets(path: Path) -> Dict[str, str]:
    """Load key -> target from a blind slice (JSON written by make_blind_slice, or any table with a 'target' column)."""
    if path.suffix.lower() == ".json":
        data = load_json_data(path)
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            out: Dict[str, str] = {}
            for e in data["entries"]:
                if isinstance(e, dict) and "key" in e:
                    out[str(e["key"])] = str(e.get("target", ""))
            return out
    rows = load_table(path, "en", "target", "key", target_only=True)
    return {r.key: r.dst for r in rows}


def validate(data: Any, slice_targets: Optional[Dict[str, str]], ph_style: str, tag_style: str, locale_expected: Optional[str]) -> List[str]:
    """Return a list of problems (empty = valid)."""
    problems: List[str] = []
    if not isinstance(data, dict):
        return ["top level must be a JSON object"]
    for req in ("locale", "source_file", "entries", "summary"):
        if req not in data:
            problems.append(f"missing top-level field '{req}'")
    if problems:
        return problems
    try:
        loc = normalize_locale(str(data["locale"]))[0]
        if locale_expected and loc != locale_expected:
            problems.append(f"locale '{data['locale']}' does not match expected '{locale_expected}'")
    except L10nError as exc:
        problems.append(str(exc))
    entries = data["entries"]
    if not isinstance(entries, list):
        return problems + ["'entries' must be a list"]
    seen = set()
    flagged = 0
    critical = 0
    for idx, e in enumerate(entries):
        where = f"entries[{idx}]"
        if not isinstance(e, dict):
            problems.append(f"{where}: must be an object")
            continue
        key = e.get("key")
        if not isinstance(key, str) or not key:
            problems.append(f"{where}: 'key' must be a non-empty string")
            continue
        where = f"entries[{idx}] ({key})"
        if key in seen:
            problems.append(f"{where}: duplicate key")
        seen.add(key)
        score = e.get("score")
        if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            problems.append(f"{where}: 'score' must be an integer 1-5")
        elif score == 5:
            problems.append(f"{where}: score 5 entries must not be listed (only score < 5)")
        else:
            flagged += 1
            if score <= 2:
                critical += 1
        it = e.get("issue_type")
        if it not in ISSUE_TYPES:
            problems.append(f"{where}: 'issue_type' {it!r} not in {ISSUE_TYPES}")
        if not isinstance(e.get("reason"), str) or not e.get("reason", "").strip():
            problems.append(f"{where}: 'reason' must be a non-empty string")
        suggested = e.get("suggested")
        if not isinstance(suggested, str):
            problems.append(f"{where}: 'suggested' must be a string")
            suggested = None
        if slice_targets is not None:
            if key not in slice_targets:
                problems.append(f"{where}: key not present in the blind slice")
            elif suggested is not None and suggested.strip():
                original = slice_targets[key]
                for p in compare_placeholders(extract_placeholders(original, ph_style), extract_placeholders(suggested, ph_style)):
                    if it == "placeholder_grammar":
                        continue  # the critic is deliberately repairing a token problem; Pass 2 re-verifies against the source
                    problems.append(f"{where}: suggested text breaks placeholder parity: {p}")
                for p in compare_tags(extract_tags(original, tag_style), extract_tags(suggested, tag_style)):
                    problems.append(f"{where}: suggested text breaks tag parity: {p}")
                if suggested.strip() == original.strip():
                    problems.append(f"{where}: suggested text is identical to the current target")
    summary = data["summary"]
    if not isinstance(summary, dict):
        problems.append("'summary' must be an object")
    else:
        for k in ("total", "flagged", "critical"):
            if not isinstance(summary.get(k), int) or isinstance(summary.get(k), bool) or summary.get(k) < 0:
                problems.append(f"summary.{k} must be a non-negative integer")
        if isinstance(summary.get("flagged"), int) and summary["flagged"] != flagged:
            problems.append(f"summary.flagged={summary['flagged']} but {flagged} entries are listed")
        if isinstance(summary.get("critical"), int) and summary["critical"] != critical:
            problems.append(f"summary.critical={summary['critical']} but {critical} entries have score <= 2")
        if isinstance(summary.get("total"), int) and isinstance(summary.get("flagged"), int) and summary["total"] < summary["flagged"]:
            problems.append("summary.total is smaller than summary.flagged")
        if slice_targets is not None and isinstance(summary.get("total"), int) and summary["total"] != len(slice_targets):
            problems.append(f"summary.total={summary['total']} but the blind slice has {len(slice_targets)} entries")
    return problems


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Validate critique_<locale>_<batch>.json against the fixed critic schema (exit 0 valid / 1 invalid / 2 usage)")
    add_input_argument(ap, "critique_<locale>_<batch>.json produced by the native-ear critic", name="critique")
    ap.add_argument("--slice", help="Blind slice the critic read; enables key existence + placeholder/tag parity checks")
    ap.add_argument("--locale", help="Expected locale (must match the file's 'locale')")
    ap.add_argument("--placeholder-style", choices=PLACEHOLDER_STYLES, default=None, help="Placeholder syntax (default auto)")
    ap.add_argument("--tag-style", choices=TAG_STYLES, default=None, help="Rich-text tag syntax (default auto)")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args, name="critique")
    cfg = load_config(Path(args.config)) if args.config else {}
    data = load_json_data(Path(args.critique))
    slice_targets = load_slice_targets(Path(args.slice)) if args.slice else None
    expected = normalize_locale(args.locale)[0] if args.locale else None
    problems = validate(data, slice_targets, pick(args.placeholder_style, cfg, "placeholder_style", "auto"), pick(args.tag_style, cfg, "tag_style", "auto"), expected)
    exit_code = EXIT_FINDINGS if problems else EXIT_OK
    n_entries = len(data.get("entries", [])) if isinstance(data, dict) and isinstance(data.get("entries"), list) else 0
    lines = [f"Critique validation: {args.critique} ({n_entries} entries" + (f", slice {len(slice_targets)} targets" if slice_targets is not None else "") + ")"]
    lines.append(f"  Problems: {len(problems)}")
    limit = args.max_report if args.max_report is not None else len(problems)
    for p in problems[:limit]:
        lines.append(f"  ERR : {p}")
    if len(problems) > limit:
        lines.append(f"  ... and {len(problems) - limit} more.")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "critique": str(args.critique), "slice": args.slice,
               "entries": n_entries, "summary": {"problems": len(problems)}, "problems": problems, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
