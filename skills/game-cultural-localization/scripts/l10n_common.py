#!/usr/bin/env python3
"""Shared, dependency-free helpers for the game-cultural-localization CLI tools.

Python 3.9+ standard library only. Imported by the sibling scripts in this
directory (python prepends a script's own directory to sys.path, so the import
works from any working directory).

Contents
--------
* exit-code contract (EXIT_OK / EXIT_FINDINGS / EXIT_USAGE)
* UTF-8 console setup (ensure_utf8_stdio)
* locale normalisation for the 15 supported locales (normalize_locale)
* placeholder extraction for unity / unreal / godot / icu / printf / python
* rich-text tag extraction for tmp / html / bbcode (+ structure check)
* BOM-tolerant loaders: JSON (list / map), CSV / TSV (delimiter sniffing),
  gettext PO (multi-line, plural, fuzzy, msgctxt), Unity Localization YAML
* project config (l10n.config.json) and glossary CSV loading
* visual-width estimation (East Asian Width aware)
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

__version__ = "2.2.0"

# --------------------------------------------------------------------------- #
# Exit-code contract (shared by every script)
# --------------------------------------------------------------------------- #
EXIT_OK = 0        # clean
EXIT_FINDINGS = 1  # lint findings (ERR, or WARN with --fail-on-warn / HIGH risks / missing glyphs)
EXIT_USAGE = 2     # usage or input error (unknown locale, broken file, missing column, bad font)

SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_RULES_DIR = SCRIPTS_DIR / "rules"
BACKTICK = "\x60"


class L10nError(Exception):
    """A usage / input error that must end the program with EXIT_USAGE (2)."""


def ensure_utf8_stdio() -> None:
    """Force UTF-8 on stdout/stderr (Windows consoles default to cp1252).

    'backslashreplace' keeps the run alive on terminals that cannot render a
    code point while still showing *which* character was involved (\\uXXXX).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass


