"""Batch API mode: the calls of many threads go to the provider as one batch job at half the price.

Anthropic Message Batches and Gemini Batch Mode bill every token at 50 percent of the standard price. In exchange a
reply comes when its job ends, most jobs end within an hour, Anthropic stops a job after 24 hours and Google aims at
24 hours. The tools stay as they are. A task still calls complete() once per batch of rows from its worker threads,
BatchCollector holds those calls, sends the ones that arrive together as one job, polls the job and hands every
caller its own reply. A caller that gets an error asks again as before, the next attempt rides the next job.

  Anthropic  POST {endpoint}/batches                  {"requests": [{"custom_id", "params"}]}
             GET  {endpoint}/batches/{id}             processing_status "ended" when done
             GET  results_url                         JSON lines {"custom_id", "result": {"type": "succeeded", "message"}}
  Google     POST {endpoint}/models/{model}:batchGenerateContent
                  {"batch": {"displayName", "inputConfig": {"requests": {"requests": [{"request", "metadata": {"key"}}]}}}}
             GET  {endpoint}/{name}                   state JOB_STATE_* (or BATCH_STATE_*) under metadata, done true
             results inline, in the order of the requests, under response.inlinedResponses.inlinedResponses

Google's guide and its API reference name the state and the result fields in two ways, so the reader accepts both.
A job that ends without a reply for a request gives that request a ProviderError. A batch request cannot stream, the
body is the adapter's own body without "stream". Python 3.9+, standard library only.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Sequence

from .base import (
    DEFAULT_TIMEOUT_S, ChatResult, GetTransport, ProviderError, estimate_tokens, http_get, post_json, urllib_get,
)

BATCH_PRICE_FACTOR = 0.5          # both vendors bill a batch at half the standard price
DEFAULT_LINGER_S = 5.0            # a job is sent once no new call arrived for this long
DEFAULT_POLL_S = 30.0             # the state of a job is asked this often
DEFAULT_TIMEOUT_JOB_S = 25 * 3600  # a job still open after this is cancelled and its calls fail


class BatchJobError(ProviderError):
    """A batch job failed, expired or was cancelled, every call in it fails."""


class _Pending:
    __slots__ = ("cid", "system", "user", "temperature", "max_tokens", "json_mode", "size", "event", "result", "error")

    def __init__(self, cid: str, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> None:
        self.cid, self.system, self.user = cid, system, user
        self.temperature, self.max_tokens, self.json_mode = temperature, max_tokens, json_mode
        self.size = len(system.encode("utf-8")) + len(user.encode("utf-8")) + 512
        self.event = threading.Event()
        self.result: Optional[ChatResult] = None
        self.error: Optional[BaseException] = None


class BatchCollector:
    """complete() of a provider in batch mode. Calls that arrive together go to the provider as one job.

    A job is sent when `max_requests` calls or `max_bytes` of prompts are waiting, or when no new call came for
    `linger_s` seconds. Several jobs can be open at once, each has its own polling thread.
    """

    batched = True

    def __init__(self, backend: Any, *, linger_s: float = DEFAULT_LINGER_S, poll_s: float = DEFAULT_POLL_S,
                 max_requests: int = 1000, max_bytes: Optional[int] = None, timeout_s: float = DEFAULT_TIMEOUT_JOB_S,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 on_job: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self.backend = backend
        self.model = backend.model
        self.name = backend.name
        self.linger_s, self.poll_s, self.timeout_s = float(linger_s), float(poll_s), float(timeout_s)
        self.max_requests = max(1, int(max_requests))
        self.max_bytes = int(max_bytes or getattr(backend, "max_bytes", 200_000_000))
        self._sleep, self._clock, self._on_job = sleep, clock, on_job
        self._lock = threading.Lock()
        self._queue: List[_Pending] = []
        self._last = 0.0
        self._seq = 0
        self._flusher: Optional[threading.Thread] = None
        self.jobs: List[Dict[str, Any]] = []

    def __repr__(self) -> str:
        return f"BatchCollector({self.name}/{self.model})"

    def complete(self, system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 2048,
                 json_mode: bool = False) -> ChatResult:
        with self._lock:
            self._seq += 1
            item = _Pending(f"r{self._seq}", system, user, temperature, max_tokens, json_mode)
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

    # ------------------------------------------------------------------ #
    def _take(self) -> List[_Pending]:
        """The next job's calls from the queue (lock held): at most max_requests and max_bytes."""
        items: List[_Pending] = []
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

    def _run_job(self, items: List[_Pending]) -> None:
        started = self._clock()
        job: Optional[Dict[str, Any]] = None
        try:
            job = self.backend.submit(items)
            info = {"job": job.get("id"), "requests": len(items), "model": self.model}
            self.jobs.append(info)
            if self._on_job is not None:
                self._on_job(info)
            while True:
                state = self.backend.poll(job)
                if state.get("done"):
                    break
                if self._clock() - started > self.timeout_s:
                    try:
                        self.backend.cancel(job)
                    except ProviderError:
                        pass
                    raise BatchJobError(f"{self.name}/{self.model}: batch job {job.get('id')} did not end within {self.timeout_s:.0f} s, cancelled")
                self._sleep(self.poll_s)
            results = self.backend.results(job, state)
            latency = int((self._clock() - started) * 1000)
            for it in items:
                r = results.get(it.cid)
                if isinstance(r, ChatResult):
                    it.result = r._replace(latency_ms=latency, batch_id=str(job.get("id", "")))
                else:
                    it.error = r if isinstance(r, BaseException) else ProviderError(
                        f"{self.name}/{self.model}: batch job {job.get('id')} ended without a reply for request {it.cid}")
        except BaseException as exc:  # the whole job failed, every caller gets the error and may ask again
            err = exc if isinstance(exc, ProviderError) else ProviderError(f"{self.name}/{self.model}: batch job failed ({exc})")
            for it in items:
                if it.result is None and it.error is None:
                    it.error = err
        finally:
            for it in items:
                it.event.set()


