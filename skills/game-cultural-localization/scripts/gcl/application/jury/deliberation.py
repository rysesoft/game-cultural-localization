"""Anonymized J3 deliberation re-voting and majority decision domain service."""
from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from gcl.application.tasks.concrete_tasks import revote, revote_many
from gcl.application.tasks.vote_codec import everyday_rule
from gcl.domain.errors import L10nError

from .policy import STATUSES, juror_view, status_for

__layer__ = "application"
__pattern__ = "Domain Service"
__owns__ = "vendor name anonymization, target only evidence packaging and J3 deliberation voting"

LABELS: Tuple[str, ...] = ("A", "B")
GENERIC_NAMES: Tuple[str, ...] = (
    "anthropic", "claude", "haiku", "sonnet", "opus", "google", "gemini", "hydrogen", "neon", "carbon",
    "deepseek", "openai", "gpt", "llama", "mistral", "qwen", "v4 pro", "v4 flash", "v4-pro", "v4-flash",
    "v4.1 flash", "v4.1-flash", "flash", "pro",
)


def name_scrubber(config: Any) -> "re.Pattern[str]":
    """Build case insensitive regex matching model ids, aliases and family names."""
    names = set(GENERIC_NAMES)
    for spec in config.models.values():
        names.update({spec.alias.lower(), spec.id.lower(), spec.provider.lower()})
    alts = sorted(names, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in alts) + r")(?![\w-])", re.IGNORECASE)


def anonymize(text: str, scrub: "re.Pattern[str]") -> str:
    """Replace model and vendor identifiers with 'another juror'."""
    out = scrub.sub("another juror", text or "")
    return re.sub(r"another juror(?:[\s-]+another juror)+", "another juror", out)


