#!/usr/bin/env python3
"""J3 deliberation round CLI facade delegating to gcl.application.jury.deliberation."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_context_map import load_context  # noqa: E402
from build_language_pack import LANGPACK_DIR  # noqa: E402
from gcl.application.jury.deliberation import (  # noqa: E402
    GENERIC_NAMES, LABELS, anonymize, decide, decide_line, deliberate_line as _deliberate_line,
    deliberate_lines as _deliberate_lines, deliberate_verdicts, evidence_package, make_deliberator,
    name_scrubber, revote_payload,
)
from gcl.application.jury.policy import juror_view, status_for  # noqa: E402
from gcl.infrastructure.persistence.context_views import BlindContextAdapter  # noqa: E402
from jury import build_system_prompt, load_blind_slice  # noqa: E402
from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, apply_config, emit_report,
    load_json_data, normalize_locale, resolve_input, run_main, __version__,
)
from llm_tasks import add_model_args, default_budget_path, make_router  # noqa: E402

TOOL = "deliberate"


def deliberate_line(
    entry: Dict[str, Any],
    j3_votes: Sequence[Dict[str, Any]],
    evidence: Dict[str, Any],
    members: Sequence[Any],
    locale: str,
    system: str,
    scrub: "re.Pattern[str]",
    critical_max: int = 2,
) -> Dict[str, Any]:
    """Backward compatible wrapper forwarding explicit critical_max to gcl.application.jury.deliberation."""
    return _deliberate_line(entry, j3_votes, evidence, members, locale, system, scrub, critical_max=critical_max)


def deliberate_lines(
    items: Sequence[Tuple[Dict[str, Any], Sequence[Dict[str, Any]], Dict[str, Any]]],
    members: Sequence[Any],
    locale: str,
    system: str,
    scrub: "re.Pattern[str]",
    critical_max: int = 2,
    workers: int = 1,
    memo: Any = None,
) -> Dict[str, Dict[str, Any]]:
    """Backward compatible wrapper forwarding explicit parameters to gcl.application.jury.deliberation."""
    return _deliberate_lines(items, members, locale, system, scrub, critical_max=critical_max, workers=workers, memo=memo)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="J3 deliberation round (anonymous rationales, evidence, one re-vote, majority)")
    add_input_argument(ap, "Verdict file written by jury.py")
    ap.add_argument("--slice", required=True, help="The blind slice the jury read (target texts)")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--out", default=None, help="Write the updated verdicts here (default: update the input file)")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs, for the critic prompt warm-up (default: the skill's langpack/)")
    ap.add_argument("--no-warmup", action="store_true", help="Leave the warm-up block out of the critic prompt")
    ap.add_argument("--seed", type=int, default=1234, help="Seed of the warm-up and few-shot sample (default 1234)")
    ap.add_argument("--context-map", default=None, help="CONTEXT_MAP.md of the game (or context_map of --config), the jurors re-vote with the map and the neutral line notes")
    add_model_args(ap)
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    apply_config(args, {"context_map": None})
    locale, _v = normalize_locale(args.locale)
    inp = Path(args.input)
    doc = load_json_data(inp)
    if not isinstance(doc, dict) or not isinstance(doc.get("verdicts"), list):
        raise L10nError(f"{inp}: not a jury verdict file (no 'verdicts' list)")
    entries, _src = load_blind_slice(Path(args.slice))
    out = Path(args.out) if args.out else inp
    router = make_router(args, ["J3"], default_budget_path(out))
    pack_dir = (Path(args.langpack_dir) if args.langpack_dir else LANGPACK_DIR) / locale
    system, _info = build_system_prompt(locale, entries, pack_dir, warmup=not args.no_warmup, warmup_count=40, shots=6, seed=args.seed)
    if args.context_map:
        ctx = BlindContextAdapter(load_context(Path(args.context_map), locale))
        ctx.enrich_entries(entries)
        system = ctx.build_system(system)
    counts = deliberate_verdicts(doc, entries, router, locale, system)
    doc["notes"] = list(doc.get("notes", [])) + [n for n in router.notes if n not in doc.get("notes", [])]
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    remaining = sum(1 for v in doc["verdicts"] if v["status"] == "unresolved")
    exit_code = EXIT_FINDINGS if remaining else EXIT_OK
    lines = [
        f"Deliberation {locale}: {counts['deliberated']} J3 disagreement(s), {counts['resolved']} settled by majority, "
        f"{counts['unresolved']} still unresolved -> {out}",
    ]
    for v in doc["verdicts"]:
        if v.get("final_tier") == "deliberation":
            d = v["deliberation"]
            lines.append(f"  {v['key']}: first {d['first']} revote {d['revote']} -> {v['status']}")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "out": str(out), "counts": counts, "unresolved": remaining, "notes": router.notes, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
