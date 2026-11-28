"""Per provider RPS rate limiter, retry backoff delays and secret redaction."""

import re
import threading
import time
from collections.abc import Callable, Sequence

from gcl.domain.errors import L10nError

__layer__ = "infrastructure"
__pattern__ = "Rate Limiter Registry"
__owns__ = "RPS throttling, 429 and 5xx backoff schedules, key redaction and model error matching"

MAX_ATTEMPTS = 5
BACKOFF_BASE_S = 1.0
BACKOFF_CAP_S = 30.0
RATE_LIMIT_BASE_S = 15.0
RATE_LIMIT_CAP_S = 120.0
_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')
_KEY_QS_RE = re.compile(r"([?&]key=)[^&\s]+")
_NOT_FOUND_RE = re.compile(
    r"model[^\n]{0,80}(not[ _]found|not exist|does not exist|is not supported|unknown)|not_found_error|model_not_found",
    re.IGNORECASE,
)


class RateLimiter:
    """Thread safe minimum interval RPS rate limiter."""

    def __init__(self, rps: float, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        if rps <= 0:
            raise L10nError(f"rate limit must be > 0 requests per second, got {rps}")
        self.interval = 1.0 / float(rps)
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> float:
        """Sleep until next slot and return seconds waited."""
        with self._lock:
            now = self._clock()
            slept = 0.0
            if self._next > now:
                slept = self._next - now
                self._sleep(slept)
                now = self._next
            self._next = now + self.interval
            return slept


_LIMITERS: dict[str, RateLimiter] = {}
_LIMITERS_LOCK = threading.Lock()


def limiter_for(provider_name: str, rps: float) -> RateLimiter:
    """Return shared RateLimiter per provider name."""
    with _LIMITERS_LOCK:
        lim = _LIMITERS.get(provider_name)
        if lim is None or abs(lim.interval - 1.0 / float(rps)) > 1e-12:
            lim = RateLimiter(rps)
            _LIMITERS[provider_name] = lim
        return lim


def backoff_delay(attempt: int, retry_after: str | None = None) -> float:
    """Exponential delay (1, 2, 4, 8 s capped at 30s) or Retry-After header value."""
    if retry_after:
        try:
            return max(0.0, min(BACKOFF_CAP_S, float(retry_after)))
        except ValueError:
            pass
    return min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** attempt))


def rate_limit_delay(attempt: int, retry_after: str | None = None, body: str = "") -> float:
    """Longer delay (15, 30, 60, 120 s) or server retryDelay after HTTP 429."""
    m = _RETRY_DELAY.search(body or "")
    for hint in (retry_after, m.group(1) if m else None):
        if hint:
            try:
                return max(0.0, min(RATE_LIMIT_CAP_S, float(hint)))
            except ValueError:
                pass
    return min(RATE_LIMIT_CAP_S, RATE_LIMIT_BASE_S * (2 ** attempt))


def redact(text: str, secrets: Sequence[str] = ()) -> str:
    """Remove ?key= query params and secret keys from text."""
    out = _KEY_QS_RE.sub(r"\1***", text)
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***")
    return out


def is_model_not_found(status: int, body_text: str) -> bool:
    """True when HTTP status and body indicate an unknown model identifier."""
    if status == 404:
        return True
    return status in (400, 422) and bool(_NOT_FOUND_RE.search(body_text))
