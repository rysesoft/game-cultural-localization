"""Deterministic fake provider adapter for --dry-run and test suites."""

import json
from pathlib import Path
from typing import Any

from gcl.domain.errors import L10nError, ModelNotFoundError, ProviderError
from gcl.domain.models import ChatRequest, ChatResult, RawVendorReply, TokenUsage
from gcl.infrastructure.formats.io_utils import load_json_data
from gcl.ports.llm import ProviderCapabilities

from ..envelope import estimate_tokens, prompt_hash, split_envelope

__layer__ = "infrastructure"
__pattern__ = "Mock Adapter"
__owns__ = "scenario driven offline FakeScenario and FakeProvider"

LITERAL_MARK = "literal]"
_SCENARIO_KEYS = ("responses", "errors", "scores", "pairwise", "deliberate", "pass2", "picks", "roundtrip", "default", "_comment")


class FakeScenario:
    """Validated JSON scenario rules driving FakeProvider replies."""

    def __init__(self, data: dict[str, Any] | None = None, source: str = "<inline>") -> None:
        data = dict(data or {})
        for k in data:
            if k not in _SCENARIO_KEYS and not k.startswith("_"):
                raise L10nError(f"{source}: unknown fake scenario key '{k}'; known: {', '.join(_SCENARIO_KEYS)}")
        self.responses: dict[str, str] = {str(k): str(v) for k, v in (data.get("responses") or {}).items()}
        self.errors: dict[str, str] = {str(k): str(v) for k, v in (data.get("errors") or {}).items()}
        self.rules: dict[str, list[dict[str, Any]]] = {}
        for k in ("scores", "pairwise", "deliberate", "pass2", "picks", "roundtrip"):
            items = data.get(k) or []
            if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
                raise L10nError(f"{source}: scenario '{k}' must be a list of objects")
            self.rules[k] = list(items)
        self.default: str | None = data.get("default")

    @classmethod
    def load(cls, path: Path | None) -> FakeScenario:
        if path is None:
            return cls()
        data = load_json_data(Path(path))
        if not isinstance(data, dict):
            raise L10nError(f"{path}: fake scenario must be a JSON object")
        return cls(data, str(path))


