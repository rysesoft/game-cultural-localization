"""Immutable core domain entities and typed value objects."""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, NamedTuple

__layer__ = "domain"
__pattern__ = "Value Objects"
__owns__ = "rows, tokens, findings, risks, votes and typed LLM messages"


class JuryTier(StrEnum):
    """Supported mixed family jury evaluation tiers."""

    J1 = "J1"
    J2 = "J2"
    J3 = "J3"


class LineStatus(StrEnum):
    """Canonical localization workflow verdict statuses."""

    PASS = "pass"
    REWRITE_LIGHT = "rewrite_light"
    REWRITE = "rewrite"
    CRITICAL = "critical"
    UNRESOLVED = "unresolved"


class ThinkingEffort(StrEnum):
    """Configurable per task reasoning effort levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ServiceTier(StrEnum):
    """Supported vendor request service tiers."""

    STANDARD = "standard"
    FLEX = "flex"
    PRIORITY = "priority"


class Row(NamedTuple):
    """One localisable unit with key, source, target and extra metadata."""
    key: str
    src: str
    dst: str
    meta: dict[str, Any]


class PlaceholderSet(NamedTuple):
    """Placeholders extracted from one string."""
    top: tuple[str, ...]
    nested: tuple[str, ...]
    printf: tuple[str, ...]


class Tag(NamedTuple):
    """One parsed rich text tag."""
    name: str
    closing: bool
    norm: str
    raw: str


class GlossaryTerm(NamedTuple):
    """Compiled glossary term constraint."""
    source: str
    targets: tuple[str, ...]
    forbidden: tuple[str, ...]
    regex: re.Pattern[str]


class Finding(NamedTuple):
    """One LQA lint finding."""
    severity: str
    code: str
    key: str
    message: str
    target: str

    def as_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "key": self.key, "message": self.message, "target": self.target}


class Risk(NamedTuple):
    """One UI expansion risk."""
    level: str
    key: str
    src: str
    dst: str
    src_width: float
    dst_width: float
    ratio: float
    allowed: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level, "key": self.key, "src": self.src, "dst": self.dst,
            "src_width": round(self.src_width, 2), "dst_width": round(self.dst_width, 2),
            "ratio": round(self.ratio, 3), "allowed": round(self.allowed, 3), "reason": self.reason,
        }


class ChatResult(NamedTuple):
    """Completed model call response paired with token usage and cache telemetry."""
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    latency_ms: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    batch_id: str = ""
    thought_tokens: int = 0


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Normalized vendor usage counts, always including cache telemetry."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    thought_tokens: int = 0


@dataclass(frozen=True, slots=True)
class RawVendorReply:
    """Uniform adapter output replacing loose 3 or 5 element tuples."""
    text: str
    usage: TokenUsage
    finish_reason: str = "stop"
    batch_id: str = ""


@dataclass(frozen=True, slots=True)
class ChatRequest:
    """Immutable LLM invocation request passed through the AOP CallAspect chain."""
    system: str
    user: str
    role: str = ""
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 2048
    json_mode: bool = False
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JurorVote:
    """Immutable normalized juror vote."""
    score: int
    issue_type: str = "none"
    reason: str = ""
    suggested: str = ""
    odd_words: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score, "issue_type": self.issue_type, "reason": self.reason,
            "suggested": self.suggested, "odd_words": list(self.odd_words),
        }

    def with_update(self, *, score: int, issue_type: str, reason: str) -> JurorVote:
        return JurorVote(score=score, issue_type=issue_type, reason=reason, suggested=self.suggested, odd_words=self.odd_words)
