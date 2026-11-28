"""Facade delegating providers.base symbols to gcl.infrastructure.providers and gcl.aspects."""

import sys
import time
from pathlib import Path
from collections.abc import Callable, Sequence
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcl.aspects.event_bus import BudgetLog  # noqa: E402
from gcl.domain.errors import MissingKeyError, ModelNotFoundError, ProviderError, StreamInterrupted  # noqa: E402
from gcl.domain.models import ChatResult  # noqa: E402
from gcl.infrastructure.providers.adapters.legacy_adapter import FromLegacy, LegacyAdapter, as_legacy  # noqa: E402
from gcl.infrastructure.providers.envelope import (  # noqa: E402
    JSON_ONLY_HINT, PAYLOAD_SEP, envelope, estimate_tokens, extract_json, prompt_hash, split_envelope,
)
from gcl.infrastructure.providers.http_transport import (  # noqa: E402
    ANTHROPIC_MAX_OUTPUT, DEEPSEEK_MAX_OUTPUT, DEFAULT_TIMEOUT_S, GOOGLE_MAX_OUTPUT, OFFLINE_ENV, STREAM_DONE,
    GetTransport, HttpProvider, HttpRequestOptions, Transport, fetch_text, json_object, send_json, sse_events,
    urllib_get, urllib_transport,
)
from gcl.infrastructure.providers.rate_limiter import (  # noqa: E402
    BACKOFF_BASE_S, BACKOFF_CAP_S, MAX_ATTEMPTS, RATE_LIMIT_BASE_S, RATE_LIMIT_CAP_S, RateLimiter, backoff_delay,
    is_model_not_found, limiter_for, rate_limit_delay, redact,
)
from gcl.ports.llm import LLMClient as Provider  # noqa: E402


def http_get(
    url: str,
    headers: dict[str, str],
    *,
    get: GetTransport,
    sleep: Callable[[float], None] = time.sleep,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_attempts: int = MAX_ATTEMPTS,
    label: str = "provider",
    secrets: Sequence[str] = (),
) -> str:
    """Legacy keyword compatible wrapper delegating to gcl.infrastructure.providers.http_transport.fetch_text."""
    opts = HttpRequestOptions(sleep=sleep, timeout=timeout, max_attempts=max_attempts, label=label, secrets=secrets)
    return fetch_text(url, headers, get, opts)


def post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    *,
    transport: Transport,
    sleep: Callable[[float], None] = time.sleep,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_attempts: int = MAX_ATTEMPTS,
    label: str = "provider",
    before_attempt: Callable[[], Any] | None = None,
    secrets: Sequence[str] = (),
    decode: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Legacy keyword compatible wrapper delegating to gcl.infrastructure.providers.http_transport.send_json."""
    opts = HttpRequestOptions(
        sleep=sleep, timeout=timeout, max_attempts=max_attempts, label=label,
        before_attempt=before_attempt, secrets=secrets, decode=decode,
    )
    return send_json(url, headers, payload, transport, opts)


__all__ = [
    "ANTHROPIC_MAX_OUTPUT", "BACKOFF_BASE_S", "BACKOFF_CAP_S", "BudgetLog", "ChatResult", "DEEPSEEK_MAX_OUTPUT",
    "DEFAULT_TIMEOUT_S", "FromLegacy", "GOOGLE_MAX_OUTPUT", "GetTransport", "HttpProvider", "JSON_ONLY_HINT",
    "LegacyAdapter", "MAX_ATTEMPTS", "MissingKeyError", "ModelNotFoundError", "OFFLINE_ENV", "PAYLOAD_SEP",
    "Provider", "ProviderError", "RATE_LIMIT_BASE_S", "RATE_LIMIT_CAP_S", "RateLimiter", "STREAM_DONE",
    "StreamInterrupted", "Transport", "as_legacy", "backoff_delay", "envelope", "estimate_tokens", "extract_json",
    "http_get", "is_model_not_found", "json_object", "limiter_for", "post_json", "prompt_hash", "rate_limit_delay",
    "redact", "split_envelope", "sse_events", "urllib_get", "urllib_transport",
]