# --------------------------------------------------------------------------- #
# vendor backends
# --------------------------------------------------------------------------- #
class _Backend:
    """Shared plumbing: the real-time adapter builds every request body and parses every reply."""

    max_bytes = 200_000_000

    def __init__(self, provider: Any, get: Optional[GetTransport] = None) -> None:
        self.provider = provider
        self.model = provider.model
        self.name = provider.name
        self._get = get or urllib_get

    def _post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        p = self.provider
        return post_json(url, p._headers(), payload, transport=p._transport, sleep=p._sleep, timeout=p._timeout,
                         max_attempts=p._max_attempts, label=f"{self.name}/{self.model} batch", before_attempt=p._limiter.wait,
                         secrets=(p._key,))

    def _get_text(self, url: str) -> str:
        p = self.provider
        return http_get(url, p._headers(), get=self._get, sleep=p._sleep, timeout=p._timeout or DEFAULT_TIMEOUT_S,
                        max_attempts=p._max_attempts, label=f"{self.name}/{self.model} batch", secrets=(p._key,))

    def _get_json(self, url: str) -> Dict[str, Any]:
        text = self._get_text(url)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.name}/{self.model} batch: reply is not JSON ({exc.msg})")
        if not isinstance(data, dict):
            raise ProviderError(f"{self.name}/{self.model} batch: reply is not a JSON object")
        return data

    def _result(self, data: Dict[str, Any], it_system: str = "", it_user: str = "") -> ChatResult:
        parsed = self.provider._parse(data)
        text, tin, tout = parsed[:3]
        cread, cwrite = (int(parsed[3] or 0), int(parsed[4] or 0)) if len(parsed) >= 5 else (0, 0)
        return ChatResult(text, tin if tin is not None else estimate_tokens(it_system + it_user),
                          tout if tout is not None else estimate_tokens(text), self.model, 0, cread, cwrite)


