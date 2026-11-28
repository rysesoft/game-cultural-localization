"""Provider Router, Member and RoleProvider weaving AOP telemetry and fallback."""

import os
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, NamedTuple

from gcl.aspects.call_chain import (
    AspectChain, BudgetTelemetryAspect, FallbackModelAspect, ProceedCall, ThinkingEffortAspect,
)
from gcl.aspects.event_bus import BudgetLog, BudgetLogSubscriber, InMemoryEventBus
from gcl.domain.errors import L10nError, MissingKeyError, ModelNotFoundError
from gcl.domain.models import ChatRequest, ChatResult
from gcl.ports.llm import ProviderCapabilities

from .adapters import FakeProvider, FakeScenario
from .batch_collector import BatchCollector
from .config import ModelSpec, ProvidersConfig
from .vendor_registry import DEFAULT_VENDOR_REGISTRY, VendorRegistry

__layer__ = "infrastructure"
__pattern__ = "Factory and Proxy with AOP Interceptors"
__owns__ = "RoleProvider, Member and Router wiring VendorRegistry, batching and EventBus telemetry"


class Member(NamedTuple):
    """One jury seat bound to a RoleProvider."""

    tier: str
    index: int
    alias: str
    family: str
    model: str
    provider: RoleProvider


class RoleProvider:
    """Role scoped LLMClient proxy applying FallbackModelAspect and BudgetTelemetryAspect."""

    def __init__(self, router: Router, spec: ModelSpec, role: str, *, task_role: str | None = None) -> None:
        self.router = router
        self.spec = spec
        self.role = role
        self.task_role = task_role or role
        self.fallback_from: str | None = None
        self._impl = router._batch_wrap(spec, router._instantiate(spec, self.task_role, force_thinking=False))

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

    @property
    def batched(self) -> bool:
        caps = getattr(self._impl, "capabilities", None)
        return bool(caps.batched) if caps is not None else bool(getattr(self._impl, "batched", False))

    @property
    def capabilities(self) -> ProviderCapabilities:
        caps = getattr(self._impl, "capabilities", None)
        return caps if isinstance(caps, ProviderCapabilities) else ProviderCapabilities(batched=self.batched)

    def _telemetry_meta(self) -> dict[str, object]:
        opts = getattr(self._impl, "options", None) or {}
        return {
            "role": self.role, "provider": self.spec.provider, "alias": self.spec.alias,
            "model": self.spec.id, "batched": self.batched,
            "flex": bool(opts.get("service_tier") == "flex") and not self.batched,
            "dry_run": self.router.dry_run, "fallback_from": self.fallback_from or "",
        }

    def _call_impl(self, req: ChatRequest) -> ChatResult:
        return self._impl.complete(
            req.system, req.user, temperature=req.temperature, max_tokens=req.max_tokens, json_mode=req.json_mode,
        )

    def _switch_fallback(self, exc: ModelNotFoundError) -> ProceedCall:
        if self.fallback_from is not None or not self.spec.fallback:
            raise L10nError(f"model '{self.spec.id}' ({self.spec.alias}) was not found and no fallback is configured: {exc}")
        old = self.spec
        new = self.router.config.models[old.fallback]
        self.router._missing_key_check([new])
        self.fallback_from = old.id
        self.spec = new
        self._impl = self.router._instantiate(new, self.task_role, force_thinking=old.fallback_thinking)
        suffix = self.router._registry.fallback_suffix(new.provider, old.fallback_thinking)
        self.router.note(f"{old.alias} ({old.id}) not found for role {self.role}, using fallback {new.alias} ({new.id}){suffix}")
        return self._call_impl

    def complete(
        self, system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 2048, json_mode: bool = False,
    ) -> ChatResult:
        req = ChatRequest(
            system=system, user=user, role=self.role, model=self.spec.id,
            temperature=temperature, max_tokens=max_tokens, json_mode=json_mode,
        )
        chain = AspectChain(
            self._call_impl,
            (
                BudgetTelemetryAspect(self.router.event_bus, self._telemetry_meta),
                ThinkingEffortAspect(lambda: dict(getattr(self._impl, "options", None) or {})),
                FallbackModelAspect(self._switch_fallback),
            ),
        )
        return chain.invoke(req)


