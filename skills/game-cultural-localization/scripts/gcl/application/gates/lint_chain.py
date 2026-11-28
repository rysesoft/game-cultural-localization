"""Chain of Responsibility deterministic LQA lint pipeline."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set

from gcl.domain.lint_models import LintOptions, Rule
from gcl.domain.locales import PLURAL_FORMS
from gcl.domain.models import Finding, Row
from gcl.ports.formats import LintCheck, TokenParityPort

from .lint_rules import row_contexts, rule_applies

__layer__ = "application"
__pattern__ = "Chain of Responsibility"
__owns__ = "composable per row LintCheck handlers preserving deterministic finding order"

_MOJIBAKE_RE = re.compile(r"[ÃÂ][\u0080-\u00ff]|â€[\u0080-\u00ff\x9d\x9c\x9e\x99]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ALPHA_WORD_RE = re.compile(r"[A-Za-z]{3,}")


@dataclass
class LintRowContext:
    """Per row execution context shared across Chain of Responsibility handlers."""

    row: Row
    opt: LintOptions
    rules: Sequence[Rule]
    expected_forms: Optional[int]
    parity: TokenParityPort
    contexts: Set[str]
    ignored: Set[str]
    stop: bool = False


def _ignored_rules(meta: dict) -> Set[str]:
    v = meta.get("lqa_ignore")
    if not v:
        return set()
    if isinstance(v, str):
        return {x.strip() for x in v.split(",") if x.strip()}
    return {str(x).strip() for x in v}


class EmptyTargetCheck:
    """Reject empty targets when source exists or entry is a kv_map, halting row checks."""

    def check_row(self, row: Row, ctx: LintRowContext) -> List[Finding]:
        if row.dst.strip() != "":
            return []
        ctx.stop = True
        if row.src.strip() != "" or row.meta.get("kv_map"):
            return [Finding("ERR", "EMPTY", row.key, "target string is empty", row.dst)]
        return []


class PoMetadataCheck:
    """Flag PO fuzzy markers and incomplete plural form counts."""

    def check_row(self, row: Row, ctx: LintRowContext) -> List[Finding]:
        out: List[Finding] = []
        if row.meta.get("fuzzy"):
            out.append(Finding("WARN", "FUZZY", row.key, "PO entry is marked fuzzy (needs review before shipping)", row.dst))
        exp = ctx.expected_forms
        if exp and row.meta.get("plural_index") == 0 and row.meta.get("plural_nforms", exp) < exp:
            nforms = row.meta.get("plural_nforms")
            out.append(Finding("WARN", "PLURAL_FORMS", row.key, f"only {nforms} plural form(s), {ctx.opt.locale} needs {exp}", row.dst))
        return out


class EncodingCheck:
    """Detect U+FFFD, mojibake sequences and control characters."""

    def check_row(self, row: Row, ctx: LintRowContext) -> List[Finding]:
        out: List[Finding] = []
        if "\ufffd" in row.dst:
            out.append(Finding("ERR", "ENCODING", row.key, "replacement character U+FFFD found (decoding damage)", row.dst))
        if _MOJIBAKE_RE.search(row.dst):
            out.append(Finding("ERR", "ENCODING", row.key, "mojibake sequence (double-encoded UTF-8 such as 'Ã¼' / 'â€™')", row.dst))
        if _CONTROL_RE.search(row.dst):
            out.append(Finding("ERR", "CONTROL_CHAR", row.key, "control character inside the string", row.dst))
        return out


class PunctuationBanCheck:
    """Enforce forbid_chars and forbid_spaced_hyphen project bans."""

    def check_row(self, row: Row, ctx: LintRowContext) -> List[Finding]:
        out: List[Finding] = []
        for ch in ctx.opt.forbid_chars:
            if ch in row.dst:
                out.append(Finding("ERR", "FORBIDDEN_CHAR", row.key, f"forbidden character {ch!r}", row.dst))
        if ctx.opt.forbid_spaced_hyphen and " - " in row.dst and not any(sub in row.dst for sub in ctx.opt.allow_spaced_hyphen_substr):
            out.append(Finding("ERR", "SPACED_HYPHEN", row.key, "' - ' is forbidden by project rules", row.dst))
        return out


class PlaceholderCheck:
    """Validate placeholder parity when source text is present."""

    def check_row(self, row: Row, ctx: LintRowContext) -> List[Finding]:
        if row.src == "":
            return []
        probs = ctx.parity.placeholder_problems(row.src, row.dst, ctx.opt.placeholder_style, ctx.opt.placeholder_regex)
        return [Finding("ERR", "PLACEHOLDER", row.key, p, row.dst) for p in probs]


class RichTagCheck:
    """Validate rich text tag parity and structure when source text is present."""

    def check_row(self, row: Row, ctx: LintRowContext) -> List[Finding]:
        if row.src == "":
            return []
        probs = ctx.parity.tag_problems(row.src, row.dst, ctx.opt.tag_style)
        return [Finding("ERR", "RICH_TAG", row.key, p, row.dst) for p in probs]


class WhitespaceCheck:
    """Verify leading spaces, trailing spaces and trailing newlines when strict_whitespace is enabled."""

    def check_row(self, row: Row, ctx: LintRowContext) -> List[Finding]:
        if row.src == "" or not ctx.opt.strict_whitespace:
            return []
        out: List[Finding] = []
        lead_s = len(row.src) - len(row.src.lstrip(" \t\u00a0"))
        lead_d = len(row.dst) - len(row.dst.lstrip(" \t\u00a0"))
        if lead_s != lead_d:
            out.append(Finding("ERR", "LEADING_SPACE", row.key, f"leading whitespace src={row.src[:lead_s]!r} vs dst={row.dst[:lead_d]!r}", row.dst))
        core_s, core_d = row.src.rstrip("\r\n"), row.dst.rstrip("\r\n")
        trail_s = len(core_s) - len(core_s.rstrip(" \t\u00a0"))
        trail_d = len(core_d) - len(core_d.rstrip(" \t\u00a0"))
        if trail_s != trail_d:
            out.append(Finding("ERR", "TRAILING_SPACE", row.key, f"trailing whitespace src={core_s[len(core_s)-trail_s:]!r} vs dst={core_d[len(core_d)-trail_d:]!r}", row.dst))
        if (len(row.src) - len(core_s)) != (len(row.dst) - len(core_d)):
            out.append(Finding("ERR", "TRAILING_NEWLINE", row.key, "trailing newline parity differs from source", row.dst))
        return out


class UntranslatedCheck:
    """Warn when non English target copies source words unchanged."""

    def check_row(self, row: Row, ctx: LintRowContext) -> List[Finding]:
        if row.src == "" or not ctx.opt.check_untranslated or ctx.opt.locale == "en":
            return []
        if row.src.strip() == row.dst.strip() and _ALPHA_WORD_RE.search(row.src):
            return [Finding("WARN", "UNTRANSLATED", row.key, "target is identical to the source text", row.dst)]
        return []


class GlossaryCheck:
    """Check locked termbase matches when source and glossary are supplied."""

    def check_row(self, row: Row, ctx: LintRowContext) -> List[Finding]:
        if row.src == "" or not ctx.opt.glossary:
            return []
        probs = ctx.parity.glossary_problems(row.src, row.dst, ctx.opt.glossary)
        return [Finding(ctx.opt.glossary_severity, "GLOSSARY", row.key, p, row.dst) for p in probs]


class LocaleRegexCheck:
    """Evaluate compiled locale regex rules scoped to row contexts."""

    def check_row(self, row: Row, ctx: LintRowContext) -> List[Finding]:
        out: List[Finding] = []
        for rule in ctx.rules:
            if rule_applies(rule, ctx.contexts) and rule.id not in ctx.ignored and rule.regex.search(row.dst):
                out.append(Finding(rule.severity, rule.id, row.key, rule.message, row.dst))
        return out


class LintChainRunner:
    """Executes an ordered sequence of LintCheck handlers over table rows."""

    def __init__(self, handlers: Optional[Sequence[LintCheck]] = None) -> None:
        self.handlers: Sequence[LintCheck] = tuple(handlers) if handlers is not None else (
            EmptyTargetCheck(), PoMetadataCheck(), EncodingCheck(), PunctuationBanCheck(),
            PlaceholderCheck(), RichTagCheck(), WhitespaceCheck(), UntranslatedCheck(),
            GlossaryCheck(), LocaleRegexCheck(),
        )

    def lint_rows(self, rows: Sequence[Row], rules: Sequence[Rule], opt: LintOptions, parity: TokenParityPort) -> List[Finding]:
        findings: List[Finding] = []
        expected_forms = PLURAL_FORMS.get(opt.locale)
        for row in rows:
            ctx = LintRowContext(row, opt, rules, expected_forms, parity, row_contexts(row.key, row.meta), _ignored_rules(row.meta))
            for handler in self.handlers:
                findings.extend(handler.check_row(row, ctx))
                if ctx.stop:
                    break
        return findings


def lint_rows(rows: Sequence[Row], rules: Sequence[Rule], opt: LintOptions, parity: TokenParityPort) -> List[Finding]:
    """Run default Chain of Responsibility lint checks over rows."""
    return LintChainRunner().lint_rows(rows, rules, opt, parity)
