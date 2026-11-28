"""Stdlib urllib transport, SSE reassembly, unified HTTP retry engine and HttpProvider base."""

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from collections.abc import Callable, Sequence
from typing import Any

from gcl.domain.errors import MissingKeyError, ModelNotFoundError, PermanentProviderError, ProviderError, StreamInterrupted
from gcl.domain.models import ChatRequest, ChatResult, RawVendorReply, TokenUsage
from gcl.ports.llm import ProviderCapabilities

from .envelope import estimate_tokens
from .rate_limiter import (
    MAX_ATTEMPTS, RateLimiter, backoff_delay, is_model_not_found, limiter_for, rate_limit_delay, redact,
)

__layer__ = "infrastructure"
__pattern__ = "Template HTTP Transport"
__owns__ = "urllib GET/POST execution, SSE event assembly and retry loop"

DEFAULT_TIMEOUT_S = 600.0
ANTHROPIC_MAX_OUTPUT = 128000
DEEPSEEK_MAX_OUTPUT = 393216
GOOGLE_MAX_OUTPUT = 65536
OFFLINE_ENV = "GCL_OFFLINE"
STREAM_DONE = {"__done__": True}

type Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes, dict[str, str]]]
type GetTransport = Callable[[str, dict[str, str], float], tuple[int, bytes, dict[str, str]]]


@dataclass(frozen=True, slots=True)
class HttpRequestOptions:
    """Parameter object grouping retry and decode policy for HTTP requests."""
    sleep: Callable[[float], None] = time.sleep
    timeout: float = DEFAULT_TIMEOUT_S
    max_attempts: int = MAX_ATTEMPTS
    label: str = "provider"
    before_attempt: Callable[[], Any] | None = None
    secrets: Sequence[str] = ()
    decode: Callable[[str, dict[str, str]], dict[str, Any]] | None = None


def _urlopen_request(req: urllib.request.Request, timeout: float) -> tuple[int, bytes, dict[str, str]]:
    if os.environ.get(OFFLINE_ENV, "") == "1":
        raise ProviderError(f"network access is disabled ({OFFLINE_ENV}=1); use --dry-run")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return int(resp.status), resp.read(), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = b""
        try:
            raw = exc.read()
        except Exception:
            pass
        finally:
            exc.close()
        return int(exc.code), raw, ({k.lower(): v for k, v in exc.headers.items()} if exc.headers else {})


def urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes, dict[str, str]]:
    return _urlopen_request(urllib.request.Request(url, data=body, headers=headers, method="POST"), timeout)


def urllib_get(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes, dict[str, str]]:
    clean = {k: v for k, v in headers.items() if k.lower() != "content-type"}
    return _urlopen_request(urllib.request.Request(url, headers=clean, method="GET"), timeout)


