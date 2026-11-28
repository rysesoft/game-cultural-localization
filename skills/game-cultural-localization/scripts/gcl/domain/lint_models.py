"""Domain value objects and vocabularies for LQA lint rules and options."""
from __future__ import annotations

import re
from typing import Any, NamedTuple, Optional, Sequence, Tuple

__layer__ = "domain"
__pattern__ = "Value Objects"
__owns__ = "Rule, LintOptions and context tag constants shared across infrastructure and application"

RULE_CONTEXTS: Tuple[str, ...] = ("any", "ui", "dialog", "player", "button", "formal")
ROW_CONTEXTS: Tuple[str, ...] = ("ui", "dialog", "player", "button", "formal")


class Rule(NamedTuple):
    """Compiled locale LQA regex rule."""

    id: str
    severity: str
    regex: "re.Pattern[str]"
    message: str
    context: str
    skip_variants: Tuple[str, ...]
    source: str
    skip_contexts: Tuple[str, ...] = ()


class LintOptions(NamedTuple):
    """Options controlling LQA checks per lint run."""

    locale: str
    placeholder_style: str = "auto"
    tag_style: str = "auto"
    placeholder_regex: Optional["re.Pattern[str]"] = None
    forbid_chars: str = ""
    forbid_spaced_hyphen: bool = False
    allow_spaced_hyphen_substr: Sequence[str] = ()
    strict_whitespace: bool = False
    glossary: Sequence[Any] = ()
    glossary_severity: str = "WARN"
    check_untranslated: bool = True
