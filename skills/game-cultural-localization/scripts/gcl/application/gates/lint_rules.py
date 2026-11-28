"""Row context extraction and Specification based lint rule scoping."""
from __future__ import annotations

import re
from typing import Any, Dict, Set

from gcl.domain.lint_models import ROW_CONTEXTS, RULE_CONTEXTS, LintOptions, Rule
from gcl.domain.specifications import RuleAppliesSpec

__layer__ = "application"
__pattern__ = "Specification Bridge"
__owns__ = "deriving row context tags and matching Rules via RuleAppliesSpec"

_UI_WORDS = frozenset(("ui", "button", "menu", "label", "tooltip", "hud", "toast", "warning", "tab", "badge", "prompt", "keybind"))
_DIALOG_WORDS = frozenset((
    "dialog", "dialogue", "speech", "letter", "story", "npc", "bark",
    "cutscene", "mail", "news", "dialogue_casual", "dialogue_formal",
))
_FORMAL_WORDS = frozenset(("formal", "dialogue_formal", "official", "news", "announcement", "press", "lore", "codex", "encyclopedia"))
_FORMAL_KEY_RE = re.compile(r"(?i)(?:^|[_.])(?:codex|lore|news)(?:$|[_.])")
_BUTTON_KEY_RE = re.compile(r"(?i)(?:^|[_.])(?:btn|button)(?:$|[_.])")
_CTX_KEYS = ("category", "context", "type", "ui_type", "speaker_or_ui_type", "audience", "tags")


def row_contexts(key: str, meta: Dict[str, Any]) -> Set[str]:
    """Derive row context tags from metadata fields and key conventions."""
    tags: Set[str] = set()
    values = []
    for k in _CTX_KEYS:
        v = meta.get(k)
        if isinstance(v, (list, tuple)):
            values.extend(str(x).lower() for x in v)
        elif v not in (None, ""):
            values.append(str(v).lower())
    for v in values:
        parts = {p.strip() for p in re.split(r"[,;/|\s]+", v) if p.strip()}
        if parts & _UI_WORDS:
            tags.add("ui")
        if parts & _DIALOG_WORDS:
            tags.add("dialog")
        if "button" in parts:
            tags.add("button")
        if "player" in parts:
            tags.add("player")
        if parts & _FORMAL_WORDS:
            tags.add("formal")
    if meta.get("player") in (True, 1, "1", "true", "True", "yes"):
        tags.add("player")
    if _BUTTON_KEY_RE.search(key):
        tags.update({"button", "ui"})
    if _FORMAL_KEY_RE.search(key):
        tags.add("formal")
    return tags


def rule_applies(rule: Rule, contexts: Set[str]) -> bool:
    """Evaluate whether rule applies to row context tags via RuleAppliesSpec."""
    return RuleAppliesSpec(rule.context, rule.skip_contexts).is_satisfied_by(contexts)
