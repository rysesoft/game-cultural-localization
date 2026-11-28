"""Jury agreement specifications, line status mapping, escalation tally and blind juror view."""

from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any

from gcl.domain.models import JuryTier, LineStatus
from gcl.domain.specifications import CleanLightPassSpec, CriticalVoteSpec, MaxSpreadSpec, TierPassSpec

__layer__ = "application"
__pattern__ = "Specification Policy"
__owns__ = "J1-J3 agreement evaluation, EscalationTally and source free juror_view"

TIERS: tuple[str, ...] = tuple(JuryTier)
SOURCE_COLUMNS: tuple[str, ...] = ("en", "source", "src", "english")
CONTEXT_FIELDS: tuple[str, ...] = ("register", "category", "speaker", "archetype", "context")
STATUSES: tuple[str, ...] = tuple(LineStatus)


@dataclass(slots=True)
class EscalationTally:
    """Cumulative judged, J2 and J3 escalation counts across batches of one run."""

    lines: int = 0
    to_j2: int = 0
    to_j3: int = 0


def classify(scores: Sequence[int], agreement: dict[str, int]) -> str:
    """Classify tier votes into 'critical', 'pass' or 'escalate' via Specifications."""
    if CriticalVoteSpec(agreement["critical_max"]).is_satisfied_by(scores):
        return "critical"
    if TierPassSpec(agreement["pass_min"], agreement["max_spread"]).is_satisfied_by(scores):
        return "pass"
    return "escalate"


def agrees(scores: Sequence[int], agreement: dict[str, int]) -> bool:
    """True when J3 vote spread fits within configured max_spread."""
    return MaxSpreadSpec(agreement["max_spread"]).is_satisfied_by(scores)


def status_for(score: int) -> str:
    """Map settled numeric score to canonical line workflow status."""
    match score:
        case s if s >= 5:
            return LineStatus.PASS
        case 4:
            return LineStatus.REWRITE_LIGHT
        case 3:
            return LineStatus.REWRITE
        case _:
            return LineStatus.CRITICAL


def juror_view(entry: dict[str, Any]) -> dict[str, Any]:
    """Filter entry to key, target and neutral context fields allowed for blind jurors."""
    view: dict[str, Any] = {"key": entry["key"], "target": entry["target"]}
    for k in CONTEXT_FIELDS:
        if entry.get(k) not in (None, ""):
            view[k] = entry[k]
    return view


def is_clean_light_pass(votes: Sequence[dict[str, Any]], ban_hits: Sequence[Any]) -> bool:
    """True for clean [5, 5, 4] votes with zero odd words and zero ban hits."""
    scores = [int(v["score"]) for v in votes]
    odd_count = sum(len(v.get("odd_words") or []) for v in votes)
    return CleanLightPassSpec().is_satisfied_by((scores, odd_count, len(ban_hits)))
