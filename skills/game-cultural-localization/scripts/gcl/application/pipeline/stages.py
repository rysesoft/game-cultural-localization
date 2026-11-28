"""Pure application stage helpers for Phase 1 payload prep, parity guard and outputs."""

import json
from pathlib import Path
from collections.abc import Callable, Sequence
from typing import Any

from gcl.domain.models import Row
from gcl.ports.context import WriterContextView
from gcl.ports.formats import TokenParityPort
from gcl.ports.storage import TMQuery

__layer__ = "application"
__pattern__ = "Stage Helpers"
__owns__ = "Pass 1 RAG payload assembly, token parity escalation guard and batch artifact writing"


def send_broken_lines_to_pass2(
    res: dict[str, Any],
    targets: dict[str, str],
    sources: dict[str, str],
    ph_style: str,
    tag_style: str,
    parity: TokenParityPort,
) -> int:
    """Flag lines whose placeholders or rich text tags differ from source for mandatory Pass 2 repair."""
    counts = res["stats"].get("status", {})
    sent = 0
    for v in res["verdicts"]:
        problems = parity.parity_problems(sources.get(v["key"], ""), targets.get(v["key"], ""), ph_style, tag_style)
        if not problems:
            continue
        v.setdefault("evidence", {})["parity"] = problems
        v["rationales"] = [
            f"the line breaks placeholder or tag parity with the source line ({'. '.join(problems)})"
        ] + list(v.get("rationales", []))
        if v.get("status") in ("pass", "rewrite_light"):
            counts[v["status"]] = counts.get(v["status"], 1) - 1
            counts["rewrite"] = counts.get("rewrite", 0) + 1
            v["status"], v["score"] = "rewrite", min(int(v.get("score", 3)), 3)
        sent += 1
    return sent


def build_pass1_payload_rows(
    batch: Sequence[Row],
    locale: str,
    register_of: Callable[[Row], str],
    tm: Any = None,
    wctx: WriterContextView | None = None,
) -> list[dict[str, Any]]:
    """Build enriched Pass 1 row dicts including optional TM neighbors and WriterContextView notes."""
    out: list[dict[str, Any]] = []
    for r in batch:
        pr: dict[str, Any] = {"key": r.key, "source": r.src, "register": register_of(r)}
        for k in ("category", "speaker", "archetype", "max_chars"):
            if r.meta.get(k) not in (None, ""):
                pr[k] = r.meta[k]
        if tm is not None:
            nb = _tm_lookup(tm, locale, r.src, str(r.meta.get("category") or ""), str(r.meta.get("speaker") or ""), k=3)
            if nb:
                pr["tm"] = [{"source": x["src"], "target": x["dst"], "similarity": x["similarity"]} for x in nb]
        if wctx is not None:
            wfields = wctx.line_fields(r.key)
            if wfields:
                pr["context"] = wfields
        out.append(pr)
    return out


def _tm_lookup(tm: Any, locale: str, text: str, category: str, speaker: str, *, k: int = 5, exclude_key: str | None = None) -> list[dict[str, Any]]:
    if hasattr(tm, "query_neighbors"):
        return tm.query_neighbors(TMQuery(locale=locale, text=text, category=category, speaker=speaker, k=k, exclude_key=exclude_key))
    return tm.neighbors(locale, text, category=category, speaker=speaker, k=k, exclude_key=exclude_key)


def write_verdict_doc(
    vpath: Path,
    locale: str,
    source_name: str,
    info: dict[str, Any],
    res: dict[str, Any],
    notes: Sequence[str],
) -> dict[str, Any]:
    """Serialize verdict artifact for one batch."""
    doc = {
        "locale": locale, "source_file": source_name, "langpack_version": info.get("langpack_version"),
        "prompt": {
            "warmup_lines": info.get("warmup_lines", 0), "shots": info.get("shots", 0),
            "context_map": info.get("context_map"), "context_lines": info.get("context_lines", 0),
        },
        "stats": res["stats"], "halted": res["halted"], "verdicts": res["verdicts"],
        "pending": res["pending"], "notes": list(notes),
    }
    vpath.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


def write_final_batch(final_path: Path, p1_rows: Sequence[dict[str, Any]], rw: dict[str, Any], res: dict[str, Any], locale: str) -> int:
    """Apply confirmed Pass 2 rewrites into final_batch_NN.json and return actual change count."""
    status_by_key = {v["key"]: v["status"] for v in res["verdicts"]}
    applied = {
        l["key"]: l["new"] for l in rw["lines"]
        if l["valid"] and status_by_key.get(l["key"]) != "unresolved" and l["new"] != l["old"]
    }
    out_rows = [{**row, locale: applied.get(row["key"], row[locale])} for row in p1_rows]
    final_path.write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(applied)
