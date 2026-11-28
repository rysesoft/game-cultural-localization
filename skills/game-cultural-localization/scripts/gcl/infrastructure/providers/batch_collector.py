"""Thread safe BatchCollector coalescing concurrent complete() calls into batch jobs."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from gcl.domain.errors import BatchJobError, ProviderError
from gcl.domain.models import ChatResult
from gcl.ports.llm import ProviderCapabilities

from .batch_backends import PendingCall

__layer__ = "infrastructure"
__pattern__ = "Proxy and Coalescing Collector"
__owns__ = "concurrent call queueing, linger flushing and background polling for batch APIs"

BATCH_PRICE_FACTOR = 0.5
DEFAULT_LINGER_S = 5.0
DEFAULT_POLL_S = 30.0
DEFAULT_TIMEOUT_JOB_S = 25 * 3600
_VALID_KW = frozenset({"linger_s", "poll_s", "max_requests", "max_bytes", "timeout_s", "sleep", "clock", "on_job"})


class BatchCollector:
    """Thread safe proxy submitting concurrent calls together via a vendor batch backend."""

    batched = True
    capabilities = ProviderCapabilities(batched=True, supports_streaming=False)

    def __init__(self, backend: Any, **kw: Any) -> None:
        bad = set(kw) - _VALID_KW
        if bad:
            raise TypeError(f"unexpected BatchCollector keyword argument(s): {', '.join(sorted(bad))}")
        self.backend = backend
        self.model = backend.model
        self.name = backend.name
        self.linger_s = float(kw.get("linger_s", DEFAULT_LINGER_S))
        self.poll_s = float(kw.get("poll_s", DEFAULT_POLL_S))
        self.timeout_s = float(kw.get("timeout_s", DEFAULT_TIMEOUT_JOB_S))
        self.max_requests = max(1, int(kw.get("max_requests", 1000)))
        self.max_bytes = int(kw.get("max_bytes") or getattr(backend, "max_bytes", 200_000_000))
        self._sleep: Callable[[float], None] = kw.get("sleep") or time.sleep
        self._clock: Callable[[], float] = kw.get("clock") or time.monotonic
        self._on_job: Optional[Callable[[Dict[str, Any]], None]] = kw.get("on_job")
        self._lock = threading.Lock()
        self._queue: List[PendingCall] = []
        self._last = 0.0
        self._seq = 0
        self._flusher: Optional[threading.Thread] = None
        self.jobs: List[Dict[str, Any]] = []

    def __repr__(self) -> str:
        return f"BatchCollector({self.name}/{self.model})"

    def complete(
        self, system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 2048, json_mode: bool = False,
    ) -> ChatResult:
        with self._lock:
            self._seq += 1
            item = PendingCall(f"r{self._seq}", system, user, temperature, max_tokens, json_mode)
            self._queue.append(item)
            self._last = self._clock()
            if self._flusher is None or not self._flusher.is_alive():
                self._flusher = threading.Thread(target=self._flush_loop, name=f"batch-{self.model}", daemon=True)
                self._flusher.start()
        item.event.wait()
        if item.error is not None:
            raise item.error
        assert item.result is not None
        return item.result

    def _take(self) -> List[PendingCall]:
        items: List[PendingCall] = []
        used = 0
        while self._queue and len(items) < self.max_requests:
            nxt = self._queue[0]
            if items and used + nxt.size > self.max_bytes:
                break
            items.append(self._queue.pop(0))
            used += nxt.size
        return items

    def _flush_loop(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    self._flusher = None
                    return
                full = len(self._queue) >= self.max_requests or sum(i.size for i in self._queue) >= self.max_bytes
                quiet = self._clock() - self._last >= self.linger_s
                items = self._take() if (full or quiet) else []
            if items:
                threading.Thread(target=self._run_job, args=(items,), name=f"batch-job-{self.model}", daemon=True).start()
            else:
                self._sleep(min(0.25, max(0.01, self.linger_s / 4)))

    def _poll_until_done(self, job: Dict[str, Any], started: float) -> Dict[str, Any]:
        while True:
            state = self.backend.poll(job)
            if state.get("done"):
                return state
            if self._clock() - started > self.timeout_s:
                try:
                    self.backend.cancel(job)
                except ProviderError:
                    pass
                raise BatchJobError(f"{self.name}/{self.model}: batch job {job.get('id')} did not end within {self.timeout_s:.0f} s, cancelled")
            self._sleep(self.poll_s)

    def _run_job(self, items: List[PendingCall]) -> None:
        started = self._clock()
        try:
            job = self.backend.submit(items)
            info = {"job": job.get("id"), "requests": len(items), "model": self.model}
            self.jobs.append(info)
            if self._on_job is not None:
                self._on_job(info)
            state = self._poll_until_done(job, started)
            results = self.backend.results(job, state)
            self._deliver(items, results, job, int((self._clock() - started) * 1000))
        except BaseException as exc:
            err = exc if isinstance(exc, ProviderError) else ProviderError(f"{self.name}/{self.model}: batch job failed ({exc})")
            for it in items:
                if it.result is None and it.error is None:
                    it.error = err
        finally:
            for it in items:
                it.event.set()

    def _deliver(self, items: List[PendingCall], results: Dict[str, Any], job: Dict[str, Any], latency: int) -> None:
        jid = str(job.get("id", ""))
        for it in items:
            r = results.get(it.cid)
            if isinstance(r, ChatResult):
                it.result = r._replace(latency_ms=latency, batch_id=jid)
            elif isinstance(r, BaseException):
                it.error = r
            else:
                it.error = ProviderError(f"{self.name}/{self.model}: batch job {jid} ended without a reply for request {it.cid}")