def json_object(text: str, label: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise ProviderError(f"{label}: response is not JSON: {text[:200]!r}")
    if not isinstance(data, dict):
        raise ProviderError(f"{label}: response must be a JSON object")
    return data


def sse_events(text: str, label: str = "provider") -> list[dict[str, Any]]:
    """Decode Server Sent Events frames into ordered dicts."""
    events: list[dict[str, Any]] = []
    data: list[str] = []

    def flush() -> None:
        if not data:
            return
        if "\n".join(data).strip() == "[DONE]":
            events.append(dict(STREAM_DONE))
            data.clear()
            return
        try:
            item = json.loads("\n".join(data))
        except json.JSONDecodeError:
            raise StreamInterrupted(f"{label}: a stream event is not JSON: {data[0][:120]!r}")
        if isinstance(item, dict):
            events.append(item)
        data.clear()

    for line in text.splitlines():
        if not line:
            flush()
        elif not line.startswith(":"):
            field, _, value = line.partition(":")
            if field == "data":
                data.append(value[1:] if value.startswith(" ") else value)
    flush()
    return events


def _execute_with_retry(send_once: Callable[[], tuple[int, bytes, dict[str, str]]], opts: HttpRequestOptions, *, check_not_found: bool) -> Any:
    last = "no attempt made"
    for attempt in range(opts.max_attempts):
        if opts.before_attempt is not None:
            opts.before_attempt()
        try:
            status, raw, hdrs = send_once()
        except ProviderError:
            raise
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
            last = f"network error: {redact(str(exc), opts.secrets)}"
            if attempt < opts.max_attempts - 1:
                opts.sleep(backoff_delay(attempt))
            continue
        text = raw.decode("utf-8", "replace")
        if 200 <= status < 300:
            if opts.decode is None:
                return text
            try:
                return opts.decode(text, hdrs)
            except StreamInterrupted as exc:
                last = redact(str(exc), opts.secrets)
                if attempt < opts.max_attempts - 1:
                    opts.sleep(backoff_delay(attempt))
                continue
        snippet = redact(text[:300].replace("\n", " "), opts.secrets)
        if check_not_found and is_model_not_found(status, text):
            raise ModelNotFoundError(f"{opts.label}: model not found (HTTP {status}): {snippet}")
        if status == 429 or 500 <= status < 600:
            last = f"HTTP {status}: {snippet}"
            if attempt < opts.max_attempts - 1:
                wait_s = rate_limit_delay(attempt, hdrs.get("retry-after"), text) if status == 429 else backoff_delay(attempt, hdrs.get("retry-after"))
                opts.sleep(wait_s)
            continue
        if status in (401, 403):
            raise PermanentProviderError(f"{opts.label}: authentication failed (HTTP {status}); check the API key environment variable")
        if status in (400, 404):
            raise PermanentProviderError(f"{opts.label}: HTTP {status}: {snippet}")
        raise ProviderError(f"{opts.label}: HTTP {status}: {snippet}")
    raise ProviderError(f"{opts.label}: giving up after {opts.max_attempts} attempts ({last})")


def send_json(url: str, headers: dict[str, str], payload: dict[str, Any], transport: Transport, opts: HttpRequestOptions | None = None) -> dict[str, Any]:
    o = opts or HttpRequestOptions()
    decode = o.decode or (lambda txt, _h: json_object(txt, o.label))
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    eff = HttpRequestOptions(o.sleep, o.timeout, o.max_attempts, o.label, o.before_attempt, o.secrets, decode)
    return _execute_with_retry(lambda: transport(url, headers, body, o.timeout), eff, check_not_found=True)


def fetch_text(url: str, headers: dict[str, str], get: GetTransport, opts: HttpRequestOptions | None = None) -> str:
    o = opts or HttpRequestOptions()
    return str(_execute_with_retry(lambda: get(url, headers, o.timeout), o, check_not_found=False))


class HttpProvider:
    """Base Template transport returning typed RawVendorReply and ChatResult."""

    name = "http"
    capabilities = ProviderCapabilities()

    def __init__(self, model: str, api_key: str, endpoint: str, *, rps: float = 5.0, transport: Transport | None = None, **kw: Any) -> None:
        if not api_key:
            raise MissingKeyError(f"{self.name}: empty API key")
        self.model, self.family, self._key = model, self.name, api_key
        self.endpoint = endpoint.rstrip("/") if self.name == "google" else endpoint
        self.options = dict(kw.get("options") or {})
        self._transport = transport or urllib_transport
        self._sleep = kw.get("sleep") or time.sleep
        self._timeout = float(kw.get("timeout", DEFAULT_TIMEOUT_S))
        self._max_attempts = int(kw.get("max_attempts", MAX_ATTEMPTS))
        self._limiter = limiter_for(self.name, rps) if transport is None else RateLimiter(rps, sleep=self._sleep)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(model={self.model!r})"

    def max_output(self, default: int) -> int:
        value = self.options.get("max_output_tokens")
        return int(value) if value else int(default)

    def _url(self) -> str:
        return self.endpoint

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _body(self, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> dict[str, Any]:
        raise NotImplementedError

    def _decode(self, text: str, headers: dict[str, str]) -> dict[str, Any]:
        return json_object(text, f"{self.name}/{self.model}")

    @staticmethod
    def _is_stream(text: str, headers: dict[str, str]) -> bool:
        return "text/event-stream" in headers.get("content-type", "") or text.lstrip().startswith(("event:", "data:", ":"))

    def parse_reply(self, data: dict[str, Any]) -> RawVendorReply:
        raise NotImplementedError

    def _parse(self, data: dict[str, Any]) -> tuple[str, int | None, int | None, int, int]:
        rep = self.parse_reply(data)
        u = rep.usage
        return rep.text, u.input_tokens or None, u.output_tokens or None, u.cache_read_tokens, u.cache_write_tokens

    def send(self, request: ChatRequest) -> RawVendorReply:
        opts = HttpRequestOptions(
            sleep=self._sleep, timeout=self._timeout, max_attempts=self._max_attempts,
            label=f"{self.name}/{self.model}", before_attempt=self._limiter.wait,
            secrets=(self._key,), decode=self._decode,
        )
        body = self._body(request.system, request.user, request.temperature, request.max_tokens, request.json_mode)
        data = send_json(self._url(), self._headers(), body, self._transport, opts)
        return self.parse_reply(data)

    def complete(self, system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 2048, json_mode: bool = False) -> ChatResult:
        started = time.monotonic()
        req = ChatRequest(system=system, user=user, model=self.model, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode)
        rep = self.send(req)
        u = rep.usage
        latency = int((time.monotonic() - started) * 1000)
        return ChatResult(
            rep.text, u.input_tokens if u.input_tokens > 0 else estimate_tokens(system + user),
            u.output_tokens if u.output_tokens > 0 else estimate_tokens(rep.text),
            self.model, latency, u.cache_read_tokens, u.cache_write_tokens, rep.batch_id, u.thought_tokens,
        )
