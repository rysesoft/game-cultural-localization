#!/usr/bin/env python3
"""Developer report of a jury + Pass 2 batch: what changes, why, on what evidence, how sure (B3.8).

Writes changes_<locale>_<batch>.json and changes_<locale>_<batch>.md.
  header      trust level (A9), language pack version, budget summary of the batch
  lines       every line the jury flagged. key, en, old, new, status, reason, evidence, confidence (0 to 1),
              votes summary per tier, and an empty 'decision' the developer fills with accept or reject
              (tm.py --mode approve reads it back into the translation memory)
  unresolved  lines the jury could not settle, with their three rationales

Trust level (A9)
  measured   the pack has a professional reference and a passing eval_critic calibration
  estimated  a language pack is installed, judgement rests on proxy signals
  rule_based no language pack, only the rule based gates speak for the line

Confidence = tier base (J1 0.90, J2 0.80, J3 0.70, deliberation 0.60, unresolved 0.30)
             - 0.10 per point of spread among the settling votes
             + 0.05 when the ban list hits, + 0.05 when the back-translation flags a calque
             halved when no Pass 2 candidate passed validation, clamped to 0 to 1.

The Markdown follows the house punctuation style (no semicolons, no en or em dashes, no colon
inside a sentence). Model text is rewritten to that style, line texts stay verbatim in code spans.

Usage:
  python report_changes.py verdicts_tr-TR_01.json --locale tr-TR [--rewrites rewrites_tr-TR_01.json] [--budget-log budget.jsonl]

Exit codes: 0 report written, 1 report written and some lines are unresolved or kept their old
text, 2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, emit_report, load_json_data, load_table,
    normalize_locale, resolve_input, run_main, __version__,
)
import budget_report  # noqa: E402
from build_language_pack import LANGPACK_DIR  # noqa: E402
from providers import load_providers_config  # noqa: E402
from text_style import punctuation_problems, sanitize_prose  # noqa: E402

TOOL = "report_changes"
TIER_BASE = {"J1": 0.90, "J2": 0.80, "J3": 0.70, "deliberation": 0.60}
TRUST_TEXT = {
    "measured": "Measured against a professional reference translation",
    "estimated": "Estimated from proxy signals (language pack installed, no professional reference)",
    "rule_based": "Rule based only (no language pack installed)",
}
STATUS_ORDER = ("critical", "unresolved", "rewrite", "rewrite_light", "pass")
NO_OBJECTION = "No objection, the line sounds native to this juror."


def trust_level(pack_dir: Path) -> Tuple[str, Optional[str]]:
    """(A9 level, langpack version) from the pack's trust card and manifest."""
    card = pack_dir / "trust_card.json"
    if not card.is_file():
        return "rule_based", None
    trust = load_json_data(card)
    version = trust.get("langpack_version")
    cal = trust.get("calibration") or {}
    if trust.get("trust_level") == "measured" and (cal.get("gate") or {}).get("passed"):
        return "measured", version
    return "estimated", version


def votes_summary(votes: Sequence[Dict[str, Any]]) -> Dict[str, List[int]]:
    """{tier: [scores in member order]}."""
    out: Dict[str, List[int]] = {}
    for v in sorted(votes, key=lambda x: (str(x.get("tier")), int(x.get("member", 0)))):
        out.setdefault(str(v.get("tier")), []).append(int(v.get("score", 0)))
    return out


def confidence(verdict: Dict[str, Any], rewrite_valid: Optional[bool]) -> float:
    """Confidence that the recommended outcome of a line is right (see module docstring)."""
    if verdict.get("status") == "unresolved":
        base = 0.30
    else:
        base = TIER_BASE.get(str(verdict.get("final_tier")), 0.5)
    settling = votes_summary(verdict.get("votes", [])).get(str(verdict.get("final_tier")), [])
    if settling:
        base -= 0.10 * (max(settling) - min(settling))
    ev = verdict.get("evidence") or {}
    flagged = verdict.get("status") not in ("pass",)
    if flagged and ev.get("ban_hits"):
        base += 0.05
    if flagged and (ev.get("roundtrip") or {}).get("suspect"):
        base += 0.05
    if rewrite_valid is False:
        base *= 0.5
    return round(min(1.0, max(0.0, base)), 2)


