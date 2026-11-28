"""Facade delegating providers package exports to gcl.infrastructure.providers."""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcl.aspects.event_bus import BudgetLog  # noqa: E402
from gcl.domain.errors import MissingKeyError, ModelNotFoundError, ProviderError  # noqa: E402
from gcl.domain.models import ChatResult  # noqa: E402
from gcl.infrastructure.providers.adapters import (  # noqa: E402
    AnthropicProvider, DeepSeekProvider, FakeProvider, FakeScenario, FromLegacy, GoogleProvider, LegacyAdapter, as_legacy,
)
from gcl.infrastructure.providers.batch_backends import BACKENDS as BATCH_BACKENDS  # noqa: E402
from gcl.infrastructure.providers.batch_collector import BATCH_PRICE_FACTOR, BatchCollector  # noqa: E402
from gcl.infrastructure.providers.config import (  # noqa: E402
    CONTEXT_ROLES, DEFAULT_CONFIG_PATH, JURY_TIERS, OPTIONAL_SINGLE_ROLES, SINGLE_ROLES, ModelSpec, ProvidersConfig,
    load_providers_config,
)
from gcl.infrastructure.providers.envelope import envelope, estimate_tokens, extract_json, split_envelope  # noqa: E402
from gcl.infrastructure.providers.factory import Member, RoleProvider, Router  # noqa: E402
from gcl.infrastructure.providers.http_transport import HttpProvider, Transport  # noqa: E402
from gcl.infrastructure.providers.rate_limiter import RateLimiter  # noqa: E402
from gcl.infrastructure.providers.vendor_registry import DEFAULT_VENDOR_REGISTRY  # noqa: E402
from gcl.ports.llm import LLMClient as Provider  # noqa: E402

__all__ = [
    "BudgetLog", "ChatResult", "DEFAULT_CONFIG_PATH", "FakeProvider", "FakeScenario", "FromLegacy", "JURY_TIERS",
    "LegacyAdapter", "Member", "MissingKeyError", "ModelNotFoundError", "ModelSpec", "Provider", "ProviderError",
    "ProvidersConfig", "RateLimiter", "CONTEXT_ROLES", "OPTIONAL_SINGLE_ROLES", "RoleProvider", "Router",
    "SINGLE_ROLES", "as_legacy",
    "envelope", "estimate_tokens", "extract_json", "get_provider", "load_providers_config", "split_envelope",
]

PROVIDER_CLASSES: dict[str, Any] = DEFAULT_VENDOR_REGISTRY.provider_classes()


def get_provider(name: str, model: str, **kwargs: Any) -> Any:
    """Instantiate a provider by registry name via DEFAULT_VENDOR_REGISTRY."""
    return DEFAULT_VENDOR_REGISTRY.create(name, model, **kwargs)
