"""TMP fallback chain traversal, character resolution and target code point collection."""

import os
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

from gcl.domain.errors import L10nError
from gcl.infrastructure.formats.registry import load_target_rows
from gcl.infrastructure.tokens.placeholders import extract_placeholders
from gcl.infrastructure.tokens.rich_tags import strip_tags

from .sfnt_parser import _FONT_FILE_SUFFIXES, FontInfo, FontParseError, SfntFont, load_font_file
from .tmp_asset import find_assets_dir, guid_index, read_tmp_asset

__layer__ = "infrastructure"
__pattern__ = "Composite Fallback Chain"
__owns__ = "FontChain traversal, glyph coverage resolution and renderable character collection"

_SKIP_CPS = {0x20, 0xA0, 0x3000, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0xAD, 0x034F, 0x061C, 0x180E}
CJK_LOCALES = ("ja-JP", "ko-KR", "zh-CN", "zh-Hant")
FULL_WIDTH_EM = 0.9


class ChainFont:
    """One font of the chain, what it covers, advance widths and fallback paths."""

    def __init__(
        self,
        path: Path,
        info: FontInfo,
        cps: set[int],
        advance: Callable[[int], float | None],
        fallback_paths: list[Path] | None = None,
        notes: list[tuple[str, str]] | None = None,
    ) -> None:
        self.path, self.info, self.cps, self.advance = path, info, cps, advance
        self.fallback_paths: list[Path] = fallback_paths or []
        self.notes: list[tuple[str, str]] = notes or []


class ChainEntry(NamedTuple):
    font: ChainFont
    parent: ChainFont | None
    depth: int


def _key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


class FontChain:
    """Loads fonts once each and lays out TMP depth first fallback search order."""

    def __init__(self) -> None:
        self._fonts: dict[str, ChainFont] = {}
        self._files: dict[str, SfntFont] = {}

    def font_file(self, path: Path) -> SfntFont:
        key = _key(path)
        if key not in self._files:
            self._files[key] = load_font_file(path)
        return self._files[key]

    def load(self, path: Path) -> ChainFont:
        key = _key(path)
        if key in self._fonts:
            return self._fonts[key]
        suffix = path.suffix.lower()
        if suffix == ".asset":
            font = self._load_tmp(path)
        elif suffix in _FONT_FILE_SUFFIXES:
            sf = self.font_file(path)
            font = ChainFont(path, sf.info, sf.cps, sf.advance_em)
        else:
            raise L10nError(f"unsupported font file type '{path.suffix}': {path} (use .ttf/.otf/.ttc/.woff or a TMP .asset)")
        self._fonts[key] = font
        return font

    def _load_tmp(self, path: Path) -> ChainFont:
        d = read_tmp_asset(path)
        dynamic = d.mode in (1, 2)
        if not d.unicodes and not dynamic:
            raise FontParseError(f"{path}: no 'm_Unicode' character table found; is this a text-serialized TMP FontAsset?")
        notes: list[tuple[str, str]] = []
        if dynamic and d.multi_atlas is False:
            notes.append(("dynamic_single_atlas", "dynamic atlas with Multi Atlas Textures off, once the atlas texture is full new characters are dropped"))
        elif not dynamic:
            notes.append(("static_atlas", "static atlas, its characters are fixed at build time and any other character falls through to the next font"))
        assets_dir = find_assets_dir(path) if (dynamic or d.fallbacks) else None
        index = guid_index(assets_dir) if assets_dir else {}
        known = bool(assets_dir is not None or not (dynamic or d.fallbacks))
        if (dynamic or d.fallbacks) and assets_dir is None:
            notes.append(("outside_unity_project", "no Assets folder above the asset, so its source font and fallback table are not followed"))
        cps = set(d.unicodes)
        source, src_known = self._resolve_tmp_source(d, assets_dir, index, notes)
        if not src_known:
            known = False
        if source is not None:
            cps |= source.cps
        fallback_paths, fb_known = self._resolve_tmp_fallbacks(d, assets_dir, index, notes)
        if not fb_known:
            known = False

        def advance(cp: int) -> float | None:
            glyph = d.char_glyph.get(cp)
            if glyph is not None and glyph[0] in d.glyph_advance and d.point_size > 0:
                return d.glyph_advance[glyph[0]] * glyph[1] * d.face_scale / d.point_size
            if source is not None and cp in source.cps:
                em = source.advance_em(cp)
                return em * d.face_scale if em is not None else None
            return None

        info = FontInfo(str(path), "tmp-asset", len(cps), dynamic, bool(d.fallbacks), atlas_glyphs=len(d.unicodes),
                        multi_atlas=d.multi_atlas, source_font=str(source.path) if source else None, coverage_known=known)
        return ChainFont(path, info, cps, advance, fallback_paths, notes)

    def _resolve_tmp_source(self, d: Any, assets_dir: Path | None, index: dict[str, Path], notes: list[tuple[str, str]]) -> tuple[SfntFont | None, bool]:
        if d.mode not in (1, 2) or assets_dir is None:
            return None, True
        for guid in d.source_guids:
            p = index.get(guid)
            if p is None or p.suffix.lower() not in _FONT_FILE_SUFFIXES or not p.is_file():
                continue
            try:
                return self.font_file(p), True
            except FontParseError as exc:
                notes.append(("unreadable_source_font", f"source font {p.name} cannot be read ({exc})"))
        notes.append(("unresolved_source_font", "dynamic atlas whose source font file was not found, only its baked characters are counted"))
        return None, False

    @staticmethod
    def _resolve_tmp_fallbacks(d: Any, assets_dir: Path | None, index: dict[str, Path], notes: list[tuple[str, str]]) -> tuple[list[Path], bool]:
        if assets_dir is None:
            return [], True
        fallback_paths: list[Path] = []
        known = True
        for file_id, guid in d.fallbacks:
            p = index.get(guid) if guid else None
            if p is None or p.suffix.lower() != ".asset" or not p.is_file():
                known = False
                notes.append(("unresolved_fallback", f"fallback {guid or f'fileID {file_id}'} was not found in the project, that branch is not followed"))
            else:
                fallback_paths.append(p)
        return fallback_paths, known

    def search_order(self, roots: list[ChainFont]) -> list[ChainEntry]:
        """Every font in TMP search order, each --font followed by its fallback table."""
        order: list[ChainEntry] = []
        seen: set[str] = set()
        for root in roots:
            stack: list[ChainEntry] = [ChainEntry(root, None, 0)]
            while stack:
                entry = stack.pop()
                key = _key(entry.font.path)
                if key in seen:
                    continue
                seen.add(key)
                order.append(entry)
                children: list[ChainFont] = []
                for fb in entry.font.fallback_paths:
                    try:
                        children.append(self.load(fb))
                    except L10nError as exc:
                        entry.font.notes.append(("unreadable_fallback", f"fallback {fb.name} cannot be read ({exc}), that branch is not followed"))
                        entry.font.info = entry.font.info._replace(coverage_known=False)
                for child in reversed(children):
                    stack.append(ChainEntry(child, entry.font, entry.depth + 1))
        return order