class FakeProvider:
    """Offline VendorTransportAdapter and LLMClient never touching network sockets."""

    name = "fake"
    capabilities = ProviderCapabilities(batched=False, supports_streaming=False)

    def __init__(self, model: str = "fake-model", family: str = "fake", scenario: FakeScenario | None = None, alias: str | None = None) -> None:
        self.model, self.family, self.alias = model, family, alias or model
        self.scenario = scenario or FakeScenario()
        self.calls: list[dict[str, Any]] = []

    def send(self, request: ChatRequest) -> RawVendorReply:
        h = prompt_hash(request.system, request.user)
        _instr, payload = split_envelope(request.user)
        task = str((payload or {}).get("task", ""))
        self.calls.append({"hash": h, "task": task, "model": self.model})
        text = self.scenario.responses.get(f"{self.model}:{h}", self.scenario.responses.get(h))
        if text is None:
            self._raise_configured_error()
            text = self._builtin(task, payload or {})
        if text is None:
            text = self.scenario.default if self.scenario.default is not None else "{}"
        tin, tout = estimate_tokens(request.system + request.user), estimate_tokens(text)
        return RawVendorReply(text=text, usage=TokenUsage(input_tokens=tin, output_tokens=tout))

    def complete(self, system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 2048, json_mode: bool = False) -> ChatResult:
        rep = self.send(ChatRequest(system=system, user=user, model=self.model, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode))
        return ChatResult(rep.text, rep.usage.input_tokens, rep.usage.output_tokens, self.model, 0)

    def _raise_configured_error(self) -> None:
        err = self.scenario.errors.get(self.model) or self.scenario.errors.get(self.alias)
        match err:
            case "not_found":
                raise ModelNotFoundError(f"fake/{self.model}: model not found (simulated)")
            case "server_error":
                raise ProviderError(f"fake/{self.model}: giving up after 5 attempts (simulated HTTP 503)")
            case "auth":
                raise ProviderError(f"fake/{self.model}: authentication failed (simulated HTTP 401)")

    def _match(self, rule: dict[str, Any], text: str = "", key: str = "", tier: str = "") -> bool:
        if "contains" in rule and str(rule["contains"]) not in text:
            return False
        if "key" in rule and str(rule["key"]) != key:
            return False
        if "model" in rule and str(rule["model"]) not in (self.model, self.alias):
            return False
        if "family" in rule and str(rule["family"]) != self.family:
            return False
        return not ("tier" in rule and str(rule["tier"]) != tier)

    def _first(self, kind: str, text: str = "", key: str = "", tier: str = "") -> dict[str, Any] | None:
        return next((r for r in self.scenario.rules.get(kind, []) if self._match(r, text, key, tier)), None)

    @staticmethod
    def _unmark(text: str) -> str:
        return text.split("] ", 1)[1] if text.startswith("[") and "] " in text else text

    def _revote(self, p: dict[str, Any]) -> dict[str, Any]:
        own = p.get("own") or {}
        rule = self._first("deliberate", str(p.get("target", "")), str(p.get("key", "")))
        if rule is not None:
            return {"score": int(rule.get("score", own.get("score", 3))), "issue_type": str(rule.get("issue_type", own.get("issue_type", "other"))),
                    "reason": str(rule.get("reason", "revised after deliberation")), "suggested": str(rule.get("suggested", own.get("suggested", "")))}
        return {"score": int(own.get("score", 3)), "issue_type": str(own.get("issue_type", "other")),
                "reason": str(own.get("reason", "")) or "keeps the first vote", "suggested": str(own.get("suggested", ""))}

    def _builtin(self, task: str, p: dict[str, Any]) -> str | None:
        locale = str(p.get("locale", "xx"))
        match task:
            case "pass1" | "literal":
                rows = [
                    {"key": r.get("key"), "target": r.get("target") or f"[{locale}] {r.get('source', '')}"} if task == "pass1"
                    else {"key": r.get("key"), "target": f"[{locale} literal] {r.get('source', '')}"}
                    for r in p.get("rows", [])
                ]
                return json.dumps({"rows": rows}, ensure_ascii=False)
            case "roundtrip":
                return self._roundtrip_json(p)
            case "jury":
                return self._jury_json(p)
            case "pairwise":
                return self._pairwise_json(p)
            case "deliberate":
                return json.dumps(self._revote(p), ensure_ascii=False)
            case "deliberate_many":
                return json.dumps({"votes": [{"key": str(ln.get("key", "")), **self._revote(ln)} for ln in p.get("lines", [])]}, ensure_ascii=False)
            case "pass2":
                return self._pass2_json(p)
            case "pick":
                return self._pick_json(p)
            case "ping":
                return json.dumps({"ok": True, "model": self.model}, ensure_ascii=False)
            case "critique":
                return json.dumps(
                    {"locale": locale, "source_file": p.get("source_file", ""), "entries": [],
                     "summary": {"total": len(p.get("entries", [])), "flagged": 0, "critical": 0}},
                    ensure_ascii=False,
                )
            case _:
                return None

    def _roundtrip_json(self, p: dict[str, Any]) -> str:
        out = []
        for r in p.get("rows", []):
            tgt = str(r.get("target", ""))
            rule = self._first("roundtrip", tgt, str(r.get("key", "")))
            back = str(rule.get("back", "")) if rule is not None else (self._unmark(tgt) if tgt.startswith("[") else " ".join(reversed(tgt.split())))
            out.append({"key": r.get("key"), "back": back})
        return json.dumps({"rows": out}, ensure_ascii=False)

    def _jury_json(self, p: dict[str, Any]) -> str:
        tier, votes = str(p.get("tier", "")), []
        for e in p.get("entries", []):
            tgt, key = str(e.get("target", "")), str(e.get("key", ""))
            rule = self._first("scores", tgt, key, tier)
            if rule is not None:
                sc = int(rule.get("score", 5))
                v: dict[str, Any] = {"key": key, "score": sc, "issue_type": str(rule.get("issue_type", "none" if sc == 5 else "other")),
                                     "reason": str(rule.get("reason", "" if sc == 5 else "scenario rule")), "suggested": str(rule.get("suggested", ""))}
                if "odd_words" in rule:
                    v["odd_words"] = list(rule["odd_words"])
            elif LITERAL_MARK in tgt:
                v = {"key": key, "score": 2, "issue_type": "translationese", "reason": "word for word calque", "suggested": self._unmark(tgt)}
            else:
                v = {"key": key, "score": 5, "issue_type": "none", "reason": "", "suggested": ""}
            votes.append(v)
        return json.dumps({"votes": votes}, ensure_ascii=False)

    def _pairwise_json(self, p: dict[str, Any]) -> str:
        out = []
        for pr in p.get("pairs", []):
            a, b, choice = str(pr.get("a", "")), str(pr.get("b", "")), "a"
            rule = next((c for c in self.scenario.rules.get("pairwise", [])
                         if self._match({k: v for k, v in c.items() if k != "contains"}) and str(c.get("contains", ""))
                         and (str(c["contains"]) in a or str(c["contains"]) in b)), None)
            if rule is not None:
                side = "a" if str(rule["contains"]) in a else "b"
                choice = side if rule.get("pick_containing", True) else ("b" if side == "a" else "a")
            elif (LITERAL_MARK in a) != (LITERAL_MARK in b):
                choice = "b" if LITERAL_MARK in a else "a"
            out.append({"id": pr.get("id"), "choice": choice})
        return json.dumps({"choices": out}, ensure_ascii=False)

    def _pass2_json(self, p: dict[str, Any]) -> str:
        n = int(p.get("n_candidates", 3))
        out = []
        for r in p.get("rows", []):
            tgt = str(r.get("target", ""))
            rule = self._first("pass2", tgt, str(r.get("key", "")))
            if rule is not None:
                cands = [str(c) for c in rule.get("candidates", [])]
            else:
                base = str(r.get("suggested") or "") or self._unmark(tgt)
                cands = [base] + [f"{base} ({i})" for i in range(2, n + 1)]
            out.append({"key": r.get("key"), "candidates": cands[:n]})
        return json.dumps({"rows": out}, ensure_ascii=False)

    def _pick_json(self, p: dict[str, Any]) -> str:
        out = []
        for it in p.get("items", []):
            cands = it.get("candidates", [])
            rule = self._first("picks", " ".join(str(c.get("text", "")) for c in cands), str(it.get("key", "")))
            choice = cands[0].get("id") if cands else None
            if rule is not None and "prefer" in rule:
                hits = [c for c in cands if str(rule["prefer"]) in str(c.get("text", ""))]
                choice = hits[0].get("id") if hits else choice
            elif rule is not None:
                choice = rule.get("choice", choice)
            out.append({"key": it.get("key"), "choice": choice})
        return json.dumps({"picks": out}, ensure_ascii=False)
