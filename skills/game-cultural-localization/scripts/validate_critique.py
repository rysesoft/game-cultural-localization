#!/usr/bin/env python3
"""Critique schema validation CLI facade delegating to gcl.infrastructure.formats.critique_validator."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcl.infrastructure.formats.critique_validator import ISSUE_TYPES, load_slice_targets, validate  # noqa: E402
from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, PLACEHOLDER_STYLES, TAG_STYLES, add_common_args, add_input_argument, emit_report,
    load_config, load_json_data, normalize_locale, pick, resolve_input, run_main, __version__,
)

TOOL = "validate_critique"


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
    problems = validate(
        data, slice_targets,
        pick(args.placeholder_style, cfg, "placeholder_style", "auto"),
        pick(args.tag_style, cfg, "tag_style", "auto"),
        expected,
    )
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
    payload = {
        "tool": TOOL, "version": __version__, "critique": str(args.critique), "slice": args.slice,
        "entries": n_entries, "summary": {"problems": len(problems)}, "problems": problems, "exit_code": exit_code,
    }
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
