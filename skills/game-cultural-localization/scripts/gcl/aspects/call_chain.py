"""AOP CallAspect chain wrapping LLM calls with telemetry, fallback and error normalization."""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional, Protocol, Sequence, Tuple, runtime_checkable

from gcl.domain.errors import L10nError, ModelNotFoundError, ProviderError
from gcl.domain.models import ChatRequest, ChatResult
from gcl.ports.events import EventBus, LLMCallObserved

__layer__ = "aspects"
__pattern__ = "Decorator and Interceptor (AOP)"
__owns__ = "composable CallAspect pipeline for telemetry, fallback, secret scrub and offline guard"

ProceedCall = Callable[[ChatRequest], ChatResult]


@runtime_checkable
class CallAspect(Protocol):
    """Around advice intercepting ChatRequest execution."""

    def around(self, request: ChatRequest, proceed: ProceedCall) -> ChatResult: ...


class SecretRedactionAspect:
    """Scrubs sensitive secret values out of raised ProviderError messages."""

    def __init__(self, secrets: Sequence[str] = ()) -> None:
        self._secrets = tuple(s for s in secrets if s)

    def around(self, request: ChatRequest, proceed: ProceedCall) -> ChatResult:
        try:
            return proceed(request)
        except ProviderError as exc:
            msg = str(exc)
            for secret in self._secrets:
                msg = msg.replace(secret, "***")
            raise type(exc)(msg) from exc


class OfflineGuardAspect:
    """Blocks live network transport calls when GCL_OFFLINE=1 is active."""

    def __init__(self, offline_env: str = "GCL_OFFLINE") -> None:
        self._env = offline_env

    def around(self, request: ChatRequest, proceed: ProceedCall) -> ChatResult:
        if os.environ.get(self._env, "") == "1" and not request.options.get("dry_run"):
            raise ProviderError(f"network access is disabled ({self._env}=1); use --dry-run")
        return proceed(request)


class BudgetTelemetryAspect:
    """Emits LLMCallObserved events on success or failure without polluting adapters."""

    def __init__(self, bus: EventBus, metadata_fn: Callable[[], Dict[str, object]]) -> None:
        self._bus = bus
        self._meta_fn = metadata_fn

    def around(self, request: ChatRequest, proceed: ProceedCall) -> ChatResult:
        try:
            res = proceed(request)
        except (ProviderError, L10nError) as exc:
            self._emit(res=None, meta=self._meta_fn(), error=str(exc))
            raise
        self._emit(res=res, meta=self._meta_fn(), error="")
        return res

    def _emit(self, *, res: Optional[ChatResult], meta: Dict[str, object], error: str) -> None:
        self._bus.publish(LLMCallObserved(
            role=str(meta.get("role", "")), provider=str(meta.get("provider", "")),
            alias=str(meta.get("alias", "")), model=str(meta.get("model", "")),
            input_tokens=res.input_tokens if res else 0, output_tokens=res.output_tokens if res else 0,
            latency_ms=res.latency_ms if res else 0, ok=(not error),
            cache_read_tokens=res.cache_read_tokens if res else 0,
            cache_write_tokens=res.cache_write_tokens if res else 0,
            thought_tokens=int(getattr(res, "thought_tokens", 0) or 0) if res else 0,
            batch_id=str(getattr(res, "batch_id", "")) if res else "",
            batched=bool(meta.get("batched", False)), flex=bool(meta.get("flex", False)),
            dry_run=bool(meta.get("dry_run", False)),
            fallback_from=str(meta.get("fallback_from", "")), error=error,
        ))


class FallbackModelAspect:
    """Switches once to a configured fallback target when ModelNotFoundError is raised."""

    def __init__(self, switch_fn: Callable[[ModelNotFoundError], ProceedCall]) -> None:
        self._switch_fn = switch_fn

    def around(self, request: ChatRequest, proceed: ProceedCall) -> ChatResult:
        try:
            return proceed(request)
        except ModelNotFoundError as exc:
            fallback_proceed = self._switch_fn(exc)
            return fallback_proceed(request)


class ThinkingEffortAspect:
    """Attaches resolved effort and service tier options onto ChatRequest.options."""

    def __init__(self, options_fn: Callable[[], Dict[str, Any]]) -> None:
        self._opts_fn = options_fn

    def around(self, request: ChatRequest, proceed: ProceedCall) -> ChatResult:
        extra = self._opts_fn()
        if not extra:
            return proceed(request)
        merged = {**extra, **request.options}
        req = ChatRequest(
            system=request.system, user=request.user, role=request.role, model=request.model,
            temperature=request.temperature, max_tokens=request.max_tokens, json_mode=request.json_mode,
            options=merged,
        )
        return proceed(req)


class AspectChain:
    """Compose CallAspect interceptors cleanly around a core call function."""

    def __init__(self, terminal: ProceedCall, aspects: Sequence[CallAspect] = ()) -> None:
        self._terminal = terminal
        self._aspects: Tuple[CallAspect, ...] = tuple(aspects)

    def invoke(self, request: ChatRequest) -> ChatResult:
        nxt = self._terminal
        for aspect in reversed(self._aspects):
            prev = nxt
            nxt = (lambda a, n: lambda req: a.around(req, n))(aspect, prev)
        return nxt(request)
