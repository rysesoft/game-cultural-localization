"""Juror vote normalization, everyday word filtering and tier cap rule."""

import re
from collections.abc import Sequence
from typing import Any

from gcl.domain.models import JurorVote
from gcl.domain.specifications import apply_everyday_policy

from .prompts import EVERYDAY_CAP, EVERYDAY_MIN_JURORS, ISSUE_TYPES

__layer__ = "application"
__pattern__ = "Domain Policy Bridge"
__owns__ = "raw vote normalization, odd word verification and everyday tier score cap"


def normalize_vote(item: dict[str, Any]) -> dict[str, Any] | None:
    """Coerce a raw model vote dict into canonical fields or return None."""
    raw = item.get("score")
    try:
        score = int(raw) if not isinstance(raw, bool) and float(raw) == int(float(raw)) else None
    except (TypeError, ValueError):
        score = None
    if score is None or not 1 <= score <= 5:
        return None
    it = str(item.get("issue_type") or ("none" if score == 5 else "other"))
    it = "other" if it not in ISSUE_TYPES else it
    it = "none" if score == 5 else it
    odd = item.get("odd_words") or []
    if isinstance(odd, str):
        odd = re.split(r"[,;\n]", odd)
    words = [str(w).strip() for w in odd if isinstance(w, (str, int, float)) and str(w).strip()] if isinstance(odd, list) else []
    return {
        "score": score, "issue_type": it, "reason": str(item.get("reason") or ""),
        "suggested": str(item.get("suggested") or ""), "odd_words": words,
    }


def everyday_check(vote: dict[str, Any], target: str) -> dict[str, Any]:
    """Keep only odd words genuinely present in target text (mutates vote dict)."""
    low = str(target).casefold()
    words: list[str] = []
    for raw in vote.get("odd_words") or []:
        w = str(raw).strip().strip("\"'.,!?")
        if w and any(ch.isalpha() for ch in w) and not any(ch in w for ch in "{}<>%[]") and w.casefold() in low and w not in words:
            words.append(w)
    vote["odd_words"] = words[:10]
    return vote


def everyday_rule(votes: Sequence[dict[str, Any]]) -> bool:
    """Apply apply_everyday_policy across tier vote dicts in place."""
    domain_votes = [
        JurorVote(
            score=int(v["score"]),
            issue_type=str(v.get("issue_type") or "none"),
            reason=str(v.get("reason") or ""),
            suggested=str(v.get("suggested") or ""),
            odd_words=tuple(str(w) for w in (v.get("odd_words") or ())),
        )
        for v in votes
    ]
    updated, applied = apply_everyday_policy(domain_votes, cap=EVERYDAY_CAP, min_jurors=EVERYDAY_MIN_JURORS)
    if not applied:
        return False
    for target_dict, new_vote in zip(votes, updated):
        target_dict["score"] = new_vote.score
        target_dict["issue_type"] = new_vote.issue_type
        target_dict["reason"] = new_vote.reason
    return True