def evidence_package(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Extract target only ban hits, approved TM target texts and roundtrip signals."""
    tm = [n for n in evidence.get("tm_neighbors", []) if n.get("status", "approved") == "approved"][:3]
    rt = evidence.get("roundtrip") or {}
    return {
        "ban_hits": [{"rule": b.get("rule"), "message": b.get("message")} for b in evidence.get("ban_hits", [])],
        "tm_neighbors": [
            {"target": n.get("dst", n.get("target", "")), "category": n.get("category", ""), "similarity": n.get("similarity")}
            for n in tm
        ],
        "roundtrip": {k: rt[k] for k in ("applied", "calque_score", "suspect") if k in rt},
    }


def decide(scores: Sequence[int]) -> Optional[int]:
    """Return score holding a strict majority of at least two votes, else None."""
    score, count = Counter(scores).most_common(1)[0]
    return score if count >= 2 else None


def revote_payload(
    entry: Dict[str, Any],
    by_member: Dict[int, Dict[str, Any]],
    member_index: int,
    package: Dict[str, Any],
    scrub: "re.Pattern[str]",
) -> Dict[str, Any]:
    """Build anonymized re-vote payload showing own first vote and other jurors' reasons."""
    own = by_member.get(member_index)
    if own is None:
        raise L10nError(f"deliberation for '{entry['key']}': no first J3 vote of member {member_index}")
    view = juror_view(entry)
    others = [by_member[i] for i in sorted(by_member) if i != member_index]
    return {
        "key": entry["key"],
        "target": view["target"],
        "context": {k: v for k, v in view.items() if k not in ("key", "target")},
        "own": {k: own[k] for k in ("score", "issue_type", "reason", "suggested")},
        "others": [
            {"juror": LABELS[i], "score": o["score"], "issue_type": o["issue_type"],
             "reason": anonymize(o["reason"], scrub), "suggested": o.get("suggested", "")}
            for i, o in enumerate(others)
        ],
        "evidence": package,
    }


def decide_line(by_member: Dict[int, Dict[str, Any]], revotes: List[Dict[str, Any]], critical_max: int = 2) -> Dict[str, Any]:
    """Compute deliberation verdict honoring everyday cap and critical holdout rule."""
    everyday_rule(revotes)
    scores = [v["score"] for v in revotes]
    majority = decide(scores)
    first = [by_member[i]["score"] for i in sorted(by_member)]
    info: Dict[str, Any] = {"first": first, "revote": scores, "majority": majority}
    if majority is None:
        return {"score": min(scores), "status": "unresolved", "rationales": [v["reason"] for v in revotes], "revotes": revotes, "deliberation": info}
    if min(scores) <= critical_max < majority:
        info["critical_holdout"] = True
        return {"score": min(scores), "status": "unresolved", "rationales": [v["reason"] for v in revotes], "revotes": revotes, "deliberation": info}
    return {"score": majority, "status": status_for(majority), "rationales": [v["reason"] for v in revotes], "revotes": revotes, "deliberation": info}


def deliberate_line(
    entry: Dict[str, Any],
    j3_votes: Sequence[Dict[str, Any]],
    evidence: Dict[str, Any],
    members: Sequence[Any],
    locale: str,
    system: str,
    scrub: "re.Pattern[str]",
    **kw: Any,
) -> Dict[str, Any]:
    """Run synchronous single line deliberation across J3 members."""
    critical_max = int(kw.get("critical_max", 2))
    by_member = {int(v["member"]): v for v in j3_votes}
    package = evidence_package(evidence)
    revotes: List[Dict[str, Any]] = []
    for m in members:
        v = revote(m.provider, revote_payload(entry, by_member, m.index, package, scrub), locale, system=system)
        revotes.append({"key": entry["key"], "tier": "deliberation", "member": m.index, "family": m.family, "model": m.provider.model, **v})
    return decide_line(by_member, revotes, critical_max)


def deliberate_lines(
    items: Sequence[Tuple[Dict[str, Any], Sequence[Dict[str, Any]], Dict[str, Any]]],
    members: Sequence[Any],
    locale: str,
    system: str,
    scrub: "re.Pattern[str]",
    **kw: Any,
) -> Dict[str, Dict[str, Any]]:
    """Run batched multi line deliberation re-votes in parallel across J3 members."""
    if not items:
        return {}
    critical_max = int(kw.get("critical_max", 2))
    workers = int(kw.get("workers", 1))
    memo = kw.get("memo")
    firsts = {e["key"]: {int(v["member"]): v for v in votes} for e, votes, _ev in items}
    payloads = {m.index: [revote_payload(e, firsts[e["key"]], m.index, evidence_package(ev), scrub) for e, _v, ev in items] for m in members}

    def member_votes(m: Any) -> Dict[str, Dict[str, Any]]:
        return revote_many(m.provider, payloads[m.index], locale, system=system, workers=workers, memo=memo)

    if workers > 1 and len(members) > 1:
        with ThreadPoolExecutor(max_workers=len(members)) as ex:
            got = dict(zip([m.index for m in members], ex.map(member_votes, members)))
    else:
        got = {m.index: member_votes(m) for m in members}
    out: Dict[str, Dict[str, Any]] = {}
    for e, _votes, _ev in items:
        k = e["key"]
        revotes = [{"key": k, "tier": "deliberation", "member": m.index, "family": m.family, "model": m.provider.model, **got[m.index][k]} for m in members]
        out[k] = decide_line(firsts[k], revotes, critical_max)
    return out


def make_deliberator(router: Any, locale: str, system: str) -> Any:
    """Build deliberator callable with attached .many() batch helper."""
    members = router.jury("J3")
    scrub = name_scrubber(router.config)
    critical_max = int(router.config.agreement.get("critical_max", 2))

    def run(entry: Dict[str, Any], j3_votes: List[Dict[str, Any]], evidence: Dict[str, Any]) -> Dict[str, Any]:
        return deliberate_line(entry, j3_votes, evidence, members, locale, system, scrub, critical_max=critical_max)

    def many(items: Sequence[Tuple[Dict[str, Any], Sequence[Dict[str, Any]], Dict[str, Any]]], workers: int = 1, memo: Any = None) -> Dict[str, Dict[str, Any]]:
        return deliberate_lines(items, members, locale, system, scrub, critical_max=critical_max, workers=workers, memo=memo)

    run.many = many  # type: ignore[attr-defined]
    return run


def deliberate_verdicts(doc: Dict[str, Any], entries: Iterable[Dict[str, Any]], router: Any, locale: str, system: str) -> Dict[str, int]:
    """Deliberate all unresolved J3 verdicts inside doc in place and update stats."""
    by_key = {e["key"]: e for e in entries}
    run = make_deliberator(router, locale, system)
    counts = {"deliberated": 0, "resolved": 0, "unresolved": 0}
    todo = [v for v in doc.get("verdicts", []) if v.get("status") == "unresolved" and v.get("final_tier") == "J3"]
    for v in todo:
        if v["key"] not in by_key:
            raise L10nError(f"verdict '{v['key']}' is not in the blind slice")
    outcomes = run.many([(by_key[v["key"]], [x for x in v.get("votes", []) if x.get("tier") == "J3"], v.get("evidence", {})) for v in todo])
    for v in todo:
        res = outcomes[v["key"]]
        v["votes"] = list(v.get("votes", [])) + res["revotes"]
        v.update({"final_tier": "deliberation", "score": res["score"], "status": res["status"], "rationales": res["rationales"], "deliberation": res["deliberation"]})
        counts["deliberated"] += 1
        counts["resolved" if res["status"] != "unresolved" else "unresolved"] += 1
    if counts["deliberated"]:
        stats = doc.setdefault("stats", {})
        stats["status"] = {s: sum(1 for v in doc["verdicts"] if v["status"] == s) for s in STATUSES}
        stats.setdefault("final_tier", {})["deliberation"] = sum(1 for v in doc["verdicts"] if v["final_tier"] == "deliberation")
        stats["final_tier"]["J3"] = sum(1 for v in doc["verdicts"] if v["final_tier"] == "J3")
        stats["deliberation"] = counts
    return counts
