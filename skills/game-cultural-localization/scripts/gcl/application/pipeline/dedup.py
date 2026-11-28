"""Context safe intra batch deduplication and approved TM 1.0 short circuit."""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from collections.abc import Callable, Sequence
from typing import Any

from gcl.application.jury.policy import STATUSES, TIERS
from gcl.ports.context import WriterContextView

from .stages import build_pass1_payload_rows

__layer__ = "application"
__pattern__ = "Context Safe Deduplicator"
__owns__ = "context signature deduplication, approved TM short circuit and verdict/rewrite fanout"

_WS_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize text with NFC, collapsed whitespace and case folding."""
    return _WS_RE.sub(" ", unicodedata.normalize("NFC", text or "")).strip().casefold()


def context_signature(row: Any, register: str, wctx: WriterContextView | None) -> tuple[Any, ...]:
    """Full context signature ensuring homographs like 'Play' never merge across places."""
    note = json.dumps(wctx.line_fields(row.key), ensure_ascii=False, sort_keys=True) if wctx is not None else ""
    return (
        normalize_text(row.src),
        register,
        str(row.meta.get("category") or ""),
        str(row.meta.get("speaker") or ""),
        str(row.meta.get("archetype") or ""),
        str(row.meta.get("max_chars") or ""),
        note,
    )


def jury_signature(entry: dict[str, Any]) -> tuple[Any, ...]:
    """Full target + context signature for blind jury deduplication."""
    ctx_blob = json.dumps(entry.get("context") or {}, ensure_ascii=False, sort_keys=True)
    return (
        normalize_text(str(entry.get("target") or "")),
        str(entry.get("register") or ""),
        str(entry.get("category") or ""),
        str(entry.get("speaker") or ""),
        str(entry.get("archetype") or ""),
        str(entry.get("max_chars") or ""),
        ctx_blob,
    )


@dataclass(frozen=True, slots=True)
class DedupEnv:
    """Parameter bundle passed to Pass 1 batch deduplication and TM lookup."""

    locale: str
    register_of: Callable[[Any], str]
    wctx: WriterContextView | None
    tm: Any
    parity: Any
    opts: Any


@dataclass(slots=True)
class Pass1BatchPlan:
    """Partitioned Pass 1 batch separating drafts, approved TM hits and canonical rows."""

    targets: dict[str, str] = field(default_factory=dict)
    tm_verdicts: dict[str, dict[str, Any]] = field(default_factory=dict)
    canon_rows: list[Any] = field(default_factory=list)
    canon_payloads: list[dict[str, Any]] = field(default_factory=list)
    dup_to_canon: dict[str, str] = field(default_factory=dict)
    draft_count: int = 0
    tm_count: int = 0
    dedup_count: int = 0


def _tm_exact_hit(row: Any, dedup_env: DedupEnv) -> dict[str, Any] | None:
    opts = dedup_env.opts
    if not getattr(opts, "tm_shortcircuit", True) or dedup_env.tm is None:
        return None
    if not hasattr(dedup_env.tm, "exact_approved"):
        return None
    hit = dedup_env.tm.exact_approved(
        dedup_env.locale, row.src,
        category=str(row.meta.get("category") or ""),
        speaker=str(row.meta.get("speaker") or ""),
    )
    if not hit:
        return None
    if dedup_env.parity.parity_problems(row.src, hit["dst"], opts.ph_style, opts.tag_style):
        return None
    return hit


def make_tm_verdict(key: str, tm_hit: dict[str, Any]) -> dict[str, Any]:
    """Synthetic J1 pass verdict for an unambiguous approved exact TM match."""
    return {
        "key": key, "final_tier": "J1", "score": 5, "status": "pass", "votes": [],
        "evidence": {"ban_hits": [], "tm_neighbors": [tm_hit], "roundtrip": {"applied": False, "reason": "tm_exact"}},
        "rationales": [],
    }


def plan_pass1_batch(batch: Sequence[Any], dedup_env: DedupEnv) -> Pass1BatchPlan:
    """Partition batch rows into drafts, exact TM hits, deduplicated duplicates and canonical rows."""
    plan = Pass1BatchPlan()
    draft_field = getattr(dedup_env.opts, "draft_field", None)
    seen: dict[tuple[Any, ...], str] = {}
    for row in batch:
        draft = str(row.meta.get(draft_field) or "") if draft_field else ""
        if draft_field and draft.strip():
            plan.targets[row.key] = draft
            plan.draft_count += 1
            continue
        tm_hit = _tm_exact_hit(row, dedup_env)
        if tm_hit is not None:
            plan.targets[row.key] = str(tm_hit["dst"])
            plan.tm_verdicts[row.key] = make_tm_verdict(row.key, tm_hit)
            plan.tm_count += 1
            continue
        sig = context_signature(row, dedup_env.register_of(row), dedup_env.wctx)
        canon_key = seen.get(sig)
        if canon_key is not None:
            plan.dup_to_canon[row.key] = canon_key
            plan.dedup_count += 1
            continue
        seen[sig] = row.key
        plan.canon_rows.append(row)
    plan.canon_payloads = build_pass1_payload_rows(
        plan.canon_rows, dedup_env.locale, dedup_env.register_of, dedup_env.tm, dedup_env.wctx,
    )
    return plan


def expand_pass1_targets(plan: Pass1BatchPlan, translated: dict[str, str], batch: Sequence[Any]) -> dict[str, str]:
    """Fan out canonical translations to all duplicate keys while preserving batch order."""
    pool = {**plan.targets, **translated}
    out: dict[str, str] = {}
    for row in batch:
        k = row.key
        src_k = plan.dup_to_canon.get(k, k)
        out[k] = pool[src_k]
    return out


@dataclass(slots=True)
class JuryBatchPlan:
    """Deduplicated blind jury batch plan skipping TM resolved and duplicate context items."""

    pre_settled: dict[str, dict[str, Any]]
    unique_entries: list[dict[str, Any]]
    dup_to_canon: dict[str, str]


def plan_jury_batch(jentries: Sequence[dict[str, Any]], pre_settled: dict[str, dict[str, Any]]) -> JuryBatchPlan:
    """Deduplicate non settled jury entries sharing target and full blind context."""
    seen: dict[tuple[Any, ...], str] = {}
    unique: list[dict[str, Any]] = []
    dup_to_canon: dict[str, str] = {}
    for entry in jentries:
        k = str(entry["key"])
        if k in pre_settled:
            continue
        sig = jury_signature(entry)
        canon = seen.get(sig)
        if canon is not None:
            dup_to_canon[k] = canon
            continue
        seen[sig] = k
        unique.append(entry)
    return JuryBatchPlan(pre_settled=dict(pre_settled), unique_entries=unique, dup_to_canon=dup_to_canon)


def _clone_verdict(verdict: dict[str, Any], new_key: str) -> dict[str, Any]:
    return {**verdict, "key": new_key, "votes": [{**v, "key": new_key} for v in verdict.get("votes", [])]}


def expand_jury_result(plan: JuryBatchPlan, raw_res: dict[str, Any] | None, full_order: Sequence[str]) -> dict[str, Any]:
    """Merge TM settled and duplicate verdicts back into full batch order."""
    if raw_res is None:
        verdicts = [plan.pre_settled[k] for k in full_order if k in plan.pre_settled]
        stats: dict[str, Any] = {
            "lines": len(verdicts),
            "J1": {"lines": 0, "settled": len(verdicts), "to_J2": 0, "critical_to_J3": 0},
            "status": {s: sum(1 for v in verdicts if v["status"] == s) for s in STATUSES},
            "final_tier": {t: sum(1 for v in verdicts if v["final_tier"] == t) for t in TIERS + ("deliberation",)},
        }
        return {"verdicts": verdicts, "pending": [], "halted": None, "stats": stats}
    by_canon = {v["key"]: v for v in raw_res.get("verdicts", [])}
    verdicts = []
    pending_canon = set(raw_res.get("pending") or [])
    pending: list[str] = []
    for k in full_order:
        if k in plan.pre_settled:
            verdicts.append(plan.pre_settled[k])
        else:
            src_k = plan.dup_to_canon.get(k, k)
            if src_k in by_canon:
                v = by_canon[src_k]
                verdicts.append(v if src_k == k else _clone_verdict(v, k))
            elif src_k in pending_canon:
                pending.append(k)
    stats = dict(raw_res["stats"])
    stats["status"] = {s: sum(1 for v in verdicts if v["status"] == s) for s in STATUSES}
    stats["final_tier"] = {t: sum(1 for v in verdicts if v["final_tier"] == t) for t in TIERS + ("deliberation",)}
    return {"verdicts": verdicts, "pending": pending, "halted": raw_res.get("halted"), "stats": stats}


def expand_pass2_rewrites(rw: dict[str, Any], dup_to_canon: dict[str, str], batch_order: Sequence[str]) -> dict[str, Any]:
    """Expand canonical Pass 2 rewrite lines and critique entries onto duplicate siblings."""
    if not dup_to_canon:
        return rw
    lines_by_key = {l["key"]: l for l in rw.get("lines", [])}
    crit_entries = (rw.get("critique") or {}).get("entries") or []
    crit_by_key = {e["key"]: e for e in crit_entries}
    new_lines: list[dict[str, Any]] = []
    new_crit: list[dict[str, Any]] = []
    for k in batch_order:
        src_k = dup_to_canon.get(k, k)
        if src_k in lines_by_key:
            line = lines_by_key[src_k]
            new_lines.append(line if src_k == k else {**line, "key": k})
        if src_k in crit_by_key:
            c = crit_by_key[src_k]
            new_crit.append(c if src_k == k else {**c, "key": k})
    critique = dict(rw.get("critique") or {})
    critique["entries"] = new_crit
    critique["summary"] = {
        "total": len(batch_order),
        "flagged": len(new_crit),
        "critical": sum(1 for e in new_crit if e.get("score", 5) <= 2),
    }
    return {**rw, "lines": new_lines, "critique": critique}
