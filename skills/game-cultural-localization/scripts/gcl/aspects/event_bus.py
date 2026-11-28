"""In process Observer / EventBus and thread safe JSONL budget telemetry subscriber."""

import json
import threading
from pathlib import Path
from typing import Any

from gcl.ports.events import DomainEvent, EventSubscriber, LLMCallObserved

__layer__ = "aspects"
__pattern__ = "Observer EventBus"
__owns__ = "domain event publishing, budget JSONL persistence and call metrics aggregation"


class InMemoryEventBus:
    """Thread safe Observer EventBus dispatching domain events to subscribers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[EventSubscriber] = []

    def subscribe(self, subscriber: EventSubscriber) -> None:
        with self._lock:
            if subscriber not in self._subscribers:
                self._subscribers.append(subscriber)

    def publish(self, event: DomainEvent) -> None:
        with self._lock:
            targets = list(self._subscribers)
        for sub in targets:
            sub.handle(event)


class BudgetLog:
    """Thread safe JSONL writer recording one record per provider invocation."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.records: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def write(self, record: dict[str, Any]) -> None:
        with self._lock:
            self.records.append(record)
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")


class BudgetLogSubscriber:
    """Observer converting LLMCallObserved events into BudgetLog JSONL records."""

    def __init__(self, budget_log: BudgetLog) -> None:
        self.budget_log = budget_log

    def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, LLMCallObserved):
            return
        rec: dict[str, Any] = {
            "role": event.role, "provider": event.provider, "alias": event.alias, "model": event.model,
            "input_tokens": event.input_tokens, "output_tokens": event.output_tokens,
            "latency_ms": event.latency_ms, "ok": event.ok,
        }
        if event.cache_read_tokens:
            rec["cache_read_tokens"] = event.cache_read_tokens
        if event.cache_write_tokens:
            rec["cache_write_tokens"] = event.cache_write_tokens
        if event.thought_tokens:
            rec["thought_tokens"] = event.thought_tokens
        if event.batch_id:
            rec["batch"] = True
            rec["batch_id"] = event.batch_id
        elif event.batched:
            rec["batch"] = True
        if event.flex:
            rec["flex"] = True
        if event.dry_run:
            rec["dry_run"] = True
        if event.fallback_from:
            rec["fallback_from"] = event.fallback_from
        if event.error:
            rec["error"] = event.error[:300]
        self.budget_log.write(rec)
