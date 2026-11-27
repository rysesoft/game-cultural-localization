"""LLM provider registry, providers.config.json loader and role router.

    from providers import get_provider, load_providers_config, Router
    cfg = load_providers_config()                 # scripts/providers.config.json
    router = Router(cfg, dry_run=True)            # fake provider, no network
    pass1 = router.for_role("pass1")              # logged, fallback aware Provider
    jury = router.jury("J1")                      # three members, one per family

Model ids live only in providers.config.json. API keys are read from the
environment variables the config names (ANTHROPIC_API_KEY, GOOGLE_API_KEY,
DEEPSEEK_API_KEY); they are never written to any file.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Union

from l10n_common import SCRIPTS_DIR, L10nError, load_json_data

from .anthropic import AnthropicProvider
from .base import (
    BudgetLog, ChatResult, FromLegacy, HttpProvider, LegacyAdapter, MissingKeyError, ModelNotFoundError, Provider,
    ProviderError, RateLimiter, Transport, as_legacy, envelope, estimate_tokens, extract_json, split_envelope,
)
from .deepseek import DeepSeekProvider
from .fake import FakeProvider, FakeScenario
from .google import GoogleProvider

__all__ = [
    "BudgetLog", "ChatResult", "DEFAULT_CONFIG_PATH", "FakeProvider", "FakeScenario", "FromLegacy", "JURY_TIERS", "LegacyAdapter",
    "Member", "MissingKeyError", "ModelNotFoundError", "ModelSpec", "Provider", "ProviderError", "ProvidersConfig", "RateLimiter",
    "CONTEXT_ROLES", "RoleProvider", "Router", "SINGLE_ROLES", "as_legacy", "envelope", "estimate_tokens", "extract_json", "get_provider",
    "load_providers_config", "split_envelope",
]

DEFAULT_CONFIG_PATH = SCRIPTS_DIR / "providers.config.json"
PROVIDER_CLASSES: Dict[str, Any] = {
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "deepseek": DeepSeekProvider,
    "fake": FakeProvider,
}
SINGLE_ROLES = ("pass1", "pass2", "roundtrip", "literal")
# context map, the mandatory first step: one orchestrator (strongest model) and its field agents
CONTEXT_ROLES = ("context_orchestrator", "context_agent")
JURY_TIERS = ("J1", "J2", "J3")
_TOP_KEYS = ("providers", "models", "roles", "agreement", "budget_caps", "roundtrip")
_DEFAULTS = {
    "agreement": {"pass_min": 4, "max_spread": 1, "critical_max": 2},
    "budget_caps": {"escalate_j2_ratio": 0.30, "escalate_j3_ratio": 0.10},
    "roundtrip": {"min_words": 6, "registers": ["dialogue_casual", "dialogue_formal"]},
}


def get_provider(name: str, model: str, **kwargs: Any) -> Any:
    """Instantiate a provider by registry name ('anthropic', 'google', 'deepseek', 'fake')."""
    cls = PROVIDER_CLASSES.get(name)
    if cls is None:
        raise L10nError(f"unknown provider '{name}'; known: {', '.join(sorted(PROVIDER_CLASSES))}")
    return cls(model=model, **kwargs)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
class ModelSpec(NamedTuple):
    """One model entry of providers.config.json."""
    alias: str
    provider: str
    id: str
    price_in: Optional[float]
    price_out: Optional[float]
    fallback: Optional[str]
    fallback_thinking: bool
    price_cache_read: Optional[float] = None    # USD per 1M prompt tokens served from the cache, None = price_in
    price_cache_write: Optional[float] = None   # USD per 1M prompt tokens written to the cache, None = price_in


class ProvidersConfig:
    """Validated providers.config.json."""

    def __init__(self, data: Dict[str, Any], path: Path) -> None:
        self.path = path
        self.raw = data
        self.providers: Dict[str, Dict[str, Any]] = data["providers"]
        self.models: Dict[str, ModelSpec] = {}
        for alias, m in data["models"].items():
            self.models[alias] = ModelSpec(alias, m["provider"], m["id"], m.get("price_in"), m.get("price_out"),
                                           m.get("fallback"), bool(m.get("fallback_thinking", False)),
                                           m.get("price_cache_read"), m.get("price_cache_write"))
        self.roles: Dict[str, Union[str, List[str]]] = data["roles"]
        self.agreement: Dict[str, Any] = {**_DEFAULTS["agreement"], **(data.get("agreement") or {})}
        self.budget_caps: Dict[str, Any] = {**_DEFAULTS["budget_caps"], **(data.get("budget_caps") or {})}
        self.roundtrip: Dict[str, Any] = {**_DEFAULTS["roundtrip"], **(data.get("roundtrip") or {})}

    def role_model(self, role: str) -> ModelSpec:
        """Model of a single-model role (pass1, pass2, roundtrip, literal)."""
        alias = self.roles.get(role)
        if not isinstance(alias, str):
            raise L10nError(f"{self.path}: role '{role}' is not a single-model role")
        return self.models[alias]

    def jury(self, tier: str) -> List[ModelSpec]:
        """The three members of a jury tier (J1, J2, J3)."""
        aliases = self.roles.get(tier)
        if not isinstance(aliases, list):
            raise L10nError(f"{self.path}: '{tier}' is not a jury tier; known: {', '.join(JURY_TIERS)}")
        return [self.models[a] for a in aliases]

    def specs_for_roles(self, roles: Iterable[str]) -> List[ModelSpec]:
        """Every model needed by the given roles (deduplicated, config order)."""
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


def load_providers_config(path: Optional[Path] = None) -> ProvidersConfig:
    """Load and validate providers.config.json; every problem is an L10nError (exit 2)."""
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    data = load_json_data(path)
    if not isinstance(data, dict):
        raise L10nError(f"{path}: providers config must be a JSON object")
    for k in data:
        if k not in _TOP_KEYS and not k.startswith("_"):
            raise L10nError(f"{path}: unknown key '{k}'; known: {', '.join(_TOP_KEYS)}")
    for k in ("providers", "models", "roles"):
        if not isinstance(data.get(k), dict) or not data[k]:
            raise L10nError(f"{path}: '{k}' must be a non-empty object")
    for name, p in data["providers"].items():
        if name not in PROVIDER_CLASSES or name == "fake":
            raise L10nError(f"{path}: unknown provider '{name}'; known: anthropic, deepseek, google")
        if not isinstance(p, dict):
            raise L10nError(f"{path}: providers.{name} must be an object")
        if not isinstance(p.get("env_key"), str) or not p["env_key"]:
            raise L10nError(f"{path}: providers.{name}.env_key must name an environment variable")
        rps = p.get("rps")
        if not isinstance(rps, (int, float)) or isinstance(rps, bool) or rps <= 0:
            raise L10nError(f"{path}: providers.{name}.rps must be a number > 0")
        ep = p.get("endpoint")
        if not isinstance(ep, str) or not (ep.startswith("https://") or ep.startswith("http://127.0.0.1") or ep.startswith("http://localhost")):
            raise L10nError(f"{path}: providers.{name}.endpoint must be an https URL")
        thinking = p.get("thinking", {})
        if not isinstance(thinking, dict) or not all(isinstance(v, bool) or v is None for v in thinking.values()):
            raise L10nError(f"{path}: providers.{name}.thinking must map roles to true, false or null")
    for alias, m in data["models"].items():
        if not isinstance(m, dict):
            raise L10nError(f"{path}: models.{alias} must be an object")
        if m.get("provider") not in data["providers"]:
            raise L10nError(f"{path}: models.{alias}.provider '{m.get('provider')}' is not defined under 'providers'")
        if not isinstance(m.get("id"), str) or not m["id"].strip():
            raise L10nError(f"{path}: models.{alias}.id must be a non-empty string")
        for pk in ("price_in", "price_out", "price_cache_read", "price_cache_write"):
            if not _num_or_none(m.get(pk)):
                raise L10nError(f"{path}: models.{alias}.{pk} must be a number >= 0 or null (USD per 1M tokens)")
        fb = m.get("fallback")
        if fb is not None:
            if fb not in data["models"] or fb == alias:
                raise L10nError(f"{path}: models.{alias}.fallback '{fb}' is not another model alias")
            if data["models"][fb].get("fallback") is not None:
                raise L10nError(f"{path}: models.{alias}.fallback '{fb}' has its own fallback (chains are not allowed)")
    roles = data["roles"]
    for role in SINGLE_ROLES:
        if not isinstance(roles.get(role), str):
            raise L10nError(f"{path}: roles.{role} must name one model alias")
        if roles[role] not in data["models"]:
            raise L10nError(f"{path}: roles.{role} '{roles[role]}' is not a model alias")
    for role in CONTEXT_ROLES:  # optional in a custom config, set in the bundled one
        if role in roles and (not isinstance(roles[role], str) or roles[role] not in data["models"]):
            raise L10nError(f"{path}: roles.{role} must name one model alias")
    for tier in JURY_TIERS:
        members = roles.get(tier)
        if not isinstance(members, list) or len(members) != 3 or not all(isinstance(a, str) for a in members):
            raise L10nError(f"{path}: roles.{tier} must list exactly three model aliases")
        families: Dict[str, str] = {}
        for a in members:
            if a not in data["models"]:
                raise L10nError(f"{path}: roles.{tier} member '{a}' is not a model alias")
            fam = data["models"][a]["provider"]
            if fam in families:
                raise L10nError(f"{path}: jury {tier} has two members from the same family '{fam}' ({families[fam]}, {a}); "
                                "every tier needs one anthropic, one google and one deepseek member")
            families[fam] = a
    for k in roles:
        if k not in SINGLE_ROLES and k not in CONTEXT_ROLES and k not in JURY_TIERS:
            raise L10nError(f"{path}: unknown role '{k}'; known: {', '.join(SINGLE_ROLES + CONTEXT_ROLES + JURY_TIERS)}")
    ag = {**_DEFAULTS["agreement"], **(data.get("agreement") or {})}
    for k in ("pass_min", "max_spread", "critical_max"):
        if not isinstance(ag.get(k), int) or isinstance(ag.get(k), bool) or not 0 <= ag[k] <= 5:
            raise L10nError(f"{path}: agreement.{k} must be an integer 0-5")
    caps = {**_DEFAULTS["budget_caps"], **(data.get("budget_caps") or {})}
    for k in ("escalate_j2_ratio", "escalate_j3_ratio"):
        v = caps.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 1:
            raise L10nError(f"{path}: budget_caps.{k} must be a ratio between 0 and 1")
    rt = {**_DEFAULTS["roundtrip"], **(data.get("roundtrip") or {})}
    if not isinstance(rt.get("min_words"), int) or rt["min_words"] < 0:
        raise L10nError(f"{path}: roundtrip.min_words must be a non-negative integer")
    if not isinstance(rt.get("registers"), list) or not all(isinstance(r, str) for r in rt["registers"]):
        raise L10nError(f"{path}: roundtrip.registers must be a list of register names")
    return ProvidersConfig(data, path)


# --------------------------------------------------------------------------- #
# Router: role -> logged, fallback aware provider
# --------------------------------------------------------------------------- #
class Member(NamedTuple):
    """One jury seat."""
    tier: str
    index: int
    alias: str
    family: str
    model: str
    provider: "RoleProvider"


class RoleProvider:
    """Provider bound to a role: writes budget.jsonl and switches to the fallback model on 'not found'."""

    def __init__(self, router: "Router", spec: ModelSpec, role: str) -> None:
        self.router = router
        self.spec = spec
        self.role = role
        self.fallback_from: Optional[str] = None
        self._impl = router._instantiate(spec, role, force_thinking=False)

    @property
    def name(self) -> str:
        return self._impl.name

    @property
    def model(self) -> str:
        return self.spec.id

    @property
    def family(self) -> str:
        return self.spec.provider

    @property
    def alias(self) -> str:
        return self.spec.alias

    def complete(self, system: str, user: str, *, temperature: float = 0.0,
                 max_tokens: int = 2048, json_mode: bool = False) -> ChatResult:
        """Call the model; on ModelNotFoundError switch once to the configured fallback and note it."""
        kw = {"temperature": temperature, "max_tokens": max_tokens, "json_mode": json_mode}
        try:
            res = self._impl.complete(system, user, **kw)
        except ModelNotFoundError as exc:
            if self.fallback_from is not None or not self.spec.fallback:
                self._log(None, error=str(exc))
                raise L10nError(f"model '{self.spec.id}' ({self.spec.alias}) was not found and no fallback is configured: {exc}")
            old = self.spec
            new = self.router.config.models[old.fallback]  # type: ignore[index]
            self.router._missing_key_check([new])
            self.fallback_from = old.id
            self.spec = new
            self._impl = self.router._instantiate(new, self.role, force_thinking=old.fallback_thinking)
            self.router.note(f"{old.alias} ({old.id}) not found for role {self.role}, using fallback {new.alias} ({new.id})"
                             + (" in thinking mode" if old.fallback_thinking and new.provider == "deepseek" else ""))
            try:
                res = self._impl.complete(system, user, **kw)
            except ProviderError as exc2:
                self._log(None, error=str(exc2))
                raise
        except ProviderError as exc:
            self._log(None, error=str(exc))
            raise
        self._log(res)
        return res

    def _log(self, res: Optional[ChatResult], error: Optional[str] = None) -> None:
        rec: Dict[str, Any] = {"role": self.role, "provider": self.spec.provider, "alias": self.spec.alias, "model": self.spec.id,
                               "input_tokens": res.input_tokens if res else 0, "output_tokens": res.output_tokens if res else 0,
                               "latency_ms": res.latency_ms if res else 0, "ok": error is None}
        if res is not None and res.cache_read_tokens:
            rec["cache_read_tokens"] = res.cache_read_tokens
        if res is not None and res.cache_write_tokens:
            rec["cache_write_tokens"] = res.cache_write_tokens
        if self.router.dry_run:
            rec["dry_run"] = True
        if self.fallback_from:
            rec["fallback_from"] = self.fallback_from
        if error:
            rec["error"] = error[:300]
        self.router.budget.write(rec)


class Router:
    """Builds providers for roles from a ProvidersConfig (real adapters, or FakeProvider with dry_run)."""

    def __init__(self, config: ProvidersConfig, *, dry_run: bool = False, scenario: Optional[FakeScenario] = None,
                 budget_log: Optional[Path] = None, env: Optional[Mapping[str, str]] = None,
                 transport: Optional[Transport] = None, sleep: Optional[Callable[[float], None]] = None) -> None:
        self.config = config
        self.dry_run = dry_run
        self.scenario = scenario or FakeScenario()
        self.budget = BudgetLog(budget_log)
        self.env = env if env is not None else os.environ
        self.transport = transport
        self.sleep = sleep
        self.notes: List[str] = []
        self._fakes: Dict[str, FakeProvider] = {}

    def note(self, msg: str) -> None:
        if msg not in self.notes:
            self.notes.append(msg)

    # keys ------------------------------------------------------------------ #
    def _missing_key_check(self, specs: Sequence[ModelSpec]) -> None:
        if self.dry_run:
            return
        missing = sorted({self.config.env_key(s) for s in specs if not str(self.env.get(self.config.env_key(s), "")).strip()})
        if missing:
            raise MissingKeyError("missing API key environment variable(s): " + ", ".join(missing)
                                  + " (set them in the environment, or use --dry-run for the offline fake provider)")

    def require(self, roles: Iterable[str]) -> None:
        """Fail early (MissingKeyError, exit 2) when a key needed by these roles is not set."""
        self._missing_key_check(self.config.specs_for_roles(list(roles)))

    # providers ------------------------------------------------------------- #
    def _thinking(self, spec: ModelSpec, role: str, force: bool) -> Optional[bool]:
        conf = self.config.providers.get(spec.provider, {}).get("thinking", {}) or {}
        value = conf.get(role, conf.get("default"))
        if force and value is False:
            value = True
        return value

    def _instantiate(self, spec: ModelSpec, role: str, force_thinking: bool) -> Any:
        if self.dry_run:
            fake = self._fakes.get(spec.alias)
            if fake is None:
                fake = FakeProvider(model=spec.id, family=spec.provider, scenario=self.scenario, alias=spec.alias)
                self._fakes[spec.alias] = fake
            return fake
        self._missing_key_check([spec])
        pconf = self.config.providers[spec.provider]
        options: Dict[str, Any] = {}
        if spec.provider == "deepseek":
            options["thinking"] = self._thinking(spec, role, force_thinking)
        kwargs: Dict[str, Any] = {"api_key": str(self.env.get(pconf["env_key"], "")).strip(), "endpoint": pconf["endpoint"],
                                  "rps": float(pconf["rps"]), "options": options}
        if self.transport is not None:
            kwargs["transport"] = self.transport
        if self.sleep is not None:
            kwargs["sleep"] = self.sleep
        return get_provider(spec.provider, spec.id, **kwargs)

    def for_model(self, alias: str, role: str) -> RoleProvider:
        """Provider for an explicit model alias, logged under `role`."""
        if alias not in self.config.models:
            raise L10nError(f"unknown model alias '{alias}'; known: {', '.join(self.config.models)}")
        return RoleProvider(self, self.config.models[alias], role)

    def for_role(self, role: str) -> RoleProvider:
        """Provider of a single-model role (pass1, pass2, roundtrip, literal)."""
        return RoleProvider(self, self.config.role_model(role), role)

    def jury(self, tier: str) -> List[Member]:
        """The three seats of a jury tier, each logged under the tier name."""
        out: List[Member] = []
        for i, spec in enumerate(self.config.jury(tier)):
            rp = RoleProvider(self, spec, tier)
            out.append(Member(tier, i, spec.alias, spec.provider, spec.id, rp))
        return out

    def fake(self, alias: str) -> Optional[FakeProvider]:
        """The FakeProvider behind an alias in dry-run mode (for inspection in tests)."""
        return self._fakes.get(alias)
