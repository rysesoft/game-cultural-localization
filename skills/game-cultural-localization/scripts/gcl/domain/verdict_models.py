"""Immutable typed blind slice, candidate set and line verdict domain value objects."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .models import JurorVote

__layer__ = "domain"
__pattern__ = "Value Objects"
__owns__ = "immutable BlindEntry, CandidateSet and LineVerdict domain aggregates"


@dataclass(frozen=True, slots=True)
class BlindEntry:
    """Source free blind entry inspected by jurors and candidate selectors."""

    key: str
    target: str
    register: str = ""
    category: str = ""
    speaker: str = ""
    archetype: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BlindEntry:
        ctx = data.get("context")
        return cls(
            key=str(data["key"]),
            target=str(data.get("target", "")),
            register=str(data.get("register") or ""),
            category=str(data.get("category") or ""),
            speaker=str(data.get("speaker") or ""),
            archetype=str(data.get("archetype") or ""),
            context=dict(ctx) if isinstance(ctx, Mapping) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"key": self.key, "target": self.target}
        for name in ("register", "category", "speaker", "archetype"):
            val = getattr(self, name)
            if val:
                out[name] = val
        if self.context:
            out["context"] = dict(self.context)
        return out


@dataclass(frozen=True, slots=True)
class CandidateSet:
    """Immutable Pass 2 candidate choices and blind J1 selection counts for one line."""

    key: str
    candidates: tuple[str, ...]
    current_target: str
    chosen_index: int | None = None
    votes_per_candidate: tuple[int, ...] = ()

    @property
    def selected_target(self) -> str:
        if self.chosen_index is None or not 0 <= self.chosen_index < len(self.candidates):
            return self.current_target
        return self.candidates[self.chosen_index]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "candidates": list(self.candidates),
            "current_target": self.current_target,
            "chosen": self.chosen_index,
            "votes_per_candidate": list(self.votes_per_candidate),
        }


@dataclass(frozen=True, slots=True)
class LineVerdict:
    """Immutable jury verdict record hydrated from or serialized to batch verdicts JSON."""

    key: str
    final_tier: str
    score: int
    status: str
    votes: tuple[JurorVote, ...] = ()
    rationales: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LineVerdict:
        raw_votes = data.get("votes") or ()
        votes = tuple(
            v if isinstance(v, JurorVote) else JurorVote(
                score=int(v.get("score", 5)),
                issue_type=str(v.get("issue_type") or "none"),
                reason=str(v.get("reason") or ""),
                suggested=str(v.get("suggested") or ""),
                odd_words=tuple(str(w) for w in (v.get("odd_words") or ())),
            )
            for v in raw_votes
        )
        ev = data.get("evidence")
        return cls(
            key=str(data["key"]),
            final_tier=str(data.get("final_tier") or "J1"),
            score=int(data.get("score", 5)),
            status=str(data.get("status") or "pass"),
            votes=votes,
            rationales=tuple(str(r) for r in (data.get("rationales") or ())),
            evidence=dict(ev) if isinstance(ev, Mapping) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "final_tier": self.final_tier,
            "score": self.score,
            "status": self.status,
            "votes": [v.to_dict() for v in self.votes],
            "rationales": list(self.rationales),
            "evidence": dict(self.evidence),
        }
