"""Jury agreement specifications, line status mapping, escalation tally and blind juror view."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Sequence, Tuple

from gcl.domain.specifications import CleanLightPassSpec, CriticalVoteSpec, MaxSpreadSpec, TierPassSpec

__layer__ = "application"
__pattern__ = "Specification Policy"
__owns__ = "J1-J3 agreement evaluation, EscalationTally and source free juror_view"

TIERS: Tuple[str, ...] = ("J1", "J2", "J3")
SOURCE_COLUMNS: Tuple[str, ...] = ("en", "source", "src", "english")
CONTEXT_FIELDS: Tuple[str, ...] = ("register", "category", "speaker", "archetype", "context")
STATUSES: Tuple[str, ...] = ("pass", "rewrite_light", "rewrite", "critical", "unresolved")


@dataclass
class EscalationTally:
    """Cumulative judged, J2 and J3 escalation counts across batches of one run."""

    lines: int = 0
    to_j2: int = 0
    to_j3: int = 0


def classify(scores: Sequence[int], agreement: Dict[str, int]) -> str:
    """Classify tier votes into 'critical', 'pass' or 'escalate' via Specifications."""
    if CriticalVoteSpec(agreement["critical_max"]).is_satisfied_by(scores):
        return "critical"
    if TierPassSpec(agreement["pass_min"], agreement["max_spread"]).is_satisfied_by(scores):
        return "pass"
    return "escalate"


def agrees(scores: Sequence[int], agreement: Dict[str, int]) -> bool:
    """True when J3 vote spread fits within configured max_spread."""
    return MaxSpreadSpec(agreement["max_spread"]).is_satisfied_by(scores)


def status_for(score: int) -> str:
    """Map settled numeric score to canonical line workflow status."""
    if score >= 5:
        return "pass"
    if score == 4:
        return "rewrite_light"
    if score == 3:
        return "rewrite"
    return "critical"


def juror_view(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Filter entry to key, target and neutral context fields allowed for blind jurors."""
    view: Dict[str, Any] = {"key": entry["key"], "target": entry["target"]}
    for k in CONTEXT_FIELDS:
        if entry.get(k) not in (None, ""):
            view[k] = entry[k]
    return view


def is_clean_light_pass(votes: Sequence[Dict[str, Any]], ban_hits: Sequence[Any]) -> bool:
    """True for clean [5, 5, 4] votes with zero odd words and zero ban hits."""
    scores = [int(v["score"]) for v in votes]
    odd_count = sum(len(v.get("odd_words") or []) for v in votes)
    return CleanLightPassSpec().is_satisfied_by((scores, odd_count, len(ban_hits)))
