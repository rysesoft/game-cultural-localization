"""Open Closed vendor descriptor registry isolating adapter and batch wiring."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from gcl.domain.errors import L10nError

from .adapters import AnthropicProvider, DeepSeekProvider, FakeProvider, GoogleProvider
from .batch_backends import AnthropicBatchBackend, GoogleBatchBackend

__layer__ = "infrastructure"
__pattern__ = "Registry and Abstract Factory"
__owns__ = "pluggable vendor adapter, batch backend and option builder registration"

OptionsBuilder = Callable[[Any, Mapping[str, Any], str, bool], Dict[str, Any]]


@dataclass(frozen=True)
class VendorDescriptor:
    """Declarative metadata describing one LLM vendor family."""

    name: str
    adapter_cls: Any
    batch_backend_cls: Any = None
    supports_config: bool = True
    options_builder: Optional[OptionsBuilder] = None
    thinking_note_flag: bool = False
    supports_flex: bool = False


def _base_options(spec: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if getattr(spec, "max_output_tokens", None):
        out["max_output_tokens"] = spec.max_output_tokens
    return out


def _effort_options(spec: Any, provider_conf: Mapping[str, Any], role: str) -> Dict[str, Any]:
    out = _base_options(spec)
    conf = provider_conf.get("effort", {}) or {}
    val = conf.get(role, conf.get("default"))
    if isinstance(val, str) and val.strip():
        out["effort"] = val.strip().lower()
    return out


def _anthropic_options(spec: Any, provider_conf: Mapping[str, Any], role: str, force_thinking: bool) -> Dict[str, Any]:
    return _effort_options(spec, provider_conf, role)


def _google_options(spec: Any, provider_conf: Mapping[str, Any], role: str, force_thinking: bool) -> Dict[str, Any]:
    out = _effort_options(spec, provider_conf, role)
    stier = provider_conf.get("service_tier")
    if isinstance(stier, str) and stier.strip():
        out["service_tier"] = stier.strip().lower()
    return out


def _deepseek_options(spec: Any, provider_conf: Mapping[str, Any], role: str, force_thinking: bool) -> Dict[str, Any]:
    out = _base_options(spec)
    conf = provider_conf.get("thinking", {}) or {}
    val = conf.get(role, conf.get("default"))
    if force_thinking and val is False:
        val = True
    out["thinking"] = val
    return out


class VendorRegistry:
    """Open Closed registry decoupling Router and config validation from vendor classes."""

    def __init__(self) -> None:
        self._vendors: Dict[str, VendorDescriptor] = {}

    def register(self, descriptor: VendorDescriptor) -> None:
        self._vendors[descriptor.name] = descriptor

    def get(self, name: str) -> Optional[VendorDescriptor]:
        return self._vendors.get(name)

    def create(self, name: str, model: str, **kwargs: Any) -> Any:
        desc = self._vendors.get(name)
        if desc is None:
            known = ", ".join(sorted(self._vendors))
            raise L10nError(f"unknown provider '{name}'; known: {known}")
        return desc.adapter_cls(model=model, **kwargs)

    def is_config_vendor(self, name: str) -> bool:
        desc = self._vendors.get(name)
        return bool(desc and desc.supports_config)

    def config_vendor_names(self) -> List[str]:
        return sorted(k for k, v in self._vendors.items() if v.supports_config)

    def has_batch(self, name: str) -> bool:
        desc = self._vendors.get(name)
        return bool(desc and desc.batch_backend_cls is not None)

    def batch_vendor_names(self) -> List[str]:
        return sorted(k for k, v in self._vendors.items() if v.batch_backend_cls is not None)

    def batch_backend_cls(self, name: str) -> Any:
        desc = self._vendors.get(name)
        return desc.batch_backend_cls if desc else None

    def provider_classes(self) -> Dict[str, Any]:
        return {k: v.adapter_cls for k, v in self._vendors.items()}

    def build_options(
        self, spec: Any, provider_conf: Mapping[str, Any], role: str, force_thinking: bool, *, flex: bool = False,
    ) -> Dict[str, Any]:
        desc = self._vendors.get(spec.provider)
        out = desc.options_builder(spec, provider_conf, role, force_thinking) if (desc and desc.options_builder is not None) else _base_options(spec)
        if flex and desc and desc.supports_flex and "service_tier" not in out:
            out["service_tier"] = "flex"
        return out

    def fallback_suffix(self, provider_name: str, fallback_thinking: bool) -> str:
        desc = self._vendors.get(provider_name)
        return " in thinking mode" if (fallback_thinking and desc and desc.thinking_note_flag) else ""


def build_default_vendor_registry() -> VendorRegistry:
    """Create the default registry with built in HTTP vendors and FakeProvider."""
    reg = VendorRegistry()
    reg.register(VendorDescriptor("anthropic", AnthropicProvider, batch_backend_cls=AnthropicBatchBackend, options_builder=_anthropic_options))
    reg.register(VendorDescriptor("google", GoogleProvider, batch_backend_cls=GoogleBatchBackend, options_builder=_google_options, supports_flex=True))
    reg.register(VendorDescriptor("deepseek", DeepSeekProvider, options_builder=_deepseek_options, thinking_note_flag=True))
    reg.register(VendorDescriptor("fake", FakeProvider, supports_config=False))
    return reg


DEFAULT_VENDOR_REGISTRY = build_default_vendor_registry()
