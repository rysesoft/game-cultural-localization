"""Provider protocol, HTTP transport (urllib) with retry and rate limit, token estimation, budget log.

Every LLM adapter in this package returns a ChatResult and is driven through the
same Provider protocol, so the pipeline never depends on a vendor SDK.

Python 3.9+, standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Protocol, Sequence, Tuple

from l10n_common import L10nError

MAX_ATTEMPTS = 5            # 429 / 5xx / network errors are retried, at most 5 attempts in total
BACKOFF_BASE_S = 1.0        # 1, 2, 4, 8 seconds between the attempts
BACKOFF_CAP_S = 30.0
DEFAULT_TIMEOUT_S = 600.0   # a long JSON answer after thinking can take minutes, 10 minutes like the vendor SDKs
# Current models of all three families think before they answer and the thinking counts against the output
# limit. Every adapter asks for at least this many tokens so a batch answer is never cut off. Only generated
# tokens are billed, the ceiling itself costs nothing. Checked live: Claude, DeepSeek (up to 131072) and
# Gemini (up to 65536) accept it.
MIN_MAX_TOKENS = 16000
PAYLOAD_SEP = "\n---\n"     # user prompt = instruction + PAYLOAD_SEP + JSON payload
OFFLINE_ENV = "GCL_OFFLINE"  # "1" refuses every network call (tests set it as a safety net)


class ChatResult(NamedTuple):
    """One completed chat call. input_tokens is the whole prompt, cached parts included.

    cache_read_tokens are prompt tokens served from the provider's prompt cache (billed at the cache read price),
    cache_write_tokens were written to it on this call (Anthropic bills them at 1.25x the input price).
    """
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    latency_ms: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class Provider(Protocol):
    """Minimal LLM adapter shared by every vendor."""
    name: str          # "anthropic" | "google" | "deepseek" | "fake"
    model: str

    def complete(self, system: str, user: str, *, temperature: float = 0.0,
                 max_tokens: int = 2048, json_mode: bool = False) -> ChatResult: ...


class ProviderError(L10nError):
    """A provider call failed for good (after retries, or a non-retryable HTTP status). Ends the CLI with exit 2."""


class ModelNotFoundError(ProviderError):
    """The API reported that the model id does not exist; the router switches to the configured fallback."""


class MissingKeyError(L10nError):
    """A required API key environment variable is not set."""


# --------------------------------------------------------------------------- #
# Prompt envelope and reply parsing
# --------------------------------------------------------------------------- #

def envelope(instruction: str, payload: Dict[str, Any]) -> str:
    """Build a user prompt: plain instruction, separator, then the JSON payload the model works on."""
    return instruction.rstrip() + PAYLOAD_SEP + json.dumps(payload, ensure_ascii=False)


def split_envelope(user: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Inverse of envelope(): return (instruction, payload or None when the prompt has no JSON payload)."""
    if PAYLOAD_SEP not in user:
        return user, None
    head, tail = user.split(PAYLOAD_SEP, 1)
    try:
        data = json.loads(tail)
    except json.JSONDecodeError:
        return user, None
    return head, data if isinstance(data, dict) else None


_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)


def extract_json(text: str) -> Any:
    """Parse the JSON object (or array) in a model reply; tolerates code fences and leading prose."""
    cleaned = _FENCE_RE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    if not starts:
        raise L10nError("model reply contains no JSON object")
    start = min(starts)
    closer = "}" if cleaned[start] == "{" else "]"
    end = cleaned.rfind(closer)
    if end <= start:
        raise L10nError("model reply contains no complete JSON object")
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise L10nError(f"model reply is not valid JSON: {exc.msg}")


def prompt_hash(system: str, user: str) -> str:
    """Stable 16-hex-digit hash of a prompt pair (fake provider scenario key)."""
    return hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Token estimation
# --------------------------------------------------------------------------- #

def estimate_tokens(text: str) -> int:
    """Rough token count when the API does not report usage: 1 per CJK character, 1 per 4 other characters."""
    wide = sum(1 for ch in text if unicodedata.east_asian_width(ch) in ("W", "F"))
    other = len(text) - wide
    return wide + (other + 3) // 4


