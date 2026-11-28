"""Strategy + Registry for rich text tag parsing, parity and visual width calculation."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

from gcl.domain.errors import L10nError
from gcl.domain.models import Tag
from gcl.ports.formats import TagStrategy

from .placeholders import compare_placeholders, extract_placeholders

__layer__ = "infrastructure"
__pattern__ = "Strategy and Registry"
__owns__ = "TMP, HTML and BBCode rich text tag strategies plus East Asian visual width"

TAG_STYLES: Tuple[str, ...] = ("auto", "tmp", "html", "bbcode")
TMP_TAGS = frozenset(
    "align allcaps alpha b br color cspace font font-weight gradient i indent line-height line-indent link "
    "lowercase margin mark mspace nobr noparse page pos rotate s size smallcaps space sprite strikethrough "
    "style sub sup u uppercase voffset width".split()
)
HTML_EXTRA_TAGS = frozenset("a p em strong span div img hr ul ol li table tr td th h1 h2 h3 small big tt code pre".split())
BBCODE_TAGS = frozenset(
    "b i u s color url img font size center right left fill indent code table cell p br wave tornado shake fade "
    "rainbow outline_size outline_color bgcolor fgcolor lb rb ul ol hint dropcap pulse char opacity quote list".split()
)
VOID_TAGS = frozenset("br sprite space pos page img hr lb rb char input".split())
ANGLE_TAG_RE = re.compile(r"<(?P<close>/?)(?P<name>[A-Za-z][\w-]*)(?P<attr>(?:\s*=\s*[^<>]*)|(?:\s+[^<>]*))?\s*(?P<self>/?)>")
HEX_COLOR_TAG_RE = re.compile(r"<(?P<hex>#[0-9A-Fa-f]{3,8})>")
BB_TAG_RE = re.compile(r"\[(?P<close>/?)(?P<name>[A-Za-z][\w-]*)(?P<attr>=[^\]]*)?\]")
TMP_COLOR_NAMES = {
    "black": "#000000", "blue": "#0000ff", "green": "#008000", "orange": "#ffa500", "purple": "#800080",
    "red": "#ff0000", "white": "#ffffff", "yellow": "#ffff00", "lightblue": "#add8e6", "aqua": "#00ffff",
    "cyan": "#00ffff", "darkblue": "#00008b", "fuchsia": "#ff00ff", "magenta": "#ff00ff", "brown": "#a52a2a",
    "grey": "#808080", "gray": "#808080", "lime": "#00ff00", "maroon": "#800000", "navy": "#000080",
    "olive": "#808000", "silver": "#c0c0c0", "teal": "#008080",
}
_COLOR_VALUE_RE = re.compile(r"^(<(?:color|mark)=)([^>]+)(>)$")
_ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x034F, 0x061C, 0x180E}


def norm_tag(tag: str) -> str:
    """Canonicalise a tag token by lower casing and resolving named colors to hex."""
    out = re.sub(r"[\s\"']+", "", tag).lower()
    m = _COLOR_VALUE_RE.match(out)
    if m:
        val = TMP_COLOR_NAMES.get(m.group(2), m.group(2))
        if re.fullmatch(r"#[0-9a-f]{8}", val) and val.endswith("ff"):
            val = val[:7]
        elif re.fullmatch(r"#[0-9a-f]{3}", val):
            val = "#" + "".join(c * 2 for c in val[1:])
        out = m.group(1) + val + m.group(3)
    return out


class ConfiguredTagStrategy:
    """Declarative tag extraction and stripping strategy."""

    def __init__(self, style: str, *, angle_tags: Optional[frozenset], allow_all_angle: bool, include_bbcode: bool) -> None:
        self.style = style
        self._angle_tags = angle_tags
        self._allow_all_angle = allow_all_angle
        self._include_bbcode = include_bbcode

    def _keep_angle(self, name: str) -> bool:
        return self._allow_all_angle or (self._angle_tags is not None and name in self._angle_tags)

    def extract(self, text: str) -> List[Tag]:
        found: List[Tuple[int, Tag]] = []
        if self._allow_all_angle or self._angle_tags is not None:
            for m in ANGLE_TAG_RE.finditer(text):
                name = m.group("name").lower()
                if self._keep_angle(name):
                    found.append((m.start(), Tag(name, m.group("close") == "/", norm_tag(m.group(0)), m.group(0))))
            for m in HEX_COLOR_TAG_RE.finditer(text):
                found.append((m.start(), Tag("color", False, norm_tag("<color=" + m.group("hex") + ">"), m.group(0))))
        if self._include_bbcode:
            for m in BB_TAG_RE.finditer(text):
                name = m.group("name").lower()
                if name in BBCODE_TAGS:
                    found.append((m.start(), Tag(name, m.group("close") == "/", norm_tag(m.group(0)), m.group(0))))
        found.sort(key=lambda t: t[0])
        return [t for _pos, t in found]

    def strip(self, text: str) -> str:
        out = text
        if self._allow_all_angle or self._angle_tags is not None:
            out = ANGLE_TAG_RE.sub(lambda m: "" if self._keep_angle(m.group("name").lower()) else m.group(0), out)
            out = HEX_COLOR_TAG_RE.sub("", out)
        if self._include_bbcode:
            out = BB_TAG_RE.sub(lambda m: "" if m.group("name").lower() in BBCODE_TAGS else m.group(0), out)
        return out


class TagRegistry:
    """OCP registry mapping rich text styles to strategies."""

    def __init__(self) -> None:
        self._strategies: Dict[str, TagStrategy] = {}

    def register(self, strategy: TagStrategy) -> None:
        self._strategies[strategy.style] = strategy

    def get(self, style: str) -> TagStrategy:
        strat = self._strategies.get(style)
        if strat is None:
            raise L10nError(f"unknown tag style '{style}'; choose from {', '.join(sorted(self._strategies))}")
        return strat


DEFAULT_TAG_REGISTRY = TagRegistry()
for _tstrat in (
    ConfiguredTagStrategy("auto", angle_tags=None, allow_all_angle=True, include_bbcode=True),
    ConfiguredTagStrategy("tmp", angle_tags=TMP_TAGS, allow_all_angle=False, include_bbcode=False),
    ConfiguredTagStrategy("html", angle_tags=TMP_TAGS | HTML_EXTRA_TAGS, allow_all_angle=False, include_bbcode=False),
    ConfiguredTagStrategy("bbcode", angle_tags=None, allow_all_angle=False, include_bbcode=True),
):
    DEFAULT_TAG_REGISTRY.register(_tstrat)


def extract_tags(text: str, style: str = "auto", registry: TagRegistry = DEFAULT_TAG_REGISTRY) -> List[Tag]:
    return registry.get(style).extract(text)


def strip_tags(text: str, style: str = "auto", registry: TagRegistry = DEFAULT_TAG_REGISTRY) -> str:
    return registry.get(style).strip(text)


def tag_structure_error(tags: Sequence[Tag]) -> Optional[str]:
    """Validate nesting of open and closing tags."""
    stack: List[Tag] = []
    for t in tags:
        if t.raw.rstrip(">]").endswith("/") or t.name in VOID_TAGS:
            continue
        if not t.closing:
            stack.append(t)
        elif not stack:
            return f"closing {t.raw} without an open tag"
        elif stack[-1].name != t.name:
            return f"{t.raw} closes {stack[-1].raw} (wrong order / interleaved)"
        else:
            stack.pop()
    return f"unclosed tag {stack[-1].raw}" if stack else None


def compare_tags(src_tags: Sequence[Tag], dst_tags: Sequence[Tag]) -> List[str]:
    """Return parity errors between two tag sequences."""
    problems: List[str] = []
    sc, dc = Counter(t.norm for t in src_tags), Counter(t.norm for t in dst_tags)
    if sc != dc:
        problems.append(f"rich-text tags src={dict(sc)} vs dst={dict(dc)}")
    src_err, dst_err = tag_structure_error(src_tags), tag_structure_error(dst_tags)
    if dst_err and not src_err:
        problems.append(f"rich-text tag structure: {dst_err}")
    return problems


def parity_problems(src: str, dst: str, ph_style: str = "auto", tag_style: str = "auto") -> List[str]:
    """Combined placeholder and rich text tag parity problems against source."""
    if not str(src).strip() or not str(dst).strip():
        return []
    return (compare_placeholders(extract_placeholders(src, ph_style), extract_placeholders(dst, ph_style))
            + compare_tags(extract_tags(src, tag_style), extract_tags(dst, tag_style)))


def char_width(ch: str, cell: float = 2.0, ambiguous_wide: bool = False) -> float:
    cp = ord(ch)
    if cp in _ZERO_WIDTH or unicodedata.combining(ch) or (0xFE00 <= cp <= 0xFE0F) or (0xE0100 <= cp <= 0xE01EF):
        return 0.0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F") or (eaw == "A" and ambiguous_wide):
        return cell
    return 1.0


def visual_width(text: str, cell: float = 2.0, ambiguous_wide: bool = False, tag_style: str = "auto") -> float:
    clean = unicodedata.normalize("NFC", strip_tags(text, tag_style)).replace("\r\n", "\n")
    return max((sum(char_width(ch, cell, ambiguous_wide) for ch in line) for line in clean.split("\n")), default=0.0)


def line_count(text: str) -> int:
    return text.replace("\r\n", "\n").count("\n") + 1 if text else 0
