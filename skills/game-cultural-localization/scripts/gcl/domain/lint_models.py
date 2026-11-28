"""Domain value objects and vocabularies for LQA lint rules and options."""

import re
from collections.abc import Sequence
from typing import Any, NamedTuple

__layer__ = "domain"
__pattern__ = "Value Objects"
__owns__ = "Rule, LintOptions and context tag constants shared across infrastructure and application"

RULE_CONTEXTS: tuple[str, ...] = ("any", "ui", "dialog", "player", "button", "formal")
ROW_CONTEXTS: tuple[str, ...] = ("ui", "dialog", "player", "button", "formal")


class Rule(NamedTuple):
    """Compiled locale LQA regex rule."""

    id: str
    severity: str
    regex: re.Pattern[str]
    message: str
    context: str
    skip_variants: tuple[str, ...]
    source: str
    skip_contexts: tuple[str, ...] = ()


class LintOptions(NamedTuple):
    """Options controlling LQA checks per lint run."""

    locale: str
    placeholder_style: str = "auto"
    tag_style: str = "auto"
    placeholder_regex: re.Pattern[str] | None = None
    forbid_chars: str = ""
    forbid_spaced_hyphen: bool = False
    allow_spaced_hyphen_substr: Sequence[str] = ()
    strict_whitespace: bool = False
    glossary: Sequence[Any] = ()
    glossary_severity: str = "WARN"
    check_untranslated: bool = True