# --------------------------------------------------------------------------- #
# Rate limiting and retry
# --------------------------------------------------------------------------- #
class RateLimiter:
    """Minimum interval limiter: at most `rps` requests per second for one provider (thread safe)."""

    def __init__(self, rps: float, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        if rps <= 0:
            raise L10nError(f"rate limit must be > 0 requests per second, got {rps}")
        self.interval = 1.0 / float(rps)
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> float:
        """Block until the next request may start; return the seconds slept."""
        with self._lock:
            now = self._clock()
            slept = 0.0
            if self._next > now:
                slept = self._next - now
                self._sleep(slept)
                now = self._next
            self._next = now + self.interval
            return slept


_LIMITERS: Dict[str, RateLimiter] = {}
_LIMITERS_LOCK = threading.Lock()


def limiter_for(provider_name: str, rps: float) -> RateLimiter:
    """Shared limiter per provider name, so every model of one vendor counts against the same budget."""
    with _LIMITERS_LOCK:
        lim = _LIMITERS.get(provider_name)
        if lim is None or abs(lim.interval - 1.0 / float(rps)) > 1e-12:
            lim = RateLimiter(rps)
            _LIMITERS[provider_name] = lim
        return lim


def backoff_delay(attempt: int, retry_after: Optional[str] = None) -> float:
    """Seconds to wait before attempt `attempt + 1`: Retry-After when given, else exponential 1, 2, 4, 8 (capped)."""
    if retry_after:
        try:
            return max(0.0, min(BACKOFF_CAP_S, float(retry_after)))
        except ValueError:
            pass
    return min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** attempt))


# transport(url, headers, body, timeout) -> (status, response body, lower-cased headers)
Transport = Callable[[str, Dict[str, str], bytes, float], Tuple[int, bytes, Dict[str, str]]]


def urllib_transport(url: str, headers: Dict[str, str], body: bytes, timeout: float) -> Tuple[int, bytes, Dict[str, str]]:
    """POST with urllib.request; HTTP error statuses are returned, network failures raise OSError."""
    if os.environ.get(OFFLINE_ENV, "") == "1":
        raise ProviderError(f"network access is disabled ({OFFLINE_ENV}=1); use --dry-run")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https endpoints from config)
            return int(resp.status), resp.read(), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = b""
        try:
            raw = exc.read()
        except Exception:
            pass
        finally:
            exc.close()
        hdrs = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        return int(exc.code), raw, hdrs


_KEY_QS_RE = re.compile(r"([?&]key=)[^&\s]+")


def redact(text: str, secrets: Sequence[str] = ()) -> str:
    """Remove API keys from a message: '?key=' query values and every given secret string."""
    out = _KEY_QS_RE.sub(r"\1***", text)
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***")
    return out


_NOT_FOUND_RE = re.compile(r"model[^\n]{0,80}(not[ _]found|not exist|does not exist|is not supported|unknown)|not_found_error|model_not_found", re.IGNORECASE)


def is_model_not_found(status: int, body_text: str) -> bool:
    """True when the API says the requested model id is unknown (404, or 400 with a model-not-found message)."""
    if status == 404:
        return True
    return status in (400, 422) and bool(_NOT_FOUND_RE.search(body_text))


