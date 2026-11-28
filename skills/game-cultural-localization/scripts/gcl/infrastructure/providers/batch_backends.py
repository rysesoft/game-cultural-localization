"""Vendor batch API backends for Anthropic Message Batches and Gemini Batch Mode."""
from __future__ import annotations

import json
import threading
import urllib.parse
from typing import Any, Dict, List, Optional, Sequence

from gcl.domain.errors import BatchJobError, ProviderError
from gcl.domain.models import ChatResult

from .envelope import estimate_tokens
from .http_transport import DEFAULT_TIMEOUT_S, GetTransport, HttpRequestOptions, fetch_text, send_json, urllib_get

__layer__ = "infrastructure"
__pattern__ = "Bridge"
__owns__ = "vendor specific async batch submission, polling, cancellation and result parsing"

GOOGLE_BATCH_MAX_OUTPUT = 65536
_DONE_STATES = ("SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED")


class PendingCall:
    """In flight queued request waiting for batch completion event."""

    __slots__ = ("cid", "system", "user", "temperature", "max_tokens", "json_mode", "size", "event", "result", "error")

    def __init__(self, cid: str, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> None:
        self.cid = cid
        self.system = system
        self.user = user
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.json_mode = json_mode
        self.size = len(system.encode("utf-8")) + len(user.encode("utf-8")) + 512
        self.event = threading.Event()
        self.result: Optional[ChatResult] = None
        self.error: Optional[BaseException] = None


_Pending = PendingCall


class _Backend:
    """Shared plumbing delegating request bodies and reply parsing to a real time provider."""

    max_bytes = 200_000_000

    def __init__(self, provider: Any, get: Optional[GetTransport] = None) -> None:
        self.provider = provider
        self.model = provider.model
        self.name = provider.name
        self._get = get or urllib_get

    def _opts(self) -> HttpRequestOptions:
        p = self.provider
        return HttpRequestOptions(
            sleep=p._sleep, timeout=p._timeout or DEFAULT_TIMEOUT_S, max_attempts=p._max_attempts,
            label=f"{self.name}/{self.model} batch", before_attempt=p._limiter.wait, secrets=(p._key,),
        )

    def _post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        p = self.provider
        return send_json(url, p._headers(), payload, p._transport, self._opts())

    def _get_text(self, url: str) -> str:
        p = self.provider
        opts = HttpRequestOptions(
            sleep=p._sleep, timeout=p._timeout or DEFAULT_TIMEOUT_S, max_attempts=p._max_attempts,
            label=f"{self.name}/{self.model} batch", secrets=(p._key,),
        )
        return fetch_text(url, p._headers(), self._get, opts)

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
        return ChatResult(
            text,
            tin if tin is not None else estimate_tokens(it_system + it_user),
            tout if tout is not None else estimate_tokens(text),
            self.model, 0, cread, cwrite,
        )


class AnthropicBatchBackend(_Backend):
    """Anthropic Message Batches API adapter."""

    max_bytes = 200_000_000

    def _base(self) -> str:
        return self.provider.endpoint.rstrip("/") + "/batches"

    def submit(self, items: Sequence[PendingCall]) -> Dict[str, Any]:
        reqs = []
        for it in items:
            params = self.provider._body(it.system, it.user, it.temperature, it.max_tokens, it.json_mode)
            params.pop("stream", None)
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
            row = _safe_json_line(line)
            if row is None:
                continue
            cid, res = str(row.get("custom_id", "")), row.get("result") or {}
            out[cid] = self._decode_row(cid, res)
        return out

    def _decode_row(self, cid: str, res: Dict[str, Any]) -> Any:
        kind = res.get("type")
        if kind == "succeeded" and isinstance(res.get("message"), dict):
            try:
                return self._result(res["message"])
            except ProviderError as exc:
                return exc
        err = res.get("error") or {}
        detail = (err.get("error") or {}).get("message") if isinstance(err.get("error"), dict) else err.get("message")
        suffix = f" ({str(detail)[:200]})" if detail else ""
        return ProviderError(f"anthropic/{self.model} batch request {cid} {kind or 'failed'}{suffix}")

    def cancel(self, job: Dict[str, Any]) -> None:
        self._post(f"{self._base()}/{urllib.parse.quote(job['id'], safe='_-')}/cancel", {})


def _safe_json_line(line: str) -> Optional[Dict[str, Any]]:
    try:
        row = json.loads(line)
        return row if isinstance(row, dict) else None
    except json.JSONDecodeError:
        return None


def _google_state(data: Dict[str, Any]) -> str:
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    return str(meta.get("state") or data.get("state") or "")


def _google_inlined(data: Dict[str, Any]) -> Optional[List[Any]]:
    """Locate inline replies across known Gemini Batch response layouts."""
    meta_out = (data.get("metadata") or {}).get("output") if isinstance(data.get("metadata"), dict) else None
    resp_out = (data.get("response") or {}).get("output") if isinstance(data.get("response"), dict) else None
    for root in (data.get("response"), data.get("dest"), meta_out, resp_out):
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


class GoogleBatchBackend(_Backend):
    """Gemini Batch Mode adapter with inline requests under 20 MB."""

    max_bytes = 18_000_000

    def _request(self, it: PendingCall) -> Dict[str, Any]:
        body = self.provider._body(it.system, it.user, it.temperature, it.max_tokens, it.json_mode)
        gen = body.get("generationConfig")
        if isinstance(gen, dict) and int(gen.get("maxOutputTokens") or 0) > GOOGLE_BATCH_MAX_OUTPUT:
            gen["maxOutputTokens"] = GOOGLE_BATCH_MAX_OUTPUT
        return body

    def submit(self, items: Sequence[PendingCall]) -> Dict[str, Any]:
        reqs = [{"request": self._request(it), "metadata": {"key": it.cid}} for it in items]
        model = urllib.parse.quote(self.model, safe="-._")
        url = f"{self.provider.endpoint.rstrip('/')}/models/{model}:batchGenerateContent"
        payload = {"batch": {"displayName": f"gcl-{items[0].cid}-{len(items)}", "inputConfig": {"requests": {"requests": reqs}}}}
        data = self._post(url, payload)
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
            suffix = f" ({str(err.get('message', ''))[:200]})" if err else ""
            raise BatchJobError(f"google/{self.model}: batch job {job['id']} ended as {state.get('state') or 'unknown'} without inline replies{suffix}")
        order: List[str] = list(job.get("order") or [])
        out: Dict[str, Any] = {}
        for n, item in enumerate(inl):
            if not isinstance(item, dict):
                continue
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            cid = str(meta.get("key") or (order[n] if n < len(order) else ""))
            if cid:
                out[cid] = self._decode_google_item(cid, item)
        return out

    def _decode_google_item(self, cid: str, item: Dict[str, Any]) -> Any:
        if isinstance(item.get("response"), dict):
            try:
                return self._result(item["response"])
            except ProviderError as exc:
                return exc
        err = item.get("error") or {}
        return ProviderError(f"google/{self.model} batch request {cid} failed ({str(err.get('message', 'no reply'))[:200]})")

    def cancel(self, job: Dict[str, Any]) -> None:
        self._post(f"{self.provider.endpoint.rstrip('/')}/{job['id']}:cancel", {})


BACKENDS = {"anthropic": AnthropicBatchBackend, "google": GoogleBatchBackend}
