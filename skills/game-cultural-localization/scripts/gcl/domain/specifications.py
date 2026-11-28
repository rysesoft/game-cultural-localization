"""Composable Specification pattern for jury agreement, everyday word cap and lint filtering."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from .models import JurorVote

__layer__ = "domain"
__pattern__ = "Specification"
__owns__ = "composable boolean rules for jury agreement, everyday cap and rule scoping"


class Specification[T](ABC):
    """Boolean business rule supporting &, | and ~ composition."""

    __slots__ = ()

    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool:
        """Evaluate the specification on candidate."""

    def __and__(self, other: Specification[T]) -> Specification[T]:
        return _AndSpec(self, other)

    def __or__(self, other: Specification[T]) -> Specification[T]:
        return _OrSpec(self, other)

    def __invert__(self) -> Specification[T]:
        return _NotSpec(self)


@dataclass(frozen=True, slots=True)
class _AndSpec[T](Specification[T]):
    left: Specification[T]
    right: Specification[T]

    def is_satisfied_by(self, candidate: T) -> bool:
        return self.left.is_satisfied_by(candidate) and self.right.is_satisfied_by(candidate)


@dataclass(frozen=True, slots=True)
class _OrSpec[T](Specification[T]):
    left: Specification[T]
    right: Specification[T]

    def is_satisfied_by(self, candidate: T) -> bool:
        return self.left.is_satisfied_by(candidate) or self.right.is_satisfied_by(candidate)


@dataclass(frozen=True, slots=True)
class _NotSpec[T](Specification[T]):
    inner: Specification[T]

    def is_satisfied_by(self, candidate: T) -> bool:
        return not self.inner.is_satisfied_by(candidate)


@dataclass(frozen=True, slots=True)
class CriticalVoteSpec(Specification[Sequence[int]]):
    """True when at least one juror scored at or below critical_max."""

    critical_max: int = 2

    def is_satisfied_by(self, candidate: Sequence[int]) -> bool:
        return min(candidate) <= self.critical_max


@dataclass(frozen=True, slots=True)
class MinScoreSpec(Specification[Sequence[int]]):
    """True when every score meets pass_min."""

    pass_min: int = 4

    def is_satisfied_by(self, candidate: Sequence[int]) -> bool:
        return min(candidate) >= self.pass_min


@dataclass(frozen=True, slots=True)
class MaxSpreadSpec(Specification[Sequence[int]]):
    """True when max minus min stays within max_spread."""

    max_spread: int = 1

    def is_satisfied_by(self, candidate: Sequence[int]) -> bool:
        return max(candidate) - min(candidate) <= self.max_spread


class TierPassSpec(Specification[Sequence[int]]):
    """Composite jury pass rule combining MinScoreSpec and MaxSpreadSpec."""

    __slots__ = ("_rule",)

    def __init__(self, pass_min: int = 4, max_spread: int = 1) -> None:
        self._rule = MinScoreSpec(pass_min) & MaxSpreadSpec(max_spread)

    def is_satisfied_by(self, candidate: Sequence[int]) -> bool:
        return self._rule.is_satisfied_by(candidate)


@dataclass(frozen=True, slots=True)
class CleanLightPassSpec(Specification[tuple[Sequence[int], int, int]]):
    """True for clean [5, 5, 4] votes carrying zero odd words and zero ban hits."""

    def is_satisfied_by(self, candidate: tuple[Sequence[int], int, int]) -> bool:
        scores, odd_count, ban_count = candidate
        return sorted(scores) == [4, 5, 5] and odd_count == 0 and ban_count == 0


class RuleAppliesSpec(Specification[set[str]]):
    """Decide whether a lint rule matches a row context tag set."""

    __slots__ = ("rule_context", "skip_contexts")

    def __init__(self, rule_context: str, skip_contexts: Sequence[str] = ()) -> None:
        self.rule_context = rule_context
        self.skip_contexts = set(skip_contexts)

    def is_satisfied_by(self, candidate: set[str]) -> bool:
        if self.skip_contexts & candidate:
            return False
        match self.rule_context:
            case "any":
                return True
            case "player" | "button" | "formal":
                return self.rule_context in candidate
            case "ui":
                return "ui" in candidate or "dialog" not in candidate
            case _:
                return "dialog" in candidate or "ui" not in candidate


def apply_everyday_policy(votes: Sequence[JurorVote], cap: int = 3, min_jurors: int = 2) -> tuple[list[JurorVote], bool]:
    """Pure policy returning updated immutable votes capped when enough jurors flag odd words."""
    flaggers = [v for v in votes if v.odd_words]
    if len(flaggers) < min_jurors:
        return list(votes), False
    words = list(dict.fromkeys(w for v in flaggers for w in v.odd_words))
    note = f"{len(flaggers)} jurors found words a native would not use every day ({', '.join(words)})"
    out: list[JurorVote] = []
    for v in votes:
        new_score = cap if v.score > cap else v.score
        new_it = "translationese" if (v.score > cap and v.issue_type in (None, "none")) else v.issue_type
        new_reason = f"{v.reason.rstrip('. ')}. {note}" if v.reason.strip() else note
        out.append(v.with_update(score=new_score, issue_type=new_it, reason=new_reason))
    return out, True