class Router:
    """Factory building role scoped RoleProvider proxies via VendorRegistry."""

    def __init__(self, config: ProvidersConfig, **kw: Any) -> None:
        self.config = config
        self.dry_run = bool(kw.get("dry_run", False))
        self.batch = bool(kw.get("batch", False))
        self.flex = bool(kw.get("flex", False))
        self.get_transport = kw.get("get_transport")
        self._registry: VendorRegistry = kw.get("registry") or DEFAULT_VENDOR_REGISTRY
        self._collectors: dict[str, BatchCollector] = {}
        self.scenario: FakeScenario = kw.get("scenario") or FakeScenario()
        self.budget = BudgetLog(kw.get("budget_log"))
        self.event_bus: InMemoryEventBus = kw.get("event_bus") or InMemoryEventBus()
        self.event_bus.subscribe(BudgetLogSubscriber(self.budget))
        env = kw.get("env")
        self.env: Mapping[str, str] = env if env is not None else os.environ
        self.transport = kw.get("transport")
        self.sleep = kw.get("sleep")
        self.notes: list[str] = []
        self._fakes: dict[str, FakeProvider] = {}

    def note(self, msg: str) -> None:
        if msg not in self.notes:
            self.notes.append(msg)

    def _missing_key_check(self, specs: Sequence[ModelSpec]) -> None:
        if self.dry_run:
            return
        missing = sorted({self.config.env_key(s) for s in specs if not str(self.env.get(self.config.env_key(s), "")).strip()})
        if missing:
            raise MissingKeyError(
                "missing API key environment variable(s): " + ", ".join(missing)
                + " (set them in the environment, or use --dry-run for the offline fake provider)"
            )

    def require(self, roles: Iterable[str]) -> None:
        """Fail early with MissingKeyError when a required API key env var is absent."""
        self._missing_key_check(self.config.specs_for_roles(list(roles)))

    def _thinking(self, spec: ModelSpec, role: str, force: bool) -> bool | None:
        """Resolve per role thinking setting via providers config without vendor hardcoding."""
        conf = self.config.providers.get(spec.provider, {}).get("thinking", {}) or {}
        value = conf.get(role, conf.get("default"))
        return True if (force and value is False) else value

    def _instantiate(self, spec: ModelSpec, role: str, force_thinking: bool) -> Any:
        if self.dry_run:
            fake = self._fakes.get(spec.alias)
            if fake is None:
                fake = FakeProvider(model=spec.id, family=spec.provider, scenario=self.scenario, alias=spec.alias)
                self._fakes[spec.alias] = fake
            return fake
        self._missing_key_check([spec])
        pconf = self.config.providers[spec.provider]
        options = self._registry.build_options(spec, pconf, role, force_thinking, flex=self.flex)
        kwargs: dict[str, Any] = {
            "api_key": str(self.env.get(pconf["env_key"], "")).strip(),
            "endpoint": pconf["endpoint"],
            "rps": float(pconf["rps"]),
            "options": options,
        }
        if self.transport is not None:
            kwargs["transport"] = self.transport
        if self.sleep is not None:
            kwargs["sleep"] = self.sleep
        return self._registry.create(spec.provider, spec.id, **kwargs)

    def _batch_wrap(self, spec: ModelSpec, impl: Any) -> Any:
        backend_cls = self._registry.batch_backend_cls(spec.provider)
        if not self.batch or self.dry_run or backend_cls is None:
            return impl
        conf = self.config.providers.get(spec.provider, {}).get("batch") or {}
        col = self._collectors.get(spec.alias)
        if col is None:
            kw: dict[str, Any] = {k: conf[k] for k in ("linger_s", "poll_s", "max_requests") if conf.get(k) is not None}
            if self.sleep is not None:
                kw["sleep"] = self.sleep
            col = BatchCollector(backend_cls(impl, get=self.get_transport), **kw)
            self._collectors[spec.alias] = col
        return col

    def batch_jobs(self) -> list[dict[str, Any]]:
        return [j for c in self._collectors.values() for j in c.jobs]

    def for_model(self, alias: str, role: str, *, task_role: str | None = None) -> RoleProvider:
        if alias not in self.config.models:
            raise L10nError(f"unknown model alias '{alias}'; known: {', '.join(self.config.models)}")
        return RoleProvider(self, self.config.models[alias], role, task_role=task_role)

    def for_role(self, role: str, *, task_role: str | None = None) -> RoleProvider:
        return RoleProvider(self, self.config.role_model(role), role, task_role=task_role)

    def jury(self, tier: str, *, task_role: str | None = None) -> list[Member]:
        return [
            Member(tier, i, spec.alias, spec.provider, spec.id, RoleProvider(self, spec, tier, task_role=task_role))
            for i, spec in enumerate(self.config.jury(tier))
        ]

    def fake(self, alias: str) -> FakeProvider | None:
        return self._fakes.get(alias)