class AnthropicBatchBackend(_Backend):
    """Message Batches API, up to 100000 requests or 256 MB per batch."""

    max_bytes = 200_000_000

    def _base(self) -> str:
        return self.provider.endpoint.rstrip("/") + "/batches"

    def submit(self, items: Sequence[_Pending]) -> Dict[str, Any]:
        reqs = []
        for it in items:
            params = self.provider._body(it.system, it.user, it.temperature, it.max_tokens, it.json_mode)
            params.pop("stream", None)  # a batch request cannot stream
            reqs.append({"custom_id": it.cid, "params": params})
        data = self._post(self._base(), {"requests": reqs})
        if not data.get("id"):
            raise BatchJobError(f"anthropic/{self.model}: batch create reply has no id")
        return {"id": str(data["id"])}

    def poll(self, job: Dict[str, Any]) -> Dict[str, Any]:
        data = self._get_json(f"{self._base()}/{urllib.parse.quote(job['id'], safe='_-')}")
        return {"done": data.get("processing_status") == "ended", "data": data}

    def results(self, job: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        url = (state.get("data") or {}).get("results_url") or f"{self._base()}/{urllib.parse.quote(job['id'], safe='_-')}/results"
        out: Dict[str, Any] = {}
        for line in self._get_text(str(url)).splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            cid, res = str(row.get("custom_id", "")), row.get("result") or {}
            kind = res.get("type")
            if kind == "succeeded" and isinstance(res.get("message"), dict):
                try:
                    out[cid] = self._result(res["message"])
                except ProviderError as exc:
                    out[cid] = exc
            else:
                err = res.get("error") or {}
                detail = (err.get("error") or {}).get("message") if isinstance(err.get("error"), dict) else err.get("message")
                out[cid] = ProviderError(f"anthropic/{self.model} batch request {cid} {kind or 'failed'}" + (f" ({str(detail)[:200]})" if detail else ""))
        return out

    def cancel(self, job: Dict[str, Any]) -> None:
        self._post(f"{self._base()}/{urllib.parse.quote(job['id'], safe='_-')}/cancel", {})


_DONE_STATES = ("SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED")


def _google_state(data: Dict[str, Any]) -> str:
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    return str(meta.get("state") or data.get("state") or "")


def _google_inlined(data: Dict[str, Any]) -> Optional[List[Any]]:
    """The inline replies of a finished job, wherever this API version puts them."""
    for root in (data.get("response"), data.get("dest"), (data.get("metadata") or {}).get("output") if isinstance(data.get("metadata"), dict) else None,
                 (data.get("response") or {}).get("output") if isinstance(data.get("response"), dict) else None):
        if not isinstance(root, dict):
            continue
        for holder in (root, root.get("output")):
            if not isinstance(holder, dict):
                continue
            inl = holder.get("inlinedResponses", holder.get("inlined_responses"))
            if isinstance(inl, dict):
                inl = inl.get("inlinedResponses", inl.get("inlined_responses"))
            if isinstance(inl, list):
                return inl
    return None


GOOGLE_BATCH_MAX_OUTPUT = 65536  # checked live 2026-11-27, a batch request above it is refused (no decoding continuation)


class GoogleBatchBackend(_Backend):
    """Gemini Batch Mode with inline requests (the whole job under 20 MB).

    A real time call asks for the model's own output maximum, a batch request may ask for 65536 tokens at most.
    The first live job was refused with HTTP 400 ("Decoding continuation is not supported for batch requests").
    """

    max_bytes = 18_000_000

    def _request(self, it: _Pending) -> Dict[str, Any]:
        body = self.provider._body(it.system, it.user, it.temperature, it.max_tokens, it.json_mode)
        gen = body.get("generationConfig")
        if isinstance(gen, dict) and int(gen.get("maxOutputTokens") or 0) > GOOGLE_BATCH_MAX_OUTPUT:
            gen["maxOutputTokens"] = GOOGLE_BATCH_MAX_OUTPUT
        return body

    def submit(self, items: Sequence[_Pending]) -> Dict[str, Any]:
        reqs = [{"request": self._request(it), "metadata": {"key": it.cid}} for it in items]
        model = urllib.parse.quote(self.model, safe="-._")
        url = f"{self.provider.endpoint.rstrip('/')}/models/{model}:batchGenerateContent"
        data = self._post(url, {"batch": {"displayName": f"gcl-{items[0].cid}-{len(items)}", "inputConfig": {"requests": {"requests": reqs}}}})
        name = data.get("name") or (data.get("metadata") or {}).get("name") if isinstance(data, dict) else None
        if not name:
            raise BatchJobError(f"google/{self.model}: batch create reply has no name")
        return {"id": str(name), "order": [it.cid for it in items]}

    def poll(self, job: Dict[str, Any]) -> Dict[str, Any]:
        data = self._get_json(f"{self.provider.endpoint.rstrip('/')}/{job['id']}")
        state = _google_state(data)
        return {"done": bool(data.get("done")) or state.endswith(_DONE_STATES), "state": state, "data": data}

    def results(self, job: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        data = state.get("data") or {}
        inl = _google_inlined(data)
        if inl is None:
            err = data.get("error") or {}
            raise BatchJobError(f"google/{self.model}: batch job {job['id']} ended as {state.get('state') or 'unknown'} without inline replies"
                                + (f" ({str(err.get('message', ''))[:200]})" if err else ""))
        order: List[str] = list(job.get("order") or [])
        out: Dict[str, Any] = {}
        for n, item in enumerate(inl):
            if not isinstance(item, dict):
                continue
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            cid = str(meta.get("key") or (order[n] if n < len(order) else ""))
            if not cid:
                continue
            if isinstance(item.get("response"), dict):
                try:
                    out[cid] = self._result(item["response"])
                except ProviderError as exc:
                    out[cid] = exc
            else:
                err = item.get("error") or {}
                out[cid] = ProviderError(f"google/{self.model} batch request {cid} failed ({str(err.get('message', 'no reply'))[:200]})")
        return out

    def cancel(self, job: Dict[str, Any]) -> None:
        self._post(f"{self.provider.endpoint.rstrip('/')}/{job['id']}:cancel", {})


BACKENDS = {"anthropic": AnthropicBatchBackend, "google": GoogleBatchBackend}
