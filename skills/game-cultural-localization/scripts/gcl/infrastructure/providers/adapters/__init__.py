"""Vendor transport adapters conforming to VendorTransportAdapter and RawVendorReply."""

from .anthropic_adapter import AnthropicProvider
from .deepseek_adapter import DeepSeekProvider
from .fake_adapter import FakeProvider, FakeScenario
from .google_adapter import GoogleProvider
from .legacy_adapter import FromLegacy, LegacyAdapter, as_legacy

__all__ = [
    "AnthropicProvider",
    "DeepSeekProvider",
    "FakeProvider",
    "FakeScenario",
    "FromLegacy",
    "GoogleProvider",
    "LegacyAdapter",
    "as_legacy",
]
