"""Observer / EventBus domain event definitions and bus protocol."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, Tuple, runtime_checkable

__layer__ = "ports"
__pattern__ = "Observer"
__owns__ = "domain event types and event bus interface"


@dataclass(frozen=True)
class DomainEvent:
    """Base immutable domain event."""


@dataclass(frozen=True)
class LLMCallObserved(DomainEvent):
    """Emitted after each completed or failed provider invocation."""
    role: str
    provider: str
    alias: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    ok: bool
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    thought_tokens: int = 0
    batch_id: str = ""
    batched: bool = False
    flex: bool = False
    dry_run: bool = False
    fallback_from: str = ""
    error: str = ""


@dataclass(frozen=True)
class FallbackSwitched(DomainEvent):
    """Emitted when a role fails over to a backup model alias."""
    role: str
    from_model: str
    to_model: str
    to_alias: str
    note: str


@dataclass(frozen=True)
class StageCompleted(DomainEvent):
    """Emitted when a pipeline stage finishes."""
    stage: str
    batch_index: int
    details: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class EventSubscriber(Protocol):
    """Subscriber reacting to emitted DomainEvent instances."""

    def handle(self, event: DomainEvent) -> None: ...


@runtime_checkable
class EventBus(Protocol):
    """In process publish subscribe bus."""

    def subscribe(self, subscriber: EventSubscriber) -> None: ...

    def publish(self, event: DomainEvent) -> None: ...
