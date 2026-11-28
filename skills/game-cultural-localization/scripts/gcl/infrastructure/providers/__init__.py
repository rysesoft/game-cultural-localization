"""Provider adapters, HTTP retry transport, batch coalescing and AOP factory."""

from .adapters import (
    AnthropicProvider, DeepSeekProvider, FakeProvider, FakeScenario, FromLegacy, GoogleProvider, LegacyAdapter, as_legacy,
)
from .batch_backends import BACKENDS as BATCH_BACKENDS, AnthropicBatchBackend, GoogleBatchBackend
from .batch_collector import BATCH_PRICE_FACTOR, BatchCollector
from .config import (
    CONTEXT_ROLES, DEFAULT_CONFIG_PATH, JURY_TIERS, SINGLE_ROLES, ModelSpec, ProvidersConfig, load_providers_config,
)
from .envelope import envelope, estimate_tokens, extract_json, prompt_hash, split_envelope
from .factory import Member, RoleProvider, Router
from .http_transport import HttpProvider, HttpRequestOptions, fetch_text, send_json
from .rate_limiter import RateLimiter
from .vendor_registry import DEFAULT_VENDOR_REGISTRY, VendorDescriptor, VendorRegistry

__all__ = [
    "AnthropicBatchBackend", "AnthropicProvider", "BATCH_BACKENDS", "BATCH_PRICE_FACTOR", "BatchCollector",
    "CONTEXT_ROLES", "DEFAULT_CONFIG_PATH", "DEFAULT_VENDOR_REGISTRY", "DeepSeekProvider", "FakeProvider",
    "FakeScenario", "FromLegacy", "GoogleBatchBackend", "GoogleProvider", "HttpProvider", "HttpRequestOptions",
    "JURY_TIERS", "LegacyAdapter", "Member", "ModelSpec", "ProvidersConfig", "RateLimiter", "RoleProvider",
    "Router", "SINGLE_ROLES", "VendorDescriptor", "VendorRegistry", "as_legacy", "envelope", "estimate_tokens",
    "extract_json", "fetch_text", "load_providers_config", "prompt_hash", "send_json", "split_envelope",
]