def reason_of(verdict: Dict[str, Any]) -> str:
    """One readable reason: the issue type of the settling votes and their first rationale, in house style."""
    tier = verdict.get("final_tier")
    settling = [v for v in verdict.get("votes", []) if v.get("tier") == tier]
    issues = [v.get("issue_type") for v in settling if v.get("issue_type") not in (None, "none")]
    issue = max(set(issues), key=issues.count) if issues else ""
    text = next((r for r in verdict.get("rationales", []) if r), "")
    parts = [p for p in (issue.replace("_", " ") if issue else "", text) if p]
    return sanitize_prose(". ".join(parts)) if parts else ""


def build_report(doc: Dict[str, Any], locale: str, batch: str, *, rewrites: Optional[Dict[str, Any]], sources: Dict[str, Dict[str, str]],
                 pack_dir: Path, budget: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Assemble the B3.8 report document."""
    level, version = trust_level(pack_dir)
    rw = {l["key"]: l for l in (rewrites or {}).get("lines", [])}
    lines: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    counts = {s: 0 for s in STATUS_ORDER}
    for v in doc.get("verdicts", []):
        counts[v.get("status", "pass")] = counts.get(v.get("status", "pass"), 0) + 1
        if v.get("status") == "pass":
            continue
        key = v["key"]
        r = rw.get(key)
        src = sources.get(key, {})
        old = r["old"] if r else src.get("target", "")
        new = r["new"] if r else old
        valid = r["valid"] if r else None
        line = {"key": key, "en": (r or {}).get("en") or src.get("en", ""), "old": old, "new": new, "changed": new != old,
                "status": v["status"], "final_tier": v.get("final_tier"), "score": v.get("score"), "reason": reason_of(v),
                "evidence": v.get("evidence", {}), "confidence": confidence(v, valid), "votes": votes_summary(v.get("votes", [])),
                "rewrite_valid": valid, "decision": ""}
        if src.get("category"):
            line["category"] = src["category"]
        if src.get("speaker"):
            line["speaker"] = src["speaker"]
        lines.append(line)
        if v["status"] == "unresolved":
            unresolved.append({"key": key, "old": old, "proposal": new if new != old else "",
                               "rationales": [sanitize_prose(x) for x in v.get("rationales", [])], "votes": line["votes"]})
    lines.sort(key=lambda l: (STATUS_ORDER.index(l["status"]) if l["status"] in STATUS_ORDER else 9, -l["confidence"], l["key"]))
    header = {"trust_level": level, "trust_text": TRUST_TEXT[level], "langpack_version": version or doc.get("langpack_version"),
              "budget": budget, "jury_stats": doc.get("stats", {}), "halted": doc.get("halted"), "notes": doc.get("notes", [])}
    return {"locale": locale, "batch": batch, "source_file": doc.get("source_file"), "header": header, "summary": counts,
            "changed": sum(1 for l in lines if l["changed"]), "lines": lines, "unresolved": unresolved}


def _code(text: Any, table: bool = True) -> str:
    """Markdown inline code (newlines shown as ' / ', pipes escaped inside table cells, backticks fenced)."""
    t = " / ".join(s for s in str(text).replace("\r", "").split("\n")) if text != "" else ""
    if not t:
        return "(empty)"
    if table:
        t = t.replace("|", "\\|")
    fence = "``" if "`" in t else "`"
    pad = " " if fence == "``" else ""
    return f"{fence}{pad}{t}{pad}{fence}"


def _cell(text: Any) -> str:
    return sanitize_prose(str(text)).replace("|", "/").replace("\n", " ") or "none"


def render_markdown(rep: Dict[str, Any]) -> str:
    """Developer facing Markdown in the house punctuation style."""
    h = rep["header"]
    out = [f"# Change report {rep['locale']} batch {rep['batch']}", ""]
    out += ["| Item | Value |", "|---|---|",
            f"| Trust level | {h['trust_level']}. {_cell(h['trust_text'])} |",
            f"| Language pack | {_code(h['langpack_version']) if h['langpack_version'] else 'none'} |",
            f"| Lines judged | {sum(rep['summary'].values())} |",
            f"| Lines to change | {rep['changed']} |"]
    b = h.get("budget")
    if b:
        cost = f"{b['cost_usd']:.4f} USD" + ("" if b["priced"] else " plus models without a price")
        out.append(f"| Budget | {b['calls']} calls, {b['input_tokens']} tokens in, {b['output_tokens']} tokens out, {cost} |")
    if h.get("halted"):
        out.append(f"| Stopped | {_cell(h['halted'].get('reason', 'budget cap'))} |")
    out += ["", "## Status", "", "| Status | Lines |", "|---|---|"]
    out += [f"| {s} | {n} |" for s, n in rep["summary"].items()]
    out += ["", "## Changes", ""]
    if rep["lines"]:
        out += ["| Key | Old | New | Status | Confidence | Votes | Reason |", "|---|---|---|---|---|---|---|"]
        for l in rep["lines"]:
            votes = ", ".join(f"{t} {'-'.join(str(s) for s in sc)}" for t, sc in l["votes"].items())
            new = _code(l["new"]) if l["changed"] else "unchanged"
            out.append(f"| {_code(l['key'])} | {_code(l['old'])} | {new} | {l['status']} | {l['confidence']:.2f} | {votes} | {_cell(l['reason'])} |")
    else:
        out.append("No line needs a change.")
    out += ["", "## Unresolved lines", ""]
    if rep["unresolved"]:
        out.append("The jury could not settle these lines. Each one comes with the three rationales of the last round.")
        for u in rep["unresolved"]:
            out += ["", f"### {_code(u['key'], table=False)}", "", f"- Current line {_code(u['old'], table=False)}"]
            if u["proposal"]:
                out.append(f"- Proposal {_code(u['proposal'], table=False)}")
            out.append("")
            out += [f"{i}. {_cell(r) if r.strip() else NO_OBJECTION}" for i, r in enumerate(u["rationales"], start=1)]
    else:
        out.append("None.")
    out += ["", "## How to decide", "",
            "Set `decision` to `accept` or `reject` for every line in the JSON report, then store the result with "
            "`tm.py --mode approve`. Accepted lines and kept old lines become approved translation memory.", ""]
    return "\n".join(out)


def load_sources(path: Optional[Path], locale: str) -> Dict[str, Dict[str, str]]:
    """key -> {en, target, category, speaker} from the Pass 1 table (optional)."""
    if path is None:
        return {}
    for col in ("dst", locale, "target"):
        try:
            rows = load_table(path, "en", col, "key")
            return {r.key: {"en": r.src, "target": r.dst, "category": str(r.meta.get("category") or ""),
                            "speaker": str(r.meta.get("speaker") or "")} for r in rows}
        except L10nError:
            continue
    raise L10nError(f"{path}: no target column (dst, {locale} or target)")


def batch_of(path: Path, locale: str) -> str:
    m = re.match(r"verdicts_(.+)\.json$", path.name)
    if m:
        name = m.group(1)
        return name[len(locale) + 1:] if name.startswith(locale + "_") else name
    return path.stem


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
    ap = build_parser()
    args = ap.parse_args()
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
    budget = None
    if args.budget_log:
        recs = budget_report.read_records(budget_report.find_logs(Path(args.budget_log)))
        prices = budget_report.price_table(load_providers_config(Path(args.providers_config) if args.providers_config else None))
        tot = budget_report.aggregate(recs, [], prices)[0]
        budget = {k: tot[k] for k in ("calls", "errors", "input_tokens", "output_tokens", "latency_ms", "cost_usd", "priced", "unpriced_models")}
    pack_dir = (Path(args.langpack_dir) if args.langpack_dir else LANGPACK_DIR) / locale
    batch = args.batch or batch_of(inp, locale)
    rep = build_report(doc, locale, batch, rewrites=rewrites, sources=sources, pack_dir=pack_dir, budget=budget)
    md = render_markdown(rep)
    style = punctuation_problems(md)
    if style:
        raise L10nError(f"internal: generated Markdown breaks the punctuation style at line {style[0][0]} ({style[0][1]})")
    out_dir = Path(args.out_dir) if args.out_dir else inp.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    jpath = out_dir / f"changes_{locale}_{batch}.json"
    mpath = out_dir / f"changes_{locale}_{batch}.md"
    jpath.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mpath.write_text(md, encoding="utf-8")
    attention = len(rep["unresolved"]) + sum(1 for l in rep["lines"] if l["rewrite_valid"] is False)
    exit_code = EXIT_FINDINGS if attention else EXIT_OK
    lines = [f"Change report {locale} batch {batch}: {jpath.name} and {mpath.name} in {out_dir}",
             f"  trust level {rep['header']['trust_level']}, {rep['changed']} line(s) to change, {len(rep['unresolved'])} unresolved",
             f"  Exit code: {exit_code}"]
    payload = {"tool": TOOL, "version": __version__, "json": str(jpath), "markdown": str(mpath), "summary": rep["summary"],
               "changed": rep["changed"], "unresolved": len(rep["unresolved"]), "trust_level": rep["header"]["trust_level"], "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