def read_text_bom(path: Path) -> str:
    """Read a UTF-8 text file tolerating a BOM; raise L10nError on IO/decode problems."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise L10nError(f"input file not found: {path}")
    except IsADirectoryError:
        raise L10nError(f"input path is a directory, expected a file: {path}")
    except PermissionError:
        raise L10nError(f"input file is not readable: {path}")
    except UnicodeDecodeError as exc:
        raise L10nError(f"{path} is not valid UTF-8 ({exc.reason} at byte {exc.start}); re-save as UTF-8")


# --------------------------------------------------------------------------- #
# Locales
# --------------------------------------------------------------------------- #
CANONICAL_LOCALES: Tuple[str, ...] = (
    "en", "tr-TR", "de-DE", "fr", "es-ES", "it-IT", "pt-BR", "pt-PT",
    "pl-PL", "lt-LT", "ru-RU", "ja-JP", "ko-KR", "zh-CN", "zh-Hant",
)

# lower-case, '-' separated alias -> (canonical, variant)
_LOCALE_ALIASES: Dict[str, Tuple[str, Optional[str]]] = {
    "en": ("en", None), "en-us": ("en", None), "en-gb": ("en", None), "en-au": ("en", None), "en-ca": ("en", None),
    "tr": ("tr-TR", None), "tr-tr": ("tr-TR", None),
    "de": ("de-DE", None), "de-de": ("de-DE", None), "de-at": ("de-DE", "at"), "de-ch": ("de-DE", "ch"),
    "fr": ("fr", None), "fr-fr": ("fr", None), "fr-ca": ("fr", "ca"), "fr-be": ("fr", None), "fr-ch": ("fr", None),
    "es": ("es-ES", None), "es-es": ("es-ES", None),
    "it": ("it-IT", None), "it-it": ("it-IT", None),
    "pt-br": ("pt-BR", None), "pt-pt": ("pt-PT", None),
    "pl": ("pl-PL", None), "pl-pl": ("pl-PL", None),
    "lt": ("lt-LT", None), "lt-lt": ("lt-LT", None),
    "ru": ("ru-RU", None), "ru-ru": ("ru-RU", None),
    "ja": ("ja-JP", None), "ja-jp": ("ja-JP", None), "jp": ("ja-JP", None),
    "ko": ("ko-KR", None), "ko-kr": ("ko-KR", None), "kr": ("ko-KR", None),
    "zh": ("zh-CN", None), "zh-cn": ("zh-CN", None), "zh-hans": ("zh-CN", None), "zh-sg": ("zh-CN", None),
    "zh-hans-cn": ("zh-CN", None), "chs": ("zh-CN", None),
    "zh-hant": ("zh-Hant", None), "zh-tw": ("zh-Hant", None), "zh-hant-tw": ("zh-Hant", None), "cht": ("zh-Hant", None),
    "zh-hk": ("zh-Hant", "hk"), "zh-mo": ("zh-Hant", "hk"), "zh-hant-hk": ("zh-Hant", "hk"),
}
_AMBIGUOUS_LOCALES = {"pt": "pt-BR or pt-PT", "es-mx": "es-ES (LatAm Spanish is not covered)", "es-419": "es-ES"}

# gettext nplurals expected per locale (used for PO plural-form completeness)
PLURAL_FORMS: Dict[str, int] = {
    "en": 2, "tr-TR": 2, "de-DE": 2, "fr": 2, "es-ES": 2, "it-IT": 2, "pt-BR": 2, "pt-PT": 2,
    "pl-PL": 3, "lt-LT": 3, "ru-RU": 3, "ja-JP": 1, "ko-KR": 1, "zh-CN": 1, "zh-Hant": 1,
}


def normalize_locale(raw: str) -> Tuple[str, Optional[str]]:
    """Map a user-supplied locale code to (canonical, variant).

    Accepts 'de', 'de_DE', 'DE-de', 'pt_BR', 'zh-TW', 'zh-HK' (-> zh-Hant, variant 'hk') ...
    Raises L10nError listing the supported locales for anything unknown.
    """
    key = (raw or "").strip().replace("_", "-").lower()
    if not key:
        raise L10nError("locale is empty; supported locales: " + ", ".join(CANONICAL_LOCALES))
    if key in _LOCALE_ALIASES:
        return _LOCALE_ALIASES[key]
    if key in _AMBIGUOUS_LOCALES:
        raise L10nError(f"locale '{raw}' is ambiguous; use {_AMBIGUOUS_LOCALES[key]}")
    base = key.split("-")[0]
    hint = ""
    for canon in CANONICAL_LOCALES:
        if canon.lower().split("-")[0] == base:
            hint = f" (did you mean '{canon}'?)"
            break
    raise L10nError(f"unknown locale '{raw}'{hint}; supported: " + ", ".join(CANONICAL_LOCALES))


# --------------------------------------------------------------------------- #
# Placeholders
# --------------------------------------------------------------------------- #
PLACEHOLDER_STYLES: Tuple[str, ...] = ("auto", "unity", "unreal", "godot", "icu", "printf", "python")

# printf family: %s %d %5.2f %-10s %1$s %ld %lu %@ (ObjC) %(name)s (Python). '%%' is removed beforehand.
# NOTE: no ' ' in the flag class, so '100% fertig' / '50% de' are NOT tokens (audit S-04).
PRINTF_PH_RE = re.compile(
    r"%(?:(?P<pos>\d+)\$)?(?:\((?P<name>\w+)\))?[-+#0']*(?:\d+|\*)?(?:\.(?:\d+|\*))?"
    r"(?:hh|h|ll|l|L|q|j|z|t)?(?P<conv>[diouxXeEfFgGaAcspn@])"
)
_PRINTF_ESCAPE_RE = re.compile(r"%%")
_ICU_QUOTED_RE = re.compile(r"'[^']*'")
_IDENT_RE = re.compile(r"^(?:[A-Za-z_][\w.]*|\d+)$")


class PlaceholderSet(NamedTuple):
    """Placeholders found in one string.

    top:    multiset of top-level slot identifiers ('0', 'name', 'count')
    nested: set of slot identifiers inside ICU / Smart-String sub-messages
    printf: ordered printf tokens ('%d', '%1$s', '%(name)s')
    """
    top: Tuple[str, ...]
    nested: Tuple[str, ...]
    printf: Tuple[str, ...]


def _brace_groups(text: str, escape: str) -> List[str]:
    """Return the inner text of every balanced top-level {...} group.

    escape: 'double' treats '{{' / '}}' as literal braces (Unity Smart Strings,
    Python str.format); 'backtick' treats a backtick-prefixed brace as literal
    (Unreal FText); 'none' disables escapes (ICU quoting is handled by caller).
    """
    groups: List[str] = []
    depth = 0
    start = -1
    i = 0
    n = len(text)
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
    """'count, plural, ...' -> 'count'; '0:plural:a|b' -> '0'; 'name:>10' -> 'name'; '0,-10' -> '0'."""
    m = re.match(r"\s*([^:,|!\s}]*)", inner)
    return (m.group(1) if m else inner).strip()


def extract_placeholders(text: str, style: str = "auto", extra_regex: Optional[re.Pattern] = None) -> PlaceholderSet:
    """Extract placeholders according to a placeholder style (see PLACEHOLDER_STYLES)."""
    if style not in PLACEHOLDER_STYLES:
        raise L10nError(f"unknown placeholder style '{style}'; choose from {', '.join(PLACEHOLDER_STYLES)}")
    top: List[str] = []
    nested: List[str] = []
    printf: List[str] = []
    use_brace = style != "printf"
    use_printf = style in ("auto", "godot", "printf", "python")
    if use_brace:
        src = text
        escape = "double"
        if style == "unreal":
            escape = "backtick"
        elif style == "icu":
            escape = "none"
            src = _ICU_QUOTED_RE.sub(lambda m: m.group(0) if ("{" not in m.group(0) and "}" not in m.group(0)) else "", src)
        for inner in _brace_groups(src, escape):
            sid = _slot_id(inner)
            if sid == "" and "{" not in inner:
                continue  # '{}' or '{ }' is not a slot
            if sid:
                top.append(sid)
            # Groups inside a slot are either placeholders ({place}) or ICU / Smart-String
            # sub-messages ("# items from {place}"); only identifier-like ids count as slots.
            for sub in _brace_groups(inner, "none"):
                sub_id = _slot_id(sub)
                if _IDENT_RE.match(sub_id) and "{" not in sub:
                    nested.append(sub_id)
                    continue
                for deeper in _brace_groups(sub, "none"):
                    did = _slot_id(deeper)
                    if _IDENT_RE.match(did):
                        nested.append(did)
    if use_printf:
        for m in PRINTF_PH_RE.finditer(_PRINTF_ESCAPE_RE.sub("", text)):
            printf.append(m.group(0))
    if extra_regex is not None:
        for m in extra_regex.finditer(text):
            top.append(m.group(0))
    return PlaceholderSet(tuple(top), tuple(sorted(set(nested))), tuple(printf))


def _printf_positional(tok: str) -> bool:
    return bool(re.match(r"%\d+\$|%\(\w+\)", tok))


def compare_placeholders(src: PlaceholderSet, dst: PlaceholderSet) -> List[str]:
    """Return a list of human-readable mismatch descriptions (empty = parity OK)."""
    problems: List[str] = []
    if Counter(src.top) != Counter(dst.top):
        problems.append(f"brace placeholders src={list(src.top)} vs dst={list(dst.top)}")
    if set(src.nested) != set(dst.nested):
        problems.append(f"nested placeholders src={list(src.nested)} vs dst={list(dst.nested)}")
    if src.printf or dst.printf:
        all_pos = all(_printf_positional(t) for t in src.printf + dst.printf)
        if all_pos:
            if Counter(src.printf) != Counter(dst.printf):
                problems.append(f"printf tokens src={list(src.printf)} vs dst={list(dst.printf)}")
        elif list(src.printf) != list(dst.printf):
            problems.append(f"printf tokens (order matters) src={list(src.printf)} vs dst={list(dst.printf)}")
    return problems


# --------------------------------------------------------------------------- #
# Rich-text tags
# --------------------------------------------------------------------------- #
TAG_STYLES: Tuple[str, ...] = ("auto", "tmp", "html", "bbcode")

TMP_TAGS = frozenset("""
align allcaps alpha b br color cspace font font-weight gradient i indent line-height line-indent link
lowercase margin mark mspace nobr noparse page pos rotate s size smallcaps space sprite strikethrough
style sub sup u uppercase voffset width
""".split())
HTML_EXTRA_TAGS = frozenset("a p em strong span div img hr ul ol li table tr td th h1 h2 h3 small big tt code pre".split())
BBCODE_TAGS = frozenset("""
b i u s color url img font size center right left fill indent code table cell p br wave tornado shake fade
rainbow outline_size outline_color bgcolor fgcolor lb rb ul ol hint dropcap pulse char opacity quote list
""".split())
VOID_TAGS = frozenset("br sprite space pos page img hr lb rb char input".split())

ANGLE_TAG_RE = re.compile(r"<(?P<close>/?)(?P<name>[A-Za-z][\w-]*)(?P<attr>(?:\s*=\s*[^<>]*)|(?:\s+[^<>]*))?\s*(?P<self>/?)>")
HEX_COLOR_TAG_RE = re.compile(r"<(?P<hex>#[0-9A-Fa-f]{3,8})>")
BB_TAG_RE = re.compile(r"\[(?P<close>/?)(?P<name>[A-Za-z][\w-]*)(?P<attr>=[^\]]*)?\]")


class Tag(NamedTuple):
    name: str      # lower-case tag name ('color' for '<#ff0000>')
    closing: bool
    norm: str      # normalised token used for parity ('<color=#ff0000>')
    raw: str


# TextMeshPro named colours -> hex, so '<color=red>' and '<color=#ff0000>' count as the same tag.
TMP_COLOR_NAMES = {
    "black": "#000000", "blue": "#0000ff", "green": "#008000", "orange": "#ffa500", "purple": "#800080",
    "red": "#ff0000", "white": "#ffffff", "yellow": "#ffff00", "lightblue": "#add8e6", "aqua": "#00ffff",
    "cyan": "#00ffff", "darkblue": "#00008b", "fuchsia": "#ff00ff", "magenta": "#ff00ff", "brown": "#a52a2a",
    "grey": "#808080", "gray": "#808080", "lime": "#00ff00", "maroon": "#800000", "navy": "#000080",
    "olive": "#808000", "silver": "#c0c0c0", "teal": "#008080",
}
_COLOR_VALUE_RE = re.compile(r"^(<(?:color|mark)=)([^>]+)(>)$")


def norm_tag(tag: str) -> str:
    """Canonicalise a tag token: drop whitespace and quotes, lower-case, map colour names to hex."""
    out = re.sub(r"[\s\"']+", "", tag).lower()
    m = _COLOR_VALUE_RE.match(out)
    if m:
        val = m.group(2)
        val = TMP_COLOR_NAMES.get(val, val)
        if re.fullmatch(r"#[0-9a-f]{8}", val) and val.endswith("ff"):
            val = val[:7]
        elif re.fullmatch(r"#[0-9a-f]{3}", val):
            val = "#" + "".join(c * 2 for c in val[1:])
        out = m.group(1) + val + m.group(3)
    return out


def extract_tags(text: str, style: str = "auto") -> List[Tag]:
    """Tokenise rich-text tags in order of appearance (see TAG_STYLES)."""
    if style not in TAG_STYLES:
        raise L10nError(f"unknown tag style '{style}'; choose from {', '.join(TAG_STYLES)}")
    found: List[Tuple[int, Tag]] = []
    if style in ("auto", "tmp", "html"):
        for m in ANGLE_TAG_RE.finditer(text):
            name = m.group("name").lower()
            if style == "tmp" and name not in TMP_TAGS:
                continue
            if style == "html" and name not in TMP_TAGS | HTML_EXTRA_TAGS:
                continue
            found.append((m.start(), Tag(name, m.group("close") == "/", norm_tag(m.group(0)), m.group(0))))
        for m in HEX_COLOR_TAG_RE.finditer(text):
            found.append((m.start(), Tag("color", False, norm_tag("<color=" + m.group("hex") + ">"), m.group(0))))
    if style in ("auto", "bbcode"):
        for m in BB_TAG_RE.finditer(text):
            name = m.group("name").lower()
            if name not in BBCODE_TAGS:
                continue
            found.append((m.start(), Tag(name, m.group("close") == "/", norm_tag(m.group(0)), m.group(0))))
    found.sort(key=lambda t: t[0])
    return [t for _pos, t in found]


def strip_tags(text: str, style: str = "auto") -> str:
    """Remove rich-text tags (for width / glyph scans)."""
    out = text
    if style in ("auto", "tmp", "html"):
        out = ANGLE_TAG_RE.sub(lambda m: "" if (style != "tmp" or m.group("name").lower() in TMP_TAGS) else m.group(0), out)
        out = HEX_COLOR_TAG_RE.sub("", out)
    if style in ("auto", "bbcode"):
        out = BB_TAG_RE.sub(lambda m: "" if m.group("name").lower() in BBCODE_TAGS else m.group(0), out)
    return out


def tag_structure_error(tags: Sequence[Tag]) -> Optional[str]:
    """Check open/close nesting; return a description of the first problem or None."""
    stack: List[Tag] = []
    for t in tags:
        if t.raw.rstrip(">]").endswith("/") or t.name in VOID_TAGS:
            continue
        if not t.closing:
            stack.append(t)
        else:
            if not stack:
                return f"closing {t.raw} without an open tag"
            if stack[-1].name != t.name:
                return f"{t.raw} closes {stack[-1].raw} (wrong order / interleaved)"
            stack.pop()
    if stack:
        return f"unclosed tag {stack[-1].raw}"
    return None


def compare_tags(src_tags: Sequence[Tag], dst_tags: Sequence[Tag]) -> List[str]:
    """Return parity problems between two tag sequences (multiset + structure)."""
    problems: List[str] = []
    sc = Counter(t.norm for t in src_tags)
    dc = Counter(t.norm for t in dst_tags)
    if sc != dc:
        problems.append(f"rich-text tags src={dict(sc)} vs dst={dict(dc)}")
    src_err = tag_structure_error(src_tags)
    dst_err = tag_structure_error(dst_tags)
    if dst_err and not src_err:
        problems.append(f"rich-text tag structure: {dst_err}")
    return problems


# --------------------------------------------------------------------------- #
# Visual width
# --------------------------------------------------------------------------- #
_ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x034F, 0x061C, 0x180E}


def char_width(ch: str, cell: float = 2.0, ambiguous_wide: bool = False) -> float:
    """Width of one character in Latin-cell units (0 for combining / zero-width)."""
    cp = ord(ch)
    if cp in _ZERO_WIDTH or unicodedata.combining(ch) or (0xFE00 <= cp <= 0xFE0F) or (0xE0100 <= cp <= 0xE01EF):
        return 0.0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):
        return cell
    if eaw == "A" and ambiguous_wide:
        return cell
    return 1.0


def visual_width(text: str, cell: float = 2.0, ambiguous_wide: bool = False, tag_style: str = "auto") -> float:
    """Approximate rendered width of the widest line (tags stripped, NFC, CJK = 'cell' units)."""
    clean = unicodedata.normalize("NFC", strip_tags(text, tag_style)).replace("\r\n", "\n")
    best = 0.0
    for line in clean.split("\n"):
        w = sum(char_width(ch, cell, ambiguous_wide) for ch in line)
        if w > best:
            best = w
    return best


def line_count(text: str) -> int:
    """Number of lines in a string (0 for empty)."""
    return text.replace("\r\n", "\n").count("\n") + 1 if text else 0


# --------------------------------------------------------------------------- #
# Gettext PO
# --------------------------------------------------------------------------- #
_PO_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def _po_unescape(s: str) -> str:
    def repl(m: re.Match) -> str:
        c = m.group(1)
        if c in _PO_ESCAPES:
            return _PO_ESCAPES[c]
        if c.startswith("u"):
            return chr(int(c[1:], 16))
        if c[0] in "01234567":
            return chr(int(c, 8))
        return c
    return re.sub(r"\\(u[0-9A-Fa-f]{4}|[0-7]{1,3}|.)", repl, s)


def _po_quoted(line: str, prefix_re: str) -> str:
    m = re.match(prefix_re + r'\s*"((?:[^"\\]|\\.)*)"', line)
    return m.group(1) if m else ""


class Row(NamedTuple):
    """One localisable unit: key, source text ('' when unknown), target text, extra metadata."""
    key: str
    src: str
    dst: str
    meta: Dict[str, Any]


def parse_po(raw: str) -> List[Row]:
    """Parse gettext PO text into rows (multi-line strings, plurals, fuzzy, msgctxt, obsolete '#~' skipped).

    Keys: msgid, 'msgctxt|msgid' when a context exists, and '...|[n]' per plural form.
    meta: msgctxt, fuzzy, msgid, plural_index, plural_nforms, msgid_plural.
    """
    rows: List[Row] = []
    cur: Optional[Dict[str, Any]] = None

    def finalize() -> None:
        nonlocal cur
        if cur is None:
            return
        entry = cur
        cur = None
        msgid, plural, msgstr = entry["msgid"], entry["plural"], entry["msgstr"]
        if msgid == "" and plural is None and entry["ctxt"] is None:
            return  # header
        base_key = f"{entry['ctxt']}|{msgid}" if entry["ctxt"] is not None else msgid
        meta_common = {"msgctxt": entry["ctxt"], "fuzzy": entry["fuzzy"], "msgid": msgid}
        if plural is None:
            rows.append(Row(base_key, msgid, msgstr.get(0, ""), dict(meta_common)))
        else:
            forms = sorted(msgstr) or [0]
            for idx in forms:
                meta = dict(meta_common)
                meta.update({"plural_index": idx, "plural_nforms": len(forms), "msgid_plural": plural})
                rows.append(Row(f"{base_key}|[{idx}]", msgid if idx == 0 else plural, msgstr.get(idx, ""), meta))

    pending_flags: List[str] = []
    pending_ctxt: Optional[str] = None
    state: Any = None
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("#~"):
            finalize()
            state = None
            continue
        if stripped.startswith("#,"):
            pending_flags.extend(f.strip() for f in stripped[2:].split(","))
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("msgctxt "):
            finalize()
            pending_ctxt = _po_unescape(_po_quoted(stripped, r"msgctxt"))
            state = "ctxt"
            continue
        if stripped.startswith("msgid_plural "):
            if cur is None:
                cur = {"msgid": "", "plural": None, "msgstr": {}, "ctxt": pending_ctxt, "fuzzy": False}
            cur["plural"] = _po_unescape(_po_quoted(stripped, r"msgid_plural"))
            state = "plural"
            continue
        if stripped.startswith("msgid "):
            finalize()
            cur = {
                "msgid": _po_unescape(_po_quoted(stripped, r"msgid")), "plural": None, "msgstr": {},
                "ctxt": pending_ctxt, "fuzzy": "fuzzy" in pending_flags,
            }
            pending_flags = []
            pending_ctxt = None
            state = "msgid"
            continue
        if stripped.startswith("msgstr"):
            if cur is None:
                cur = {"msgid": "", "plural": None, "msgstr": {}, "ctxt": pending_ctxt, "fuzzy": False}
            m = re.match(r"msgstr(?:\[(\d+)\])?", stripped)
            idx = int(m.group(1)) if (m and m.group(1) is not None) else 0
            cur["msgstr"][idx] = _po_unescape(_po_quoted(stripped, r"msgstr(?:\[\d+\])?"))
            state = ("msgstr", idx)
            continue
        if stripped.startswith('"'):
            frag = _po_unescape(_po_quoted(stripped, r""))
            if state == "ctxt":
                pending_ctxt = (pending_ctxt or "") + frag
            elif cur is None:
                continue
            elif state == "msgid":
                cur["msgid"] += frag
            elif state == "plural":
                cur["plural"] = (cur["plural"] or "") + frag
            elif isinstance(state, tuple):
                cur["msgstr"][state[1]] = cur["msgstr"].get(state[1], "") + frag
            continue
    finalize()
    return rows


# --------------------------------------------------------------------------- #
# Unity Localization YAML (.asset) string tables
# --------------------------------------------------------------------------- #
_YAML_SCALAR_RE = re.compile(r"^(\s*)(?:- )?(m_Localized|m_Key|m_Id|m_Code|m_Name):\s*(.*)$")
_YAML_DQ_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "0": "\0", "/": "/"}


def _quote_end(text: str, quote: str) -> int:
    """Index of the quote that closes a quoted YAML scalar (text starts after the opening quote), -1 when open."""
    i = 0
    while i < len(text):
        c = text[i]
        if quote == '"' and c == "\\":
            i += 2
            continue
        if c == quote:
            if quote == "'" and text[i + 1:i + 2] == "'":
                i += 2
                continue
            return i
        i += 1
    return -1


def _fold_flow(lines: List[str], double: bool) -> str:
    """YAML line folding of a multi line flow scalar. One line break is a space, every empty line is a newline."""
    out = lines[0].rstrip(" \t")
    empties = 0
    for ln in lines[1:]:
        s = ln.strip(" \t")
        if s == "":
            empties += 1
            continue
        tail = len(out) - len(out.rstrip("\\"))
        if double and tail % 2 == 1 and not empties:  # an escaped line break joins without a space
            out = out[:-1] + s
        else:
            out += ("\n" * empties if empties else " ") + s
        empties = 0
    return out + "\n" * empties


def _yaml_scalar(value: str, following: List[str], indent: int, content_indent: Optional[int] = None) -> Tuple[str, int]:
    """Decode a YAML scalar (plain, 'single', "double", | or > block), also one that spans several lines.

    Returns (text, lines consumed). Unity writes long texts as folded quoted or plain scalars over
    several lines, an empty line inside them is a paragraph break that must survive.
    """
    v = value.strip()
    if v[:1] in ("'", '"'):
        q = v[0]
        body = [value.lstrip()[1:]]
        used = 0
        while _quote_end("\n".join(body), q) < 0 and used < len(following):
            body.append(following[used])
            used += 1
        if used:
            joined = "\n".join(body)
            end = _quote_end(joined, q)
            inner = _fold_flow((joined[:end] if end >= 0 else joined).split("\n"), q == '"')
            if q == "'":
                return inner.replace("''", "'"), used
            return re.sub(
                r"\\(u[0-9A-Fa-f]{4}|x[0-9A-Fa-f]{2}|.)",
                lambda m: _YAML_DQ_ESCAPES.get(m.group(1), m.group(1)) if len(m.group(1)) == 1 else chr(int(m.group(1)[1:], 16)),
                inner,
            ), used
    if v in ("|", "|-", "|+", ">", ">-", ">+"):
        block: List[str] = []
        used = 0
        for ln in following:
            if ln.strip() == "" or (len(ln) - len(ln.lstrip(" "))) > indent:
                block.append(ln)
                used += 1
            else:
                break
        non_empty = [b for b in block if b.strip()]
        base = min((len(b) - len(b.lstrip(" "))) for b in non_empty) if non_empty else 0
        lines = [b[base:] if b.strip() else "" for b in block]
        while lines and lines[-1] == "":
            lines.pop()
        text = "\n".join(lines) if v.startswith("|") else " ".join(l for l in lines if l)
        if not v.endswith("-"):
            text += "\n"
        return text, used
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        inner = v[1:-1]
        return re.sub(
            r"\\(u[0-9A-Fa-f]{4}|x[0-9A-Fa-f]{2}|.)",
            lambda m: _YAML_DQ_ESCAPES.get(m.group(1), m.group(1)) if len(m.group(1)) == 1 else chr(int(m.group(1)[1:], 16)),
            inner,
        ), 0
    if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
        return v[1:-1].replace("''", "'"), 0
    if v and content_indent is not None:  # a plain scalar continues on lines indented deeper than its key
        more: List[str] = []
        for ln in following:
            if ln.strip() == "" or (len(ln) - len(ln.lstrip(" "))) > content_indent:
                more.append(ln)
            else:
                break
        while more and more[-1].strip() == "":
            more.pop()
        if more:
            return _fold_flow([v] + more, False), len(more)
    return v, 0


def parse_unity_yaml(text: str) -> Dict[str, Any]:
    """Extract Unity Localization data from a StringTable / SharedTableData .asset.

    Returns {'entries': [{'id': str|None, 'key': str|None, 'text': str|None}], 'locale': str|None,
             'name': str|None, 'kind': 'string_table'|'shared_table'|'unknown'}.
    """
    lines = text.splitlines()
    entries: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    locale_code: Optional[str] = None
    name: Optional[str] = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = _YAML_SCALAR_RE.match(ln)
        if not m:
            i += 1
            continue
        indent, field, value = len(m.group(1)), m.group(2), m.group(3)
        is_item = ln.lstrip().startswith("- ")
        scalar, used = _yaml_scalar(value, lines[i + 1:], indent, indent + 2 if is_item else indent)
        if field in ("m_Id", "m_Key", "m_Localized"):
            attr = {"m_Id": "id", "m_Key": "key", "m_Localized": "text"}[field]
            if is_item or cur is None or cur.get(attr) is not None:
                cur = {"id": None, "key": None, "text": None}
                entries.append(cur)
            cur[attr] = scalar
        elif field == "m_Code":
            locale_code = locale_code or scalar
        elif field == "m_Name":
            name = name or scalar
        i += 1 + used
    kind = "unknown"
    if any(e["text"] is not None for e in entries):
        kind = "string_table"
    elif any(e["key"] is not None for e in entries):
        kind = "shared_table"
    return {"entries": entries, "locale": locale_code, "name": name, "kind": kind}


# --------------------------------------------------------------------------- #
# Unified table loaders
# --------------------------------------------------------------------------- #
SUPPORTED_INPUT_SUFFIXES = (".json", ".csv", ".tsv", ".po", ".asset", ".yaml", ".yml")


def _as_str(v: Any) -> str:
    return "" if v is None else str(v)


def sniff_delimiter(sample: str, suffix: str) -> str:
    """Pick the CSV delimiter: tab for .tsv, else the most frequent of ',' ';' tab '|' in the header line."""
    if suffix == ".tsv":
        return "\t"
    header = sample.splitlines()[0] if sample else ""
    counts = {d: header.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


def _check_columns(available: Iterable[str], required: Dict[str, str], path: Path) -> None:
    avail = set(available)
    missing = [f"{role} column '{name}'" for role, name in required.items() if name not in avail]
    if missing:
        raise L10nError(
            f"{path}: missing " + ", ".join(missing) + f"; available columns: {sorted(avail)}"
            " (use --src-field/--dst-field/--key-field or --target-only)"
        )


def load_json_data(path: Path) -> Any:
    """Load JSON tolerating a BOM; clear L10nError for empty / invalid files."""
    raw = read_text_bom(path)
    if raw.strip() == "":
        raise L10nError(f"{path}: file is empty")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise L10nError(f"{path}: invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}")


def load_table(
    path: Path,
    src_field: str = "en",
    dst_field: str = "dst",
    key_field: str = "key",
    *,
    target_only: bool = False,
    delimiter: Optional[str] = None,
    src_input: Optional[Path] = None,
    shared_table: Optional[Path] = None,
) -> List[Row]:
    """Load rows from JSON (list / map), CSV / TSV, PO, or Unity Localization YAML.

    Validates that the requested columns exist (CSV / JSON objects) unless
    target_only is set, in which case only the target column is required.
    A JSON object of plain strings ({key: "text"}) is always target-only.
    """
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_INPUT_SUFFIXES:
        raise L10nError(f"{path}: unsupported input format '{suffix}'; supported: {', '.join(SUPPORTED_INPUT_SUFFIXES)}")
    rows: List[Row] = []
    req = {"target": dst_field} if target_only else {"source": src_field, "target": dst_field}
    if suffix == ".json":
        data = load_json_data(path)
        if isinstance(data, list):
            keys: set = set()
            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    raise L10nError(f"{path}: item #{idx} is {type(item).__name__}, expected an object with '{key_field}'/'{dst_field}' fields")
                keys.update(item.keys())
            if data:
                _check_columns(keys, req, path)
            for idx, item in enumerate(data):
                k = _as_str(item.get(key_field) or item.get("id") or f"row_{idx}")
                table = _as_str(item.get("table"))
                label = f"{table}:{k}" if table else k
                rows.append(Row(label, "" if target_only else _as_str(item.get(src_field)), _as_str(item.get(dst_field)), dict(item)))
        elif isinstance(data, dict):
            dict_values = [v for v in data.values() if isinstance(v, dict)]
            if dict_values:
                keys = set()
                for v in dict_values:
                    keys.update(v.keys())
                _check_columns(keys, req, path)
            for k, v in data.items():
                if isinstance(v, dict):
                    rows.append(Row(str(k), "" if target_only else _as_str(v.get(src_field)), _as_str(v.get(dst_field)), dict(v)))
                elif isinstance(v, (str, int, float)) or v is None:
                    rows.append(Row(str(k), "", _as_str(v), {"kv_map": True}))
                else:
                    raise L10nError(f"{path}: value of '{k}' is {type(v).__name__}; expected string or object")
        else:
            raise L10nError(f"{path}: top-level JSON must be a list or an object, got {type(data).__name__}")
    elif suffix in (".csv", ".tsv"):
        raw = read_text_bom(path)
        if raw.strip() == "":
            raise L10nError(f"{path}: file is empty")
        delim = delimiter or sniff_delimiter(raw, suffix)
        reader = csv.DictReader(raw.splitlines(keepends=True), delimiter=delim)
        fieldnames = [f.strip() for f in (reader.fieldnames or [])]
        reader.fieldnames = fieldnames
        _check_columns(fieldnames, req, path)
        for idx, row in enumerate(reader):
            k = _as_str(row.get(key_field)) or f"row_{idx}"
            rows.append(Row(k, "" if target_only else _as_str(row.get(src_field)), _as_str(row.get(dst_field)), dict(row)))
    elif suffix == ".po":
        rows = parse_po(read_text_bom(path))
        if target_only:
            rows = [Row(r.key, "", r.dst, r.meta) for r in rows]
    else:  # Unity YAML
        rows = _load_unity_rows(path, src_input, shared_table)
    return rows


def _load_unity_rows(path: Path, src_input: Optional[Path], shared_table: Optional[Path]) -> List[Row]:
    data = parse_unity_yaml(read_text_bom(path))
    if data["kind"] != "string_table":
        raise L10nError(f"{path}: no 'm_Localized' entries found; expected a Unity Localization StringTable .asset")
    key_names: Dict[str, str] = {}
    if shared_table is not None:
        shared = parse_unity_yaml(read_text_bom(shared_table))
        for e in shared["entries"]:
            if e["id"] is not None and e["key"] is not None:
                key_names[e["id"]] = e["key"]
    src_texts: Dict[str, str] = {}
    if src_input is not None:
        src_data = parse_unity_yaml(read_text_bom(src_input))
        if src_data["kind"] != "string_table":
            raise L10nError(f"{src_input}: no 'm_Localized' entries found in --src-input table")
        for e in src_data["entries"]:
            if e["id"] is not None:
                src_texts[e["id"]] = e["text"] or ""
    rows: List[Row] = []
    for idx, e in enumerate(data["entries"]):
        if e["text"] is None:
            continue
        eid = e["id"] or f"row_{idx}"
        key = key_names.get(eid, eid)
        rows.append(Row(key, src_texts.get(eid, ""), e["text"], {"unity_id": eid, "locale": data["locale"]}))
    return rows


def load_pairs(input_path: Path, src_field: str = "en", dst_field: str = "dst", key_field: str = "key", **kw: Any) -> List[Row]:
    """Backward-compatible alias of load_table()."""
    return load_table(input_path, src_field, dst_field, key_field, **kw)


def load_target_rows(input_path: Path, dst_field: str = "dst", key_field: str = "key") -> List[Tuple[str, str]]:
    """Load (key, target_text) rows from any supported table or, for other suffixes, a plain text file."""
    if input_path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES:
        return [(r.key, r.dst) for r in load_table(input_path, "en", dst_field, key_field, target_only=True)]
    return [(input_path.name, read_text_bom(input_path))]


# --------------------------------------------------------------------------- #
# Project config (l10n.config.json) and glossary
# --------------------------------------------------------------------------- #
CONFIG_KEYS: Dict[str, Any] = {
    "locales": list, "src_field": str, "dst_field": str, "key_field": str,
    "placeholder_style": str, "tag_style": str, "placeholder_regex": str,
    "rules_dir": str, "glossary": str, "glossary_severity": str,
    "max_width": (int, float, dict), "expansion": dict, "cjk_cell_width": (int, float),
    "fail_on_warn": bool, "variant": str, "delimiter": str, "ambiguous_wide": bool,
    "forbid_chars": str, "forbid_spaced_hyphen": bool, "strict_whitespace": bool,
}


def load_config(path: Optional[Path]) -> Dict[str, Any]:
    """Load l10n.config.json; validates key names and value types. Relative paths resolve from the config dir."""
    if path is None:
        return {}
    data = load_json_data(path)
    if not isinstance(data, dict):
        raise L10nError(f"{path}: config must be a JSON object")
    for k, v in data.items():
        if k.startswith("_"):
            continue  # comment keys
        if k not in CONFIG_KEYS:
            raise L10nError(f"{path}: unknown config key '{k}'; known keys: {', '.join(sorted(CONFIG_KEYS))}")
        if not isinstance(v, CONFIG_KEYS[k]) or isinstance(v, bool) and CONFIG_KEYS[k] is not bool:
            raise L10nError(f"{path}: config key '{k}' has wrong type {type(v).__name__}")
    for k in ("rules_dir", "glossary"):
        if k in data and not os.path.isabs(data[k]):
            data[k] = str((path.parent / data[k]).resolve())
    return data


def pick(cli_value: Any, config: Dict[str, Any], key: str, default: Any) -> Any:
    """Resolve an option: explicit CLI value > config file > default."""
    if cli_value is not None:
        return cli_value
    if key in config:
        return config[key]
    return default


class GlossaryTerm(NamedTuple):
    source: str
    targets: Tuple[str, ...]
    forbidden: Tuple[str, ...]
    regex: re.Pattern


_FORBIDDEN_NOTE_RE = re.compile(r"forbidden\s*:\s*([^|]+)", re.IGNORECASE)


def load_glossary(path: Path, locale: str) -> List[GlossaryTerm]:
    """Load a termbase CSV in either of two layouts.

    Layout A (wide): header 'term_en,<locale>,...,notes' with one column per locale
      (empty cell = no lock for that locale; notes may contain 'forbidden: X; Y').
    Layout B (long): header 'source,target[,locale][,forbidden]'.
    'target' cells may list alternatives separated by '|'; an alternative starting with 're:'
    is a regular expression, otherwise it is a case-insensitive substring (so inflected
    forms such as 'Reaktörü' still satisfy 'Reaktör').
    """
    raw = read_text_bom(path)
    if raw.strip() == "":
        raise L10nError(f"{path}: glossary is empty")
    reader = csv.DictReader(raw.splitlines(keepends=True), delimiter=sniff_delimiter(raw, path.suffix.lower()))
    fields = [f.strip() for f in (reader.fieldnames or [])]
    reader.fieldnames = fields
    lower = {f.lower(): f for f in fields}
    terms: List[GlossaryTerm] = []
    if "source" in lower and "target" in lower:
        src_col, tgt_col, loc_col, forb_col = lower["source"], lower["target"], lower.get("locale"), lower.get("forbidden")
        for row in reader:
            src = _as_str(row.get(src_col)).strip()
            tgt = _as_str(row.get(tgt_col)).strip()
            if not src or not tgt:
                continue
            if loc_col:
                loc = _as_str(row.get(loc_col)).strip()
                if loc and normalize_locale(loc)[0] != locale:
                    continue
            forb = _as_str(row.get(forb_col)).strip() if forb_col else ""
            terms.append(_make_term(src, tgt, forb))
    elif "term_en" in lower:
        src_col = lower["term_en"]
        loc_col = None
        for f in fields:
            try:
                if f.lower() not in ("term_en", "notes") and normalize_locale(f)[0] == locale:
                    loc_col = f
                    break
            except L10nError:
                continue
        if loc_col is None:
            raise L10nError(f"{path}: glossary has no column for locale '{locale}' (columns: {fields})")
        notes_col = lower.get("notes")
        for row in reader:
            src = _as_str(row.get(src_col)).strip()
            tgt = _as_str(row.get(loc_col)).strip()
            if not src or not tgt:
                continue
            forb = ""
            if notes_col:
                m = _FORBIDDEN_NOTE_RE.search(_as_str(row.get(notes_col)))
                forb = m.group(1) if m else ""
            terms.append(_make_term(src, tgt, forb))
    else:
        raise L10nError(f"{path}: glossary header must be 'term_en,<locale>,...,notes' or 'source,target[,locale]'; got {fields}")
    return terms


def _make_term(src: str, tgt: str, forbidden: str) -> GlossaryTerm:
    rx = re.compile(r"(?<!\w)" + re.escape(src) + r"(?!\w)", re.IGNORECASE)
    forb = tuple(x.strip() for x in re.split(r"[;|]", forbidden) if x.strip())
    return GlossaryTerm(src, tuple(t.strip() for t in tgt.split("|") if t.strip()), forb, rx)


def glossary_violations(src: str, dst: str, terms: Sequence[GlossaryTerm]) -> List[str]:
    """Messages for glossary terms present in src whose approved target is absent (or a forbidden one present) in dst."""
    out: List[str] = []
    low = dst.lower()
    for t in terms:
        if not t.regex.search(src):
            continue
        ok = False
        for alt in t.targets:
            if alt.startswith("re:"):
                if re.search(alt[3:], dst, re.IGNORECASE):
                    ok = True
                    break
            elif alt.lower() in low:
                ok = True
                break
        if not ok:
            out.append(f"'{t.source}' must be rendered as {' | '.join(t.targets)}")
        for bad in t.forbidden:
            if bad.lower() in low:
                out.append(f"'{t.source}': forbidden rendering '{bad}' found")
    return out


# --------------------------------------------------------------------------- #
# CLI / report helpers
# --------------------------------------------------------------------------- #

def add_common_args(ap: Any, tool_name: str) -> None:
    """Attach the arguments every script shares (--version, --config, --json [file], --output, --max-report, --debug)."""
    ap.add_argument("--version", action="version", version=f"{tool_name} {__version__}")
    ap.add_argument("--config", help="Project config file (l10n.config.json); explicit CLI flags override it")
    ap.add_argument("--json", nargs="?", const=True, default=None, metavar="FILE",
                    help="Emit a machine-readable JSON report (to stdout, or to FILE when a path is given)")
    ap.add_argument("--output", help="Also write the printed report to this file (UTF-8)")
    ap.add_argument("--max-report", type=int, default=None, help="Max findings to print per severity in text mode (default: unlimited)")
    ap.add_argument("--debug", action="store_true", help="Show Python tracebacks for internal errors")


def add_input_argument(ap: Any, help_text: str, name: str = "input") -> None:
    """Accept the main input file both as a positional argument and as --<name>.

    Every script takes the same two spellings so users never have to remember
    which tool wants `tool.py table.json` and which wants `tool.py --input table.json`.
    Call `resolve_input(ap, args)` right after `parse_args()`.
    """
    ap.add_argument(f"{name}_pos", nargs="?", metavar=name.upper(), help=help_text)
    ap.add_argument(f"--{name}", dest=f"{name}_opt", metavar=name.upper(), help=f"Same as the positional {name.upper()}")


def resolve_input(ap: Any, args: Any, name: str = "input") -> str:
    """Merge the positional and --<name> spellings into `args.<name>`; exit 2 when missing or conflicting."""
    pos = getattr(args, f"{name}_pos", None)
    opt = getattr(args, f"{name}_opt", None)
    if pos and opt and pos != opt:
        ap.error(f"conflicting values for {name.upper()}: positional '{pos}' vs --{name} '{opt}'")
    value = opt or pos
    if not value:
        ap.error(f"the {name.upper()} file is required (positional {name.upper()} or --{name})")
    setattr(args, name, value)
    return value


def emit_report(text: str, payload: Dict[str, Any], json_opt: Any, output: Optional[str]) -> None:
    """Print the text or JSON report; --json FILE writes JSON to FILE and prints a one-line summary."""
    if json_opt:
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        if isinstance(json_opt, str):
            Path(json_opt).write_text(body + "\n", encoding="utf-8")
            print(text.splitlines()[0] if text else "")
            print(f"  JSON report written to {json_opt}")
        else:
            print(body)
    else:
        print(text)
    if output:
        Path(output).write_text((json.dumps(payload, ensure_ascii=False, indent=2) if json_opt else text) + "\n", encoding="utf-8")


def run_main(fn: Any) -> None:
    """Run a script main(): L10nError -> exit 2 with a clean message; unexpected exceptions -> exit 2 (+traceback with --debug)."""
    ensure_utf8_stdio()
    try:
        code = fn()
    except L10nError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as exc:
        if "--debug" in sys.argv:
            raise
        print(f"internal error: {type(exc).__name__}: {exc} (re-run with --debug for a traceback)", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    sys.exit(int(code or 0))
