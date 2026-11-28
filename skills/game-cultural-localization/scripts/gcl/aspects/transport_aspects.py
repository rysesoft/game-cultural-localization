"""Transport focused AOP CallAspect rings for rate limit, retry backoff and batch coalesce."""

import time
from collections.abc import Callable
from typing import Any

from gcl.domain.errors import ModelNotFoundError, PermanentProviderError, ProviderError
from gcl.domain.models import ChatRequest, ChatResult

from .call_chain import ProceedCall

__layer__ = "aspects"
__pattern__ = "Decorator and Interceptor (AOP)"
__owns__ = "rate limit, transient retry backoff and batch coalescing CallAspect interceptors"


class RateLimitAspect:
    """Throttles outgoing ChatRequest execution via an injected wait callback."""

    def __init__(self, wait_fn: Callable[[], Any]) -> None:
        self._wait_fn = wait_fn

    def around(self, request: ChatRequest, proceed: ProceedCall) -> ChatResult:
        self._wait_fn()
        return proceed(request)


class RetryBackoffAspect:
    """Retries transient ProviderError failures while failing fast on permanent 4xx or missing model."""

    def __init__(
        self,
        max_attempts: int = 3,
        delay_fn: Callable[[int, ProviderError], float] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max_attempts = max(1, int(max_attempts))
        self._delay_fn = delay_fn or (lambda attempt, _exc: float(min(10, 2 ** attempt)))
        self._sleep_fn = sleep_fn

    def around(self, request: ChatRequest, proceed: ProceedCall) -> ChatResult:
        last_exc: ProviderError | None = None
        for attempt in range(self._max_attempts):
            try:
                return proceed(request)
            except (PermanentProviderError, ModelNotFoundError):
                raise
            except ProviderError as exc:
                last_exc = exc
                if attempt + 1 < self._max_attempts:
                    delay = float(self._delay_fn(attempt, exc))
                    if delay > 0:
                        self._sleep_fn(delay)
        assert last_exc is not None
        raise last_exc


class BatchCoalesceAspect:
    """Routes eligible requests to an async batch collector unless bypassed per request."""

    def __init__(self, batch_proceed: ProceedCall, enabled_fn: Callable[[], bool]) -> None:
        self._batch_proceed = batch_proceed
        self._enabled_fn = enabled_fn

    def around(self, request: ChatRequest, proceed: ProceedCall) -> ChatResult:
        if self._enabled_fn() and not request.options.get("bypass_batch"):
            return self._batch_proceed(request)
        return proceed(request)