class ChainResult(NamedTuple):
    served: dict[int, int | None]
    missing: list[int]
    full_width: list[tuple[int, int, float]]


def resolve_chars(order: list[ChainEntry], cps: Any, check_full_width: bool, threshold: float = FULL_WIDTH_EM) -> ChainResult:
    """Find the serving font and full width fallbacks for every code point."""
    served: dict[int, int | None] = {}
    wide: list[tuple[int, int, float]] = []
    for cp in sorted(cps):
        idx = next((i for i, e in enumerate(order) if cp in e.font.cps), None)
        served[cp] = idx
        if not check_full_width or not idx or unicodedata.east_asian_width(chr(cp)) in ("W", "F"):
            continue
        em = order[idx].font.advance(cp)
        if em is not None and em >= threshold:
            wide.append((cp, idx, em))
    return ChainResult(served, [cp for cp, i in served.items() if i is None], wide)


def collect_target_chars(input_path: Path, dst_field: str, also_upper: bool = False, placeholder_style: str = "auto") -> dict[int, tuple[str, str, int]]:
    """Map code point -> (char, first key, occurrence count) for every renderable target character."""
    chars: dict[int, tuple[str, str, int]] = {}
    for key, text in load_target_rows(input_path, dst_field):
        cleaned = strip_tags(text)
        for ph in extract_placeholders(cleaned, placeholder_style).top:
            cleaned = cleaned.replace("{" + ph + "}", "")
        variants = [unicodedata.normalize("NFC", cleaned)] + ([unicodedata.normalize("NFC", cleaned.upper())] if also_upper else [])
        for variant in variants:
            for ch in variant:
                cp = ord(ch)
                if cp in _SKIP_CPS or cp < 0x20 or unicodedata.combining(ch) or 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF:
                    continue
                c, k, n = chars.get(cp, (ch, key, 0))
                chars[cp] = (c, k, n + 1)
    return chars


def block_name(ch: str) -> str:
    """Human readable Unicode block label for font coverage summaries."""
    cp = ord(ch)
    ranges = (
        (cp < 0x80, "Basic Latin"),
        (cp < 0x250, "Latin (accented)"),
        (0x370 <= cp < 0x400, "Greek"),
        (0x400 <= cp < 0x530, "Cyrillic"),
        (0x3040 <= cp < 0x3100, "Kana"),
        (0xAC00 <= cp < 0xD7B0 or 0x1100 <= cp < 0x1200 or 0x3130 <= cp < 0x3190, "Hangul"),
        (0x4E00 <= cp < 0xA000 or 0x3400 <= cp < 0x4DC0 or 0x20000 <= cp < 0x32000, "CJK Ideographs"),
        (0xFF00 <= cp < 0xFFF0, "Fullwidth forms"),
        (0x1F000 <= cp < 0x1FB00 or 0x2600 <= cp < 0x2800, "Emoji / symbols"),
        (0x2000 <= cp < 0x2070, "General punctuation"),
    )
    for cond, label in ranges:
        if cond:
            return label
    return unicodedata.category(ch)


_block_name = block_name
