"""ProvidersConfig schema validation loading against VendorRegistry."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Union

from gcl.domain.errors import L10nError
from gcl.infrastructure.formats.io_utils import load_json_data
from gcl.infrastructure.paths import SCRIPTS_DIR

from .vendor_registry import DEFAULT_VENDOR_REGISTRY, VendorRegistry

__layer__ = "infrastructure"
__pattern__ = "Configuration Validator"
__owns__ = "providers.config.json loading, ModelSpec definitions and schema checks"

DEFAULT_CONFIG_PATH = SCRIPTS_DIR / "providers.config.json"
SINGLE_ROLES = ("pass1", "pass2", "roundtrip", "literal")
CONTEXT_ROLES = ("context_orchestrator", "context_agent")
JURY_TIERS = ("J1", "J2", "J3")
_TOP_KEYS = ("providers", "models", "roles", "agreement", "budget_caps", "roundtrip")
_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "agreement": {"pass_min": 4, "max_spread": 1, "critical_max": 2},
    "budget_caps": {"escalate_j2_ratio": 0.30, "escalate_j3_ratio": 0.10, "min_judged": 100, "min_escalated": 10},
    "roundtrip": {"min_words": 6, "registers": ["dialogue_casual", "dialogue_formal"]},
}


class ModelSpec(NamedTuple):
    """One configured model alias inside providers.config.json."""

    alias: str
    provider: str
    id: str
    price_in: Optional[float]
    price_out: Optional[float]
    fallback: Optional[str]
    fallback_thinking: bool
    price_cache_read: Optional[float] = None
    price_cache_write: Optional[float] = None
    max_output_tokens: Optional[int] = None


class ProvidersConfig:
    """Validated providers.config.json view."""

    def __init__(self, data: Dict[str, Any], path: Path) -> None:
        self.path = path
        self.raw = data
        self.providers: Dict[str, Dict[str, Any]] = data["providers"]
        self.models: Dict[str, ModelSpec] = {
            alias: ModelSpec(
                alias, m["provider"], m["id"], m.get("price_in"), m.get("price_out"),
                m.get("fallback"), bool(m.get("fallback_thinking", False)),
                m.get("price_cache_read"), m.get("price_cache_write"), m.get("max_output_tokens"),
            )
            for alias, m in data["models"].items()
        }
        self.roles: Dict[str, Union[str, List[str]]] = data["roles"]
        self.agreement: Dict[str, Any] = {**_DEFAULTS["agreement"], **(data.get("agreement") or {})}
        self.budget_caps: Dict[str, Any] = {**_DEFAULTS["budget_caps"], **(data.get("budget_caps") or {})}
        self.roundtrip: Dict[str, Any] = {**_DEFAULTS["roundtrip"], **(data.get("roundtrip") or {})}

    def role_model(self, role: str) -> ModelSpec:
        alias = self.roles.get(role)
        if not isinstance(alias, str):
            raise L10nError(f"{self.path}: role '{role}' is not a single-model role")
        return self.models[alias]

    def jury(self, tier: str) -> List[ModelSpec]:
        aliases = self.roles.get(tier)
        if not isinstance(aliases, list):
            raise L10nError(f"{self.path}: '{tier}' is not a jury tier; known: {', '.join(JURY_TIERS)}")
        return [self.models[a] for a in aliases]

    def specs_for_roles(self, roles: Iterable[str]) -> List[ModelSpec]:
        out: List[ModelSpec] = []
        for role in roles:
            specs = self.jury(role) if role in JURY_TIERS else [self.role_model(role)]
            for s in specs:
                if s not in out:
                    out.append(s)
        return out

    def env_key(self, spec: ModelSpec) -> str:
        return str(self.providers[spec.provider]["env_key"])


def _num_or_none(v: Any) -> bool:
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0)


def _validate_provider_entry(name: str, p: Any, path: Path, reg: VendorRegistry) -> None:
    if not reg.is_config_vendor(name):
        raise L10nError(f"{path}: unknown provider '{name}'; known: {', '.join(reg.config_vendor_names())}")
    if not isinstance(p, dict):
        raise L10nError(f"{path}: providers.{name} must be an object")
    if not isinstance(p.get("env_key"), str) or not p["env_key"]:
        raise L10nError(f"{path}: providers.{name}.env_key must name an environment variable")
    rps = p.get("rps")
    if not isinstance(rps, (int, float)) or isinstance(rps, bool) or rps <= 0:
        raise L10nError(f"{path}: providers.{name}.rps must be a number > 0")
    ep = p.get("endpoint")
    if not isinstance(ep, str) or not ep.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise L10nError(f"{path}: providers.{name}.endpoint must be an https URL")
    thinking = p.get("thinking", {})
    if not isinstance(thinking, dict) or not all(isinstance(v, bool) or v is None for v in thinking.values()):
        raise L10nError(f"{path}: providers.{name}.thinking must map roles to true, false or null")
    batch = p.get("batch")
    if batch is not None:
        if not reg.has_batch(name):
            raise L10nError(f"{path}: providers.{name}.batch is set, but only {', '.join(reg.batch_vendor_names())} have a batch API")
        if not isinstance(batch, dict):
            raise L10nError(f"{path}: providers.{name}.batch must be an object")
        for bk in ("price_factor", "linger_s", "poll_s", "max_requests"):
            v = batch.get(bk)
            if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0):
                raise L10nError(f"{path}: providers.{name}.batch.{bk} must be a number >= 0")


def _validate_model_entry(alias: str, m: Any, data: Dict[str, Any], path: Path) -> None:
    if not isinstance(m, dict):
        raise L10nError(f"{path}: models.{alias} must be an object")
    if m.get("provider") not in data["providers"]:
        raise L10nError(f"{path}: models.{alias}.provider '{m.get('provider')}' is not defined under 'providers'")
    if not isinstance(m.get("id"), str) or not m["id"].strip():
        raise L10nError(f"{path}: models.{alias}.id must be a non-empty string")
    for pk in ("price_in", "price_out", "price_cache_read", "price_cache_write"):
        if not _num_or_none(m.get(pk)):
            raise L10nError(f"{path}: models.{alias}.{pk} must be a number >= 0 or null (USD per 1M tokens)")
    mo = m.get("max_output_tokens")
    if mo is not None and (not isinstance(mo, int) or isinstance(mo, bool) or mo < 1):
        raise L10nError(f"{path}: models.{alias}.max_output_tokens must be a whole number >= 1 (the model's own output maximum)")
    fb = m.get("fallback")
    if fb is not None:
        if fb not in data["models"] or fb == alias:
            raise L10nError(f"{path}: models.{alias}.fallback '{fb}' is not another model alias")
        if data["models"][fb].get("fallback") is not None:
            raise L10nError(f"{path}: models.{alias}.fallback '{fb}' has its own fallback (chains are not allowed)")


def _validate_roles(roles: Dict[str, Any], models: Dict[str, Any], path: Path) -> None:
    for role in SINGLE_ROLES:
        if not isinstance(roles.get(role), str):
            raise L10nError(f"{path}: roles.{role} must name one model alias")
        if roles[role] not in models:
            raise L10nError(f"{path}: roles.{role} '{roles[role]}' is not a model alias")
    for role in CONTEXT_ROLES:
        if role in roles and (not isinstance(roles[role], str) or roles[role] not in models):
            raise L10nError(f"{path}: roles.{role} must name one model alias")
    for tier in JURY_TIERS:
        members = roles.get(tier)
        if not isinstance(members, list) or len(members) != 3 or not all(isinstance(a, str) for a in members):
            raise L10nError(f"{path}: roles.{tier} must list exactly three model aliases")
        families: Dict[str, str] = {}
        for a in members:
            if a not in models:
                raise L10nError(f"{path}: roles.{tier} member '{a}' is not a model alias")
            fam = models[a]["provider"]
            if fam in families:
                raise L10nError(
                    f"{path}: jury {tier} has two members from the same family '{fam}' ({families[fam]}, {a}); "
                    "every tier needs one anthropic, one google and one deepseek member"
                )
            families[fam] = a
    for k in roles:
        if k not in SINGLE_ROLES and k not in CONTEXT_ROLES and k not in JURY_TIERS:
            raise L10nError(f"{path}: unknown role '{k}'; known: {', '.join(SINGLE_ROLES + CONTEXT_ROLES + JURY_TIERS)}")


def _validate_policies(data: Dict[str, Any], path: Path) -> None:
    ag = {**_DEFAULTS["agreement"], **(data.get("agreement") or {})}
    for k in ("pass_min", "max_spread", "critical_max"):
        if not isinstance(ag.get(k), int) or isinstance(ag.get(k), bool) or not 0 <= ag[k] <= 5:
            raise L10nError(f"{path}: agreement.{k} must be an integer 0-5")
    caps = {**_DEFAULTS["budget_caps"], **(data.get("budget_caps") or {})}
    for k in ("escalate_j2_ratio", "escalate_j3_ratio"):
        v = caps.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 1:
            raise L10nError(f"{path}: budget_caps.{k} must be a ratio between 0 and 1")
    for k in ("min_judged", "min_escalated"):
        v = caps.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise L10nError(f"{path}: budget_caps.{k} must be a whole number >= 0")
    rt = {**_DEFAULTS["roundtrip"], **(data.get("roundtrip") or {})}
    if not isinstance(rt.get("min_words"), int) or rt["min_words"] < 0:
        raise L10nError(f"{path}: roundtrip.min_words must be a non-negative integer")
    if not isinstance(rt.get("registers"), list) or not all(isinstance(r, str) for r in rt["registers"]):
        raise L10nError(f"{path}: roundtrip.registers must be a list of register names")


def load_providers_config(path: Optional[Path] = None, registry: Optional[VendorRegistry] = None) -> ProvidersConfig:
    """Load and validate providers.config.json; raise L10nError on any schema violation."""
    target = Path(path) if path else DEFAULT_CONFIG_PATH
    reg = registry or DEFAULT_VENDOR_REGISTRY
    data = load_json_data(target)
    if not isinstance(data, dict):
        raise L10nError(f"{target}: providers config must be a JSON object")
    for k in data:
        if k not in _TOP_KEYS and not k.startswith("_"):
            raise L10nError(f"{target}: unknown key '{k}'; known: {', '.join(_TOP_KEYS)}")
    for k in ("providers", "models", "roles"):
        if not isinstance(data.get(k), dict) or not data[k]:
            raise L10nError(f"{target}: '{k}' must be a non-empty object")
    for name, p in data["providers"].items():
        _validate_provider_entry(name, p, target, reg)
    for alias, m in data["models"].items():
        _validate_model_entry(alias, m, data, target)
    _validate_roles(data["roles"], data["models"], target)
    _validate_policies(data, target)
    return ProvidersConfig(data, target)
