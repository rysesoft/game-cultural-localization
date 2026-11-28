#!/usr/bin/env python3
"""Developer report CLI facade delegating to gcl.application.reporting."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import budget_report  # noqa: E402
from build_language_pack import LANGPACK_DIR  # noqa: E402
from gcl.application.reporting import (  # noqa: E402
    NO_OBJECTION, SECONDARY_FAILED, STATUS_ORDER, TIER_BASE, TRUST_TEXT, batch_of, build_report, confidence,
    load_sources_with, reason_of, render_markdown, secondary_passed, trust_level, votes_summary,
)
from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, emit_report, load_json_data,
    load_table, normalize_locale, resolve_input, run_main, __version__,
)
from providers import load_providers_config  # noqa: E402
from text_style import punctuation_problems  # noqa: E402

TOOL = "report_changes"


def load_sources(path: Path | None, locale: str) -> dict[str, dict[str, str]]:
    """key -> {en, target, category, speaker} from the Pass 1 table (optional)."""
    return load_sources_with(path, locale, load_table)


def _load_budget(budget_log: str | None, providers_config: str | None) -> dict[str, Any] | None:
    if not budget_log:
        return None
    recs = budget_report.read_records(budget_report.find_logs(Path(budget_log)))
    prices = budget_report.price_table(load_providers_config(Path(providers_config) if providers_config else None))
    tot = budget_report.aggregate(recs, [], prices)[0]
    return {k: tot[k] for k in ("calls", "errors", "input_tokens", "output_tokens", "latency_ms", "cost_usd", "priced", "unpriced_models")}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Developer change report (JSON + Markdown) of a jury and Pass 2 batch")
    add_input_argument(ap, "Verdict file written by jury.py (deliberated or not)")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--rewrites", default=None, help="Rewrite file of pass2_rewrite.py (new texts and candidates)")
    ap.add_argument("--source-table", default=None, help="Pass 1 table (en, current target, category, speaker) when no rewrite file covers a line")
    ap.add_argument("--budget-log", default=None, help="budget.jsonl file or folder for the budget summary")
    ap.add_argument("--providers-config", default=None, help="providers.config.json with the prices (default: the bundled one)")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs, for the trust level and version (default: the skill's langpack/)")
    ap.add_argument("--batch", default=None, help="Batch id in the file names (default: taken from verdicts_<locale>_<batch>.json)")
    ap.add_argument("--out-dir", default=None, help="Folder of changes_<locale>_<batch>.json and .md (default: next to the verdicts)")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    args = (ap := build_parser()).parse_args()
    resolve_input(ap, args)
    locale, _v = normalize_locale(args.locale)
    inp = Path(args.input)
    doc = load_json_data(inp)
    if not isinstance(doc, dict) or not isinstance(doc.get("verdicts"), list):
        raise L10nError(f"{inp}: not a jury verdict file (no 'verdicts' list)")
    rewrites = load_json_data(Path(args.rewrites)) if args.rewrites else None
    if rewrites is not None and not isinstance(rewrites, dict):
        raise L10nError(f"{args.rewrites}: not a rewrite file")
    sources = load_sources(Path(args.source_table) if args.source_table else None, locale)
    budget = _load_budget(args.budget_log, args.providers_config)
    pack_dir = (Path(args.langpack_dir) if args.langpack_dir else LANGPACK_DIR) / locale
    batch = args.batch or batch_of(inp, locale)
    rep = build_report(doc, locale, batch, rewrites=rewrites, sources=sources, pack_dir=pack_dir, budget=budget)
    md = render_markdown(rep)
    if (style := punctuation_problems(md)):
        raise L10nError(f"internal: generated Markdown breaks the punctuation style at line {style[0][0]} ({style[0][1]})")
    out_dir = Path(args.out_dir) if args.out_dir else inp.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    jpath, mpath = out_dir / f"changes_{locale}_{batch}.json", out_dir / f"changes_{locale}_{batch}.md"
    jpath.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mpath.write_text(md, encoding="utf-8")
    attention = len(rep["unresolved"]) + sum(1 for l in rep["lines"] if l["rewrite_valid"] is False)
    exit_code = EXIT_FINDINGS if attention else EXIT_OK
    lines = [
        f"Change report {locale} batch {batch}: {jpath.name} and {mpath.name} in {out_dir}",
        f"  trust level {rep['header']['trust_level']}, {rep['changed']} line(s) to change, {len(rep['unresolved'])} unresolved",
        f"  Exit code: {exit_code}",
    ]
    payload = {
        "tool": TOOL, "version": __version__, "json": str(jpath), "markdown": str(mpath),
        "summary": rep["summary"], "changed": rep["changed"], "unresolved": len(rep["unresolved"]),
        "trust_level": rep["header"]["trust_level"], "exit_code": exit_code,
    }
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
