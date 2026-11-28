"""Segregated LLM client and vendor transport port protocols."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from gcl.domain.models import ChatRequest, ChatResult, RawVendorReply

__layer__ = "ports"
__pattern__ = "Port Interface"
__owns__ = "LLM client, vendor transport adapter and capability contracts"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Explicit provider capability flags removing getattr runtime probing."""
    batched: bool = False
    supports_streaming: bool = True
    supports_cache_control: bool = False


@runtime_checkable
class LLMClient(Protocol):
    """High level model client driven by application tasks through AOP aspects."""
    model: str
    family: str
    capabilities: ProviderCapabilities

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> ChatResult: ...


@runtime_checkable
class VendorTransportAdapter(Protocol):
    """Low level HTTP or mock vendor transport returning uniform RawVendorReply."""
    name: str
    model: str
    capabilities: ProviderCapabilities

    def send(self, request: ChatRequest) -> RawVendorReply: ...
