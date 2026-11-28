"""Composable Specification pattern for jury agreement, everyday word cap and lint filtering."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, List, Sequence, Set, Tuple, TypeVar

from .models import JurorVote

__layer__ = "domain"
__pattern__ = "Specification"
__owns__ = "composable boolean rules for jury agreement, everyday cap and rule scoping"

T = TypeVar("T")


class Specification(ABC, Generic[T]):
    """Boolean business rule supporting &, | and ~ composition."""

    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool:
        """Evaluate the specification on candidate."""

    def __and__(self, other: "Specification[T]") -> "Specification[T]":
        return _AndSpec(self, other)

    def __or__(self, other: "Specification[T]") -> "Specification[T]":
        return _OrSpec(self, other)

    def __invert__(self) -> "Specification[T]":
        return _NotSpec(self)


class _AndSpec(Specification[T]):
    def __init__(self, left: Specification[T], right: Specification[T]) -> None:
        self.left, self.right = left, right

    def is_satisfied_by(self, candidate: T) -> bool:
        return self.left.is_satisfied_by(candidate) and self.right.is_satisfied_by(candidate)


class _OrSpec(Specification[T]):
    def __init__(self, left: Specification[T], right: Specification[T]) -> None:
        self.left, self.right = left, right

    def is_satisfied_by(self, candidate: T) -> bool:
        return self.left.is_satisfied_by(candidate) or self.right.is_satisfied_by(candidate)


class _NotSpec(Specification[T]):
    def __init__(self, inner: Specification[T]) -> None:
        self.inner = inner

    def is_satisfied_by(self, candidate: T) -> bool:
        return not self.inner.is_satisfied_by(candidate)


class CriticalVoteSpec(Specification[Sequence[int]]):
    """True when at least one juror scored at or below critical_max."""

    def __init__(self, critical_max: int = 2) -> None:
        self.critical_max = critical_max

    def is_satisfied_by(self, candidate: Sequence[int]) -> bool:
        return min(candidate) <= self.critical_max


class MinScoreSpec(Specification[Sequence[int]]):
    """True when every score meets pass_min."""

    def __init__(self, pass_min: int = 4) -> None:
        self.pass_min = pass_min

    def is_satisfied_by(self, candidate: Sequence[int]) -> bool:
        return min(candidate) >= self.pass_min


class MaxSpreadSpec(Specification[Sequence[int]]):
    """True when max minus min stays within max_spread."""

    def __init__(self, max_spread: int = 1) -> None:
        self.max_spread = max_spread

    def is_satisfied_by(self, candidate: Sequence[int]) -> bool:
        return max(candidate) - min(candidate) <= self.max_spread


class TierPassSpec(Specification[Sequence[int]]):
    """Composite jury pass rule combining MinScoreSpec and MaxSpreadSpec."""

    def __init__(self, pass_min: int = 4, max_spread: int = 1) -> None:
        self._rule = MinScoreSpec(pass_min) & MaxSpreadSpec(max_spread)

    def is_satisfied_by(self, candidate: Sequence[int]) -> bool:
        return self._rule.is_satisfied_by(candidate)


class CleanLightPassSpec(Specification[Tuple[Sequence[int], int, int]]):
    """True for clean [5, 5, 4] votes carrying zero odd words and zero ban hits."""

    def is_satisfied_by(self, candidate: Tuple[Sequence[int], int, int]) -> bool:
        scores, odd_count, ban_count = candidate
        return sorted(scores) == [4, 5, 5] and odd_count == 0 and ban_count == 0


class RuleAppliesSpec(Specification[Set[str]]):
    """Decide whether a lint rule matches a row context tag set."""

    def __init__(self, rule_context: str, skip_contexts: Sequence[str] = ()) -> None:
        self.rule_context = rule_context
        self.skip_contexts = set(skip_contexts)

    def is_satisfied_by(self, candidate: Set[str]) -> bool:
        if self.skip_contexts & candidate:
            return False
        if self.rule_context == "any":
            return True
        if self.rule_context in ("player", "button", "formal"):
            return self.rule_context in candidate
        if self.rule_context == "ui":
            return "ui" in candidate or "dialog" not in candidate
        return "dialog" in candidate or "ui" not in candidate


def apply_everyday_policy(votes: Sequence[JurorVote], cap: int = 3, min_jurors: int = 2) -> Tuple[List[JurorVote], bool]:
    """Pure policy returning updated immutable votes capped when enough jurors flag odd words."""
    flaggers = [v for v in votes if v.odd_words]
    if len(flaggers) < min_jurors:
        return list(votes), False
    words = list(dict.fromkeys(w for v in flaggers for w in v.odd_words))
    note = f"{len(flaggers)} jurors found words a native would not use every day ({', '.join(words)})"
    out: List[JurorVote] = []
    for v in votes:
        new_score = cap if v.score > cap else v.score
        new_it = "translationese" if (v.score > cap and v.issue_type in (None, "none")) else v.issue_type
        new_reason = f"{v.reason.rstrip('. ')}. {note}" if v.reason.strip() else note
        out.append(v.with_update(score=new_score, issue_type=new_it, reason=new_reason))
    return out, True
