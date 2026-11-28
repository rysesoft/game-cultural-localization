"""Strategy + Registry implementation for engine placeholder extraction and comparison."""

import re
from collections import Counter

from gcl.domain.errors import L10nError
from gcl.domain.models import PlaceholderSet
from gcl.ports.formats import PlaceholderStrategy

__layer__ = "infrastructure"
__pattern__ = "Strategy and Registry"
__owns__ = "pluggable placeholder parsing for unity, unreal, godot, icu, printf and python"

PLACEHOLDER_STYLES: tuple[str, ...] = ("auto", "unity", "unreal", "godot", "icu", "printf", "python")
BACKTICK = "\x60"
PRINTF_PH_RE = re.compile(
    r"%(?:(?P<pos>\d+)\$)?(?:\((?P<name>\w+)\))?[-+#0']*(?:\d+|\*)?(?:\.(?:\d+|\*))?"
    r"(?:hh|h|ll|l|L|q|j|z|t)?(?P<conv>[diouxXeEfFgGaAcspn@])"
)
_PRINTF_ESCAPE_RE = re.compile(r"%%")
_ICU_QUOTED_RE = re.compile(r"'[^']*'")
_IDENT_RE = re.compile(r"^(?:[A-Za-z_][\w.]*|\d+)$")


def _brace_groups(text: str, escape: str) -> list[str]:
    groups: list[str] = []
    depth, start, i, n = 0, -1, 0, len(text)
    while i < n:
        ch = text[i]
        if escape == "double" and depth == 0 and ch in "{}" and i + 1 < n and text[i + 1] == ch:
            i += 2
            continue
        if escape == "backtick" and ch == BACKTICK and i + 1 < n and text[i + 1] in "{}":
            i += 2
            continue
        if ch == "{":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                groups.append(text[start:i])
        i += 1
    return groups


def _slot_id(inner: str) -> str:
    m = re.match(r"\s*([^:,|!\s}]*)", inner)
    return (m.group(1) if m else inner).strip()


def _extract_brace_slots(text: str, escape: str, strip_icu_quotes: bool) -> tuple[tuple[str, ...], tuple[str, ...]]:
    src = _ICU_QUOTED_RE.sub(lambda m: m.group(0) if ("{" not in m.group(0) and "}" not in m.group(0)) else "", text) if strip_icu_quotes else text
    top: list[str] = []
    nested: list[str] = []
    for inner in _brace_groups(src, escape):
        sid = _slot_id(inner)
        if sid == "" and "{" not in inner:
            continue
        if sid:
            top.append(sid)
        for sub in _brace_groups(inner, "none"):
            sub_id = _slot_id(sub)
            if _IDENT_RE.match(sub_id) and "{" not in sub:
                nested.append(sub_id)
                continue
            for deeper in _brace_groups(sub, "none"):
                did = _slot_id(deeper)
                if _IDENT_RE.match(did):
                    nested.append(did)
    return tuple(top), tuple(sorted(set(nested)))


def _extract_printf(text: str) -> tuple[str, ...]:
    return tuple(m.group(0) for m in PRINTF_PH_RE.finditer(_PRINTF_ESCAPE_RE.sub("", text)))


class ConfiguredPlaceholderStrategy:
    """Configurable Strategy driving brace + printf placeholder rules declaratively."""

    def __init__(self, style: str, *, use_brace: bool, use_printf: bool, escape: str = "double", icu_quotes: bool = False) -> None:
        self.style = style
        self._use_brace = use_brace
        self._use_printf = use_printf
        self._escape = escape
        self._icu_quotes = icu_quotes

    def extract(self, text: str) -> PlaceholderSet:
        top, nested = _extract_brace_slots(text, self._escape, self._icu_quotes) if self._use_brace else ((), ())
        printf = _extract_printf(text) if self._use_printf else ()
        return PlaceholderSet(top, nested, printf)


class PlaceholderRegistry:
    """OCP registry allowing custom placeholder styles without touching extract_placeholders."""

    def __init__(self) -> None:
        self._strategies: dict[str, PlaceholderStrategy] = {}

    def register(self, strategy: PlaceholderStrategy) -> None:
        self._strategies[strategy.style] = strategy

    def get(self, style: str) -> PlaceholderStrategy:
        strat = self._strategies.get(style)
        if strat is None:
            names = ", ".join(sorted(self._strategies))
            raise L10nError(f"unknown placeholder style '{style}'; choose from {names}")
        return strat


DEFAULT_PLACEHOLDER_REGISTRY = PlaceholderRegistry()
for _strat in (
    ConfiguredPlaceholderStrategy("auto", use_brace=True, use_printf=True, escape="double"),
    ConfiguredPlaceholderStrategy("unity", use_brace=True, use_printf=False, escape="double"),
    ConfiguredPlaceholderStrategy("unreal", use_brace=True, use_printf=False, escape="backtick"),
    ConfiguredPlaceholderStrategy("godot", use_brace=True, use_printf=True, escape="double"),
    ConfiguredPlaceholderStrategy("icu", use_brace=True, use_printf=False, escape="none", icu_quotes=True),
    ConfiguredPlaceholderStrategy("printf", use_brace=False, use_printf=True),
    ConfiguredPlaceholderStrategy("python", use_brace=True, use_printf=True, escape="double"),
):
    DEFAULT_PLACEHOLDER_REGISTRY.register(_strat)


def extract_placeholders(
    text: str,
    style: str = "auto",
    extra_regex: re.Pattern[str] | None = None,
    registry: PlaceholderRegistry = DEFAULT_PLACEHOLDER_REGISTRY,
) -> PlaceholderSet:
    """Extract placeholders via the registered strategy plus optional project regex."""
    ps = registry.get(style).extract(text)
    if extra_regex is None:
        return ps
    extra = tuple(m.group(0) for m in extra_regex.finditer(text))
    return PlaceholderSet(ps.top + extra, ps.nested, ps.printf)


def _printf_positional(tok: str) -> bool:
    return bool(re.match(r"%\d+\$|%\(\w+\)", tok))


def compare_placeholders(src: PlaceholderSet, dst: PlaceholderSet) -> list[str]:
    """Return human readable mismatch descriptions between source and target placeholders."""
    problems: list[str] = []
    if Counter(src.top) != Counter(dst.top):
        problems.append(f"brace placeholders src={list(src.top)} vs dst={list(dst.top)}")
    if set(src.nested) != set(dst.nested):
        problems.append(f"nested placeholders src={list(src.nested)} vs dst={list(dst.nested)}")
    if src.printf or dst.printf:
        if all(_printf_positional(t) for t in src.printf + dst.printf):
            if Counter(src.printf) != Counter(dst.printf):
                problems.append(f"printf tokens src={list(src.printf)} vs dst={list(dst.printf)}")
        elif list(src.printf) != list(dst.printf):
            problems.append(f"printf tokens (order matters) src={list(src.printf)} vs dst={list(dst.printf)}")
    return problems
