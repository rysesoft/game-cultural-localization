"""Developer change report builder, confidence scoring and Markdown renderer."""

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from gcl.domain.errors import L10nError
from gcl.domain.house_style import sanitize_prose

__layer__ = "application"
__pattern__ = "Application Service"
__owns__ = "trust levels, confidence scoring, change report JSON assembly and house style Markdown"

TIER_BASE = {"J1": 0.90, "J2": 0.80, "J3": 0.70, "deliberation": 0.60}
TRUST_TEXT = {
    "measured": "Measured against a professional reference translation",
    "estimated": "Estimated from proxy signals (language pack installed, no professional reference)",
    "rule_based": "Rule based only (no language pack installed)",
}
STATUS_ORDER = ("critical", "unresolved", "rewrite", "rewrite_light", "pass")
NO_OBJECTION = "No objection, the line sounds native to this juror."
SECONDARY_FAILED = (
    "The jurors passed the pairwise gate, they pick the native line over the literal one. Their absolute scores "
    "did not pass the second check, a literal line still averages above 3 for some of them, so read the score "
    "of a line as a ranking and not as a grade."
)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise L10nError(f"{path}: invalid JSON ({exc})")


def trust_level(pack_dir: Path) -> tuple[str, str | None]:
    """(A9 level, langpack version) from the pack's trust card and manifest."""
    card = pack_dir / "trust_card.json"
    if not card.is_file():
        return "rule_based", None
    trust = _read_json(card)
    version = trust.get("langpack_version")
    cal = trust.get("calibration") or {}
    if trust.get("trust_level") == "measured" and (cal.get("gate") or {}).get("passed"):
        return "measured", version
    return "estimated", version


def secondary_passed(pack_dir: Path) -> bool | None:
    """Calibration secondary check (native > 4.5, literal < 3), None when uncalibrated."""
    card = pack_dir / "trust_card.json"
    if not card.is_file():
        return None
    cal = (_read_json(card).get("calibration") or {})
    passed = (cal.get("secondary") or {}).get("passed")
    return passed if isinstance(passed, bool) else None


def votes_summary(votes: Sequence[dict[str, Any]]) -> dict[str, list[int]]:
    """{tier: [scores in member order]}."""
    out: dict[str, list[int]] = {}
    for v in sorted(votes, key=lambda x: (str(x.get("tier")), int(x.get("member", 0)))):
        out.setdefault(str(v.get("tier")), []).append(int(v.get("score", 0)))
    return out


def confidence(verdict: dict[str, Any], rewrite_valid: bool | None) -> float:
    """Confidence score that the recommended outcome of a line is accurate."""
    base = 0.30 if verdict.get("status") == "unresolved" else TIER_BASE.get(str(verdict.get("final_tier")), 0.5)
    settling = votes_summary(verdict.get("votes", [])).get(str(verdict.get("final_tier")), [])
    if settling:
        base -= 0.10 * (max(settling) - min(settling))
    ev = verdict.get("evidence") or {}
    flagged = verdict.get("status") != "pass"
    if flagged and ev.get("ban_hits"):
        base += 0.05
    if flagged and (ev.get("roundtrip") or {}).get("suspect"):
        base += 0.05
    if rewrite_valid is False:
        base *= 0.5
    return round(min(1.0, max(0.0, base)), 2)


def reason_of(verdict: dict[str, Any]) -> str:
    """One readable reason combining settling issue type and first rationale in house style."""
    tier = verdict.get("final_tier")
    settling = [v for v in verdict.get("votes", []) if v.get("tier") == tier]
    issues = [v.get("issue_type") for v in settling if v.get("issue_type") not in (None, "none")]
    issue = max(set(issues), key=issues.count) if issues else ""
    text = next((r for r in verdict.get("rationales", []) if r), "")
    parts = [p for p in (issue.replace("_", " ") if issue else "", text) if p]
    return sanitize_prose(". ".join(parts)) if parts else ""


def _report_line(v: dict[str, Any], rw: dict[str, dict[str, Any]], sources: dict[str, dict[str, str]]) -> dict[str, Any]:
    key = v["key"]
    r = rw.get(key)
    src = sources.get(key, {})
    old = r["old"] if r else src.get("target", "")
    new = r["new"] if r else old
    valid = r["valid"] if r else None
    line: dict[str, Any] = {
        "key": key, "en": (r or {}).get("en") or src.get("en", ""), "old": old, "new": new,
        "changed": new != old, "status": v["status"], "final_tier": v.get("final_tier"),
        "score": v.get("score"), "reason": reason_of(v), "evidence": v.get("evidence", {}),
        "confidence": confidence(v, valid), "votes": votes_summary(v.get("votes", [])),
        "rewrite_valid": valid, "decision": "",
    }
    for meta_key in ("category", "speaker"):
        if src.get(meta_key):
            line[meta_key] = src[meta_key]
    return line