def post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], *, transport: Transport,
              sleep: Callable[[float], None] = time.sleep, timeout: float = DEFAULT_TIMEOUT_S,
              max_attempts: int = MAX_ATTEMPTS, label: str = "provider", before_attempt: Optional[Callable[[], Any]] = None,
              secrets: Sequence[str] = ()) -> Dict[str, Any]:
    """POST a JSON payload with retry on 429 / 5xx / network errors (exponential backoff, at most max_attempts).

    `secrets` (the API key) are scrubbed from every error message.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last = "no attempt made"
    for attempt in range(max_attempts):
        if before_attempt is not None:
            before_attempt()
        try:
            status, raw, hdrs = transport(url, headers, body, timeout)
        except ProviderError:
            raise
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
            last = f"network error: {redact(str(exc), secrets)}"
            if attempt < max_attempts - 1:
                sleep(backoff_delay(attempt))
            continue
        text = raw.decode("utf-8", "replace")
        if 200 <= status < 300:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                raise ProviderError(f"{label}: response is not JSON: {text[:200]!r}")
            if not isinstance(data, dict):
                raise ProviderError(f"{label}: response must be a JSON object")
            return data
        snippet = redact(text[:300].replace("\n", " "), secrets)
        if is_model_not_found(status, text):
            raise ModelNotFoundError(f"{label}: model not found (HTTP {status}): {snippet}")
        if status == 429 or 500 <= status < 600:
            last = f"HTTP {status}: {snippet}"
            if attempt < max_attempts - 1:
                sleep(backoff_delay(attempt, hdrs.get("retry-after")))
            continue
        if status in (401, 403):
            raise ProviderError(f"{label}: authentication failed (HTTP {status}); check the API key environment variable")
        raise ProviderError(f"{label}: HTTP {status}: {snippet}")
    raise ProviderError(f"{label}: giving up after {max_attempts} attempts ({last})")


# --------------------------------------------------------------------------- #
# HTTP provider base class
# --------------------------------------------------------------------------- #
class HttpProvider:
    """Common machinery for the urllib adapters; subclasses build the request and parse the reply."""

    name = "http"

    def __init__(self, model: str, api_key: str, endpoint: str, *, rps: float = 5.0, transport: Optional[Transport] = None,
                 sleep: Optional[Callable[[float], None]] = None, timeout: float = DEFAULT_TIMEOUT_S,
                 max_attempts: int = MAX_ATTEMPTS, options: Optional[Dict[str, Any]] = None) -> None:
        if not api_key:
            raise MissingKeyError(f"{self.name}: empty API key")
        self.model = model
        self.family = self.name
        self._key = api_key
        self.endpoint = endpoint.rstrip("/") if self.name == "google" else endpoint
        self.options = dict(options or {})
        self._transport = transport or urllib_transport
        self._sleep = sleep or time.sleep
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._limiter = limiter_for(self.name, rps) if transport is None else RateLimiter(rps, sleep=self._sleep)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(model={self.model!r})"  # never shows the key

    # subclass hooks ------------------------------------------------------- #
    def _url(self) -> str:
        return self.endpoint

    def _headers(self) -> Dict[str, str]:
        raise NotImplementedError

    def _body(self, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> Dict[str, Any]:
        raise NotImplementedError

    def _parse(self, data: Dict[str, Any]) -> Tuple[Any, ...]:
        """(text, input_tokens, output_tokens) or (text, input_tokens, output_tokens, cache_read, cache_write)."""
        raise NotImplementedError

    # public --------------------------------------------------------------- #
    def complete(self, system: str, user: str, *, temperature: float = 0.0,
                 max_tokens: int = 2048, json_mode: bool = False) -> ChatResult:
        """Send one system + user prompt and return the reply text with token usage and latency."""
        started = time.monotonic()
        data = post_json(self._url(), self._headers(), self._body(system, user, temperature, max_tokens, json_mode),
                         transport=self._transport, sleep=self._sleep, timeout=self._timeout,
                         max_attempts=self._max_attempts, label=f"{self.name}/{self.model}", before_attempt=self._limiter.wait,
                         secrets=(self._key,))
        parsed = self._parse(data)
        text, tin, tout = parsed[:3]
        cread, cwrite = (int(parsed[3] or 0), int(parsed[4] or 0)) if len(parsed) >= 5 else (0, 0)
        latency = int((time.monotonic() - started) * 1000)
        return ChatResult(text, tin if tin is not None else estimate_tokens(system + user),
                          tout if tout is not None else estimate_tokens(text), self.model, latency, cread, cwrite)


JSON_ONLY_HINT = "Reply with one JSON object only. No Markdown fences, no prose outside the JSON."


# --------------------------------------------------------------------------- #
# Legacy adapters
# --------------------------------------------------------------------------- #
class LegacyAdapter:
    """Expose a Provider through the old orchestrator_stub interface complete(system, user) -> str."""

    def __init__(self, provider: Any, **kwargs: Any) -> None:
        self.provider = provider
        self.kwargs = kwargs

    def complete(self, system: str, user: str) -> str:
        return self.provider.complete(system, user, **self.kwargs).text


def as_legacy(provider: Any, **kwargs: Any) -> LegacyAdapter:
    """Wrap a Provider so code written for complete(system, user) -> str keeps working."""
    return LegacyAdapter(provider, **kwargs)


class FromLegacy:
    """Wrap an old complete(system, user) -> str object (or callable) as a Provider with estimated tokens."""

    def __init__(self, legacy: Any, name: str = "legacy", model: str = "legacy") -> None:
        self.legacy = legacy
        self.name = name
        self.family = name
        self.model = model

    def complete(self, system: str, user: str, *, temperature: float = 0.0,
                 max_tokens: int = 2048, json_mode: bool = False) -> ChatResult:
        started = time.monotonic()
        fn = getattr(self.legacy, "complete", self.legacy)
        text = fn(system, user)
        return ChatResult(text, estimate_tokens(system + user), estimate_tokens(text), self.model,
                          int((time.monotonic() - started) * 1000))


# --------------------------------------------------------------------------- #
# Budget log
# --------------------------------------------------------------------------- #
class BudgetLog:
    """Append one JSON line per provider call (role, provider, model, tokens, latency) to budget.jsonl."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else None
        self.records: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def write(self, record: Dict[str, Any]) -> None:
        with self._lock:
            self.records.append(record)
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
