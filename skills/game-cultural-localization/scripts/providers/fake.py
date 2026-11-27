"""Deterministic fake provider for tests and --dry-run (no network, no randomness).

Lookup order for every call:
  1. scenario "responses": prompt hash (or "<model>:<hash>") -> raw reply text
  2. scenario "errors": model id or alias -> simulated failure ("not_found", "server_error", "auth")
  3. built-in task handler, driven by the JSON payload of the user prompt ("task" field),
     with per-entry scenario rules ("scores", "pairwise", "deliberate", "pass2", "picks", "roundtrip")
  4. scenario "default" reply, else "{}"

Built-in behaviour (so a dry run produces plausible, deterministic data):
  pass1      target = "[<locale>] <source>"
  literal    target = "[<locale> literal] <source>"
  roundtrip  back   = target without its "[...] " marker (a calque), else the words reversed
  jury       score 2 / translationese for lines carrying the "literal]" marker, else 5 / none
  pairwise   picks the side without the "literal]" marker (side "a" when undecided)
  deliberate repeats the member's own first score
  pass2      three candidates (suggestion or target, then two numbered variants)
  pick       first candidate

Scenario file (JSON):
  {"responses": {"<hash>": "..."}, "errors": {"deepseek-v4-pro": "not_found"},
   "scores": [{"contains": "text", "key": "K", "model": "id|alias", "family": "anthropic", "tier": "J1",
               "score": 3, "issue_type": "register", "reason": "...", "suggested": "..."}],
   "pairwise": [{"contains": "literal]", "model": "...", "pick_containing": true}],
   "deliberate": [{"key": "K", "model": "...", "score": 4, "reason": "..."}],
   "pass2": [{"contains": "...", "candidates": ["...", "...", "..."]}],
   "picks": [{"contains": "...", "model": "...", "prefer": "text in the wanted candidate"}],
   "roundtrip": [{"contains": "...", "back": "..."}],
   "default": "..."}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from l10n_common import L10nError, load_json_data

from .base import ChatResult, ModelNotFoundError, ProviderError, estimate_tokens, prompt_hash, split_envelope

LITERAL_MARK = "literal]"
_SCENARIO_KEYS = ("responses", "errors", "scores", "pairwise", "deliberate", "pass2", "picks", "roundtrip", "default", "_comment")


class FakeScenario:
    """Parsed scenario file for FakeProvider."""

    def __init__(self, data: Optional[Dict[str, Any]] = None, source: str = "<inline>") -> None:
        data = dict(data or {})
        for k in data:
            if k not in _SCENARIO_KEYS and not k.startswith("_"):
                raise L10nError(f"{source}: unknown fake scenario key '{k}'; known: {', '.join(_SCENARIO_KEYS)}")
        self.responses: Dict[str, str] = {str(k): str(v) for k, v in (data.get("responses") or {}).items()}
        self.errors: Dict[str, str] = {str(k): str(v) for k, v in (data.get("errors") or {}).items()}
        self.rules: Dict[str, List[Dict[str, Any]]] = {}
        for k in ("scores", "pairwise", "deliberate", "pass2", "picks", "roundtrip"):
            items = data.get(k) or []
            if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
                raise L10nError(f"{source}: scenario '{k}' must be a list of objects")
            self.rules[k] = list(items)
        self.default: Optional[str] = data.get("default")

    @classmethod
    def load(cls, path: Optional[Path]) -> "FakeScenario":
        """Load a scenario JSON file (None gives the empty scenario)."""
        if path is None:
            return cls()
        data = load_json_data(Path(path))
        if not isinstance(data, dict):
            raise L10nError(f"{path}: fake scenario must be a JSON object")
        return cls(data, str(path))


class FakeProvider:
    """Provider protocol implementation that never touches the network."""

    name = "fake"

    def __init__(self, model: str = "fake-model", family: str = "fake", scenario: Optional[FakeScenario] = None,
                 alias: Optional[str] = None) -> None:
        self.model = model
        self.family = family
        self.alias = alias or model
        self.scenario = scenario or FakeScenario()
        self.calls: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    def complete(self, system: str, user: str, *, temperature: float = 0.0,
                 max_tokens: int = 2048, json_mode: bool = False) -> ChatResult:
        """Return a deterministic reply (see module docstring for the lookup order)."""
        h = prompt_hash(system, user)
        _instr, payload = split_envelope(user)
        task = str((payload or {}).get("task", ""))
        self.calls.append({"hash": h, "task": task, "model": self.model})
        sc = self.scenario
        text = sc.responses.get(f"{self.model}:{h}", sc.responses.get(h))
        if text is None:
            err = sc.errors.get(self.model) or sc.errors.get(self.alias)
            if err == "not_found":
                raise ModelNotFoundError(f"fake/{self.model}: model not found (simulated)")
            if err == "server_error":
                raise ProviderError(f"fake/{self.model}: giving up after 5 attempts (simulated HTTP 503)")
            if err == "auth":
                raise ProviderError(f"fake/{self.model}: authentication failed (simulated HTTP 401)")
            text = self._builtin(task, payload or {})
        if text is None:
            text = sc.default if sc.default is not None else "{}"
        return ChatResult(text, estimate_tokens(system + user), estimate_tokens(text), self.model, 0)

    # ------------------------------------------------------------------ #
    def _match(self, rule: Dict[str, Any], text: str = "", key: str = "", tier: str = "") -> bool:
        if "contains" in rule and str(rule["contains"]) not in text:
            return False
        if "key" in rule and str(rule["key"]) != key:
            return False
        if "model" in rule and str(rule["model"]) not in (self.model, self.alias):
            return False
        if "family" in rule and str(rule["family"]) != self.family:
            return False
        if "tier" in rule and str(rule["tier"]) != tier:
            return False
        return True

    def _first(self, kind: str, text: str = "", key: str = "", tier: str = "") -> Optional[Dict[str, Any]]:
        for rule in self.scenario.rules.get(kind, []):
            if self._match(rule, text, key, tier):
                return rule
        return None

    @staticmethod
    def _unmark(text: str) -> str:
        if text.startswith("[") and "] " in text:
            return text.split("] ", 1)[1]
        return text

    def _builtin(self, task: str, p: Dict[str, Any]) -> Optional[str]:
        locale = str(p.get("locale", "xx"))
        dump = lambda obj: json.dumps(obj, ensure_ascii=False)  # noqa: E731
        if task == "pass1":
            return dump({"rows": [{"key": r.get("key"), "target": r.get("target") or f"[{locale}] {r.get('source', '')}"}
                                  for r in p.get("rows", [])]})
        if task == "literal":
            return dump({"rows": [{"key": r.get("key"), "target": f"[{locale} literal] {r.get('source', '')}"} for r in p.get("rows", [])]})
        if task == "roundtrip":
            out = []
            for r in p.get("rows", []):
                tgt = str(r.get("target", ""))
                rule = self._first("roundtrip", tgt, str(r.get("key", "")))
                if rule is not None:
                    back = str(rule.get("back", ""))
                elif tgt.startswith("["):
                    back = self._unmark(tgt)
                else:
                    back = " ".join(reversed(tgt.split()))
                out.append({"key": r.get("key"), "back": back})
            return dump({"rows": out})
        if task == "jury":
            tier = str(p.get("tier", ""))
            votes = []
            for e in p.get("entries", []):
                tgt, key = str(e.get("target", "")), str(e.get("key", ""))
                rule = self._first("scores", tgt, key, tier)
                if rule is not None:
                    score = int(rule.get("score", 5))
                    vote = {"key": key, "score": score, "issue_type": str(rule.get("issue_type", "none" if score == 5 else "other")),
                            "reason": str(rule.get("reason", "" if score == 5 else "scenario rule")), "suggested": str(rule.get("suggested", ""))}
                    if "odd_words" in rule:  # the everyday word check of the juror
                        vote["odd_words"] = list(rule["odd_words"])
                elif LITERAL_MARK in tgt:
                    vote = {"key": key, "score": 2, "issue_type": "translationese", "reason": "word for word calque", "suggested": self._unmark(tgt)}
                else:
                    vote = {"key": key, "score": 5, "issue_type": "none", "reason": "", "suggested": ""}
                votes.append(vote)
            return dump({"votes": votes})
        if task == "pairwise":
            out = []
            for pr in p.get("pairs", []):
                a, b = str(pr.get("a", "")), str(pr.get("b", ""))
                choice = "a"
                rule = None
                for cand in self.scenario.rules.get("pairwise", []):
                    if self._match({k: v for k, v in cand.items() if k != "contains"}) and str(cand.get("contains", "")) and \
                            (str(cand["contains"]) in a or str(cand["contains"]) in b):
                        rule = cand
                        break
                if rule is not None:
                    needle = str(rule["contains"])
                    side_with = "a" if needle in a else "b"
                    choice = side_with if rule.get("pick_containing", True) else ("b" if side_with == "a" else "a")
                elif (LITERAL_MARK in a) != (LITERAL_MARK in b):
                    choice = "b" if LITERAL_MARK in a else "a"
                out.append({"id": pr.get("id"), "choice": choice})
            return dump({"choices": out})
        if task == "deliberate":
            key, tgt = str(p.get("key", "")), str(p.get("target", ""))
            own = p.get("own") or {}
            rule = self._first("deliberate", tgt, key)
            if rule is not None:
                return dump({"score": int(rule.get("score", own.get("score", 3))), "issue_type": str(rule.get("issue_type", own.get("issue_type", "other"))),
                             "reason": str(rule.get("reason", "revised after deliberation")), "suggested": str(rule.get("suggested", own.get("suggested", "")))})
            return dump({"score": int(own.get("score", 3)), "issue_type": str(own.get("issue_type", "other")),
                         "reason": str(own.get("reason", "")) or "keeps the first vote", "suggested": str(own.get("suggested", ""))})
        if task == "pass2":
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
            return dump({"rows": out})
        if task == "pick":
            out = []
            for it in p.get("items", []):
                cands = it.get("candidates", [])
                joined = " ".join(str(c.get("text", "")) for c in cands)
                rule = self._first("picks", joined, str(it.get("key", "")))
                choice = cands[0].get("id") if cands else None
                if rule is not None and "prefer" in rule:
                    hits = [c for c in cands if str(rule["prefer"]) in str(c.get("text", ""))]
                    choice = hits[0].get("id") if hits else choice
                elif rule is not None:
                    choice = rule.get("choice", choice)
                out.append({"key": it.get("key"), "choice": choice})
            return dump({"picks": out})
        if task == "ping":
            return dump({"ok": True, "model": self.model})
        if task == "critique":  # legacy orchestrator_stub format
            entries = p.get("entries", [])
            return dump({"locale": locale, "source_file": p.get("source_file", ""), "entries": [],
                         "summary": {"total": len(entries), "flagged": 0, "critical": 0}})
        return None