def build_report(
    doc: dict[str, Any],
    locale: str,
    batch: str,
    *,
    rewrites: dict[str, Any] | None,
    sources: dict[str, dict[str, str]],
    pack_dir: Path,
    budget: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble the B3.8 report document."""
    level, version = trust_level(pack_dir)
    rw = {l["key"]: l for l in (rewrites or {}).get("lines", [])}
    lines: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    counts = {s: 0 for s in STATUS_ORDER}
    for v in doc.get("verdicts", []):
        st = v.get("status", "pass")
        counts[st] = counts.get(st, 0) + 1
        if st == "pass":
            continue
        line = _report_line(v, rw, sources)
        lines.append(line)
        if st == "unresolved":
            unresolved.append({
                "key": line["key"], "old": line["old"],
                "proposal": line["new"] if line["changed"] else "",
                "rationales": [sanitize_prose(x) for x in v.get("rationales", [])],
                "votes": line["votes"],
            })
    lines.sort(key=lambda l: (STATUS_ORDER.index(l["status"]) if l["status"] in STATUS_ORDER else 9, -l["confidence"], l["key"]))
    secondary = secondary_passed(pack_dir) if level == "measured" else None
    header = {
        "trust_level": level, "trust_text": TRUST_TEXT[level] + (". " + SECONDARY_FAILED if secondary is False else ""),
        "secondary_passed": secondary, "langpack_version": version or doc.get("langpack_version"),
        "budget": budget, "jury_stats": doc.get("stats", {}), "halted": doc.get("halted"), "notes": doc.get("notes", []),
    }
    return {
        "locale": locale, "batch": batch, "source_file": doc.get("source_file"), "header": header,
        "summary": counts, "changed": sum(1 for l in lines if l["changed"]), "lines": lines, "unresolved": unresolved,
    }


def _code(text: Any, table: bool = True) -> str:
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


def render_markdown(rep: dict[str, Any]) -> str:
    """Developer facing Markdown in the house punctuation style."""
    h = rep["header"]
    out = [
        f"# Change report {rep['locale']} batch {rep['batch']}", "", "| Item | Value |", "|---|---|",
        f"| Trust level | {h['trust_level']}. {_cell(h['trust_text'])} |",
        f"| Language pack | {_code(h['langpack_version']) if h['langpack_version'] else 'none'} |",
        f"| Lines judged | {sum(rep['summary'].values())} |",
        f"| Lines to change | {rep['changed']} |",
    ]
    b = h.get("budget")
    if b:
        cost = f"{b['cost_usd']:.4f} USD" + ("" if b["priced"] else " plus models without a price")
        out.append(f"| Budget | {b['calls']} calls, {b['input_tokens']} tokens in, {b['output_tokens']} tokens out, {cost} |")
    if h.get("halted"):
        out.append(f"| Stopped | {_cell(h['halted'].get('reason', 'budget cap'))} |")
    out += ["", "## Status", "", "| Status | Lines |", "|---|---|"] + [f"| {s} | {n} |" for s, n in rep["summary"].items()]
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
            out += [""] + [f"{i}. {_cell(r) if r.strip() else NO_OBJECTION}" for i, r in enumerate(u["rationales"], start=1)]
    else:
        out.append("None.")
    out += [
        "", "## How to decide", "",
        "Set `decision` to `accept` or `reject` for every line in the JSON report, then store the result with "
        "`tm.py --mode approve`. Accepted lines and kept old lines become approved translation memory.", "",
    ]
    return "\n".join(out)


def load_sources_with(path: Path | None, locale: str, table_loader: Callable[..., Any]) -> dict[str, dict[str, str]]:
    """Load key -> {en, target, category, speaker} using an injected TableFormat loader."""
    if path is None:
        return {}
    for col in ("dst", locale, "target"):
        try:
            rows = table_loader(path, "en", col, "key")
            return {
                r.key: {"en": r.src, "target": r.dst, "category": str(r.meta.get("category") or ""), "speaker": str(r.meta.get("speaker") or "")}
                for r in rows
            }
        except L10nError:
            continue
    raise L10nError(f"{path}: no target column (dst, {locale} or target)")


def batch_of(path: Path, locale: str) -> str:
    m = re.match(r"verdicts_(.+)\.json$", path.name)
    if m:
        name = m.group(1)
        return name[len(locale) + 1:] if name.startswith(locale + "_") else name
    return path.stem
