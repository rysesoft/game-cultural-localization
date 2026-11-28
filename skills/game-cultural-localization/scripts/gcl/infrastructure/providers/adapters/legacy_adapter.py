"""Legacy complete(system, user) -> str adapters bridging 2.1 callers into LLMClient."""

import time
from typing import Any

from gcl.domain.models import ChatResult
from gcl.ports.llm import ProviderCapabilities

from ..envelope import estimate_tokens

__layer__ = "infrastructure"
__pattern__ = "Adapter"
__owns__ = "bidirectional adaptation between LLMClient and legacy string callable providers"


class LegacyAdapter:
    """Expose LLMClient as legacy complete(system, user) -> str."""

    def __init__(self, provider: Any, **kwargs: Any) -> None:
        self.provider = provider
        self.kwargs = kwargs

    def complete(self, system: str, user: str) -> str:
        return self.provider.complete(system, user, **self.kwargs).text


def as_legacy(provider: Any, **kwargs: Any) -> LegacyAdapter:
    return LegacyAdapter(provider, **kwargs)


class FromLegacy:
    """Wrap complete(system, user) -> str object or callable as LLMClient."""

    capabilities = ProviderCapabilities(batched=False, supports_streaming=False)

    def __init__(self, legacy: Any, name: str = "legacy", model: str = "legacy") -> None:
        self.legacy, self.name, self.family, self.model = legacy, name, name, model

    def complete(self, system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 2048, json_mode: bool = False) -> ChatResult:
        started = time.monotonic()
        fn = getattr(self.legacy, "complete", self.legacy)
        text = fn(system, user)
        return ChatResult(text, estimate_tokens(system + user), estimate_tokens(text), self.model, int((time.monotonic() - started) * 1000))
