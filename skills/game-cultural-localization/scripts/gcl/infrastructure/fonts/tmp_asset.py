"""Unity TextMeshPro FontAsset parser and Assets/.meta GUID index."""

import os
import re
from pathlib import Path
from typing import NamedTuple

from gcl.infrastructure.formats.io_utils import read_text_bom

from .sfnt_parser import FontInfo, FontParseError

__layer__ = "infrastructure"
__pattern__ = "Unity TMP Asset Reader"
__owns__ = "text serialized TextMeshPro FontAsset reading and Unity .meta GUID lookup"

_NUM = r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
_TOP_KEY_RE = re.compile(r"^  ([A-Za-z_]\w*):[ \t]*(.*?)[ \t]*$", re.MULTILINE)
_REF_RE = re.compile(r"\{\s*fileID:\s*(-?\d+)(?:\s*,\s*guid:\s*([0-9A-Fa-f]+))?")
_GUID_RE = re.compile(r"guid:\s*([0-9A-Fa-f]{32})")
_META_GUID_RE = re.compile(rb"(?m)^guid:\s*([0-9A-Fa-f]{32})")
_INDEXED_SUFFIXES = (".asset", ".ttf", ".otf", ".ttc", ".otc")
_GUID_INDEXES: dict[str, dict[str, Path]] = {}


class TmpAssetData(NamedTuple):
    """Parsed tables, glyph metrics, atlas mode and fallbacks of one TMP FontAsset."""

    path: Path
    unicodes: set[int]
    char_glyph: dict[int, tuple[int, float]]
    glyph_advance: dict[int, float]
    point_size: float
    face_scale: float
    mode: int
    multi_atlas: bool | None
    source_guids: tuple[str, ...]
    fallbacks: tuple[tuple[int, str | None], ...]


def _font_asset_doc(txt: str) -> str:
    starts = []
    pos = 0 if txt.startswith("--- !u!") else txt.find("\n--- !u!")
    while pos >= 0:
        starts.append(pos + (0 if txt.startswith("--- !u!", pos) else 1))
        pos = txt.find("\n--- !u!", pos + 1)
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(txt)
        if txt.startswith("--- !u!114 ", start):
            body = txt[start:end]
            if "m_CharacterTable:" in body or "m_AtlasPopulationMode:" in body or "m_glyphInfoList:" in body:
                return body
    return txt


def _top_level(doc: str) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    matches = list(_TOP_KEY_RE.finditer(doc))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(doc)
        out.setdefault(m.group(1), (m.group(2), doc[m.end():end]))
    return out


def _float(rx: str, text: str, default: float) -> float:
    m = re.search(rx + r":\s*" + _NUM, text)
    return float(m.group(1)) if m else default


def read_tmp_asset(asset_path: Path) -> TmpAssetData:
    """Read character table, glyph metrics, atlas mode, source font and fallback table of a TMP FontAsset."""
    doc = _font_asset_doc(read_text_bom(asset_path))
    keys = _top_level(doc)
    inline = lambda key: keys.get(key, ("", ""))[0]
    block = lambda key: keys.get(key, ("", ""))[1]

    char_glyph: dict[int, tuple[int, float]] = {}
    if "m_CharacterTable" in keys:
        for entry in re.split(r"\n  - ", block("m_CharacterTable")):
            u = re.search(r"m_Unicode:\s*(\d+)", entry)
            if u:
                g = re.search(r"m_GlyphIndex:\s*(\d+)", entry)
                char_glyph[int(u.group(1))] = (int(g.group(1)) if g else -1, _float(r"m_Scale", entry, 1.0))
        unicodes = set(char_glyph)
    else:
        unicodes = {int(m) for m in re.findall(r"\bm_Unicode:\s*(\d+)", doc)}
    if not unicodes and "m_glyphInfoList" in doc:
        unicodes = {int(m) for m in re.findall(r"^\s*-\s*id:\s*(\d+)\s*$", doc, re.MULTILINE)}
    glyph_advance: dict[int, float] = {}
    for entry in re.split(r"\n  - ", block("m_GlyphTable")):
        i = re.search(r"m_Index:\s*(\d+)", entry)
        a = re.search(r"m_HorizontalAdvance:\s*" + _NUM, entry)
        if i and a:
            scale = re.search(r"\n    m_Scale:\s*" + _NUM, entry)
            glyph_advance[int(i.group(1))] = float(a.group(1)) * (float(scale.group(1)) if scale else 1.0)
    face = block("m_FaceInfo")
    mode_txt, multi_txt = inline("m_AtlasPopulationMode"), inline("m_IsMultiAtlasTexturesEnabled")
    guids = [m.group(1).lower() for k in ("m_SourceFontFile", "m_SourceFontFile_EditorRef") if (m := _GUID_RE.search(inline(k)))]
    if re.fullmatch(r"[0-9A-Fa-f]{32}", inline("m_SourceFontFileGUID")):
        guids.append(inline("m_SourceFontFileGUID").lower())
    if (m := re.search(r"sourceFontFileGUID:\s*([0-9A-Fa-f]{32})", block("m_CreationSettings"))):
        guids.append(m.group(1).lower())
    tkey = "m_FallbackFontAssetTable" if "m_FallbackFontAssetTable" in keys else "fallbackFontAssets"
    fallbacks = [
        (int(ref.group(1)), ref.group(2).lower() if ref.group(2) else None)
        for ref in _REF_RE.finditer(inline(tkey) + block(tkey))
        if int(ref.group(1)) != 0 or ref.group(2)
    ]
    return TmpAssetData(
        asset_path, unicodes, char_glyph, glyph_advance,
        _float(r"m_PointSize", face, 0.0), _float(r"m_Scale", face, 1.0),
        int(mode_txt) if mode_txt.isdigit() else 0,
        (multi_txt == "1") if multi_txt in ("0", "1") else None,
        tuple(dict.fromkeys(guids)), tuple(fallbacks),
    )


def parse_tmp_asset(asset_path: Path) -> tuple[set[int], FontInfo]:
    """Return (baked code points, info) of a TMP FontAsset without following source font or fallbacks."""
    d = read_tmp_asset(asset_path)
    dynamic = d.mode in (1, 2)
    if not d.unicodes and not dynamic:
        raise FontParseError(f"{asset_path}: no 'm_Unicode' character table found; is this a text-serialized TMP FontAsset?")
    return set(d.unicodes), FontInfo(str(asset_path), "tmp-asset", len(d.unicodes), dynamic, bool(d.fallbacks),
                                     atlas_glyphs=len(d.unicodes), multi_atlas=d.multi_atlas)


def find_assets_dir(path: Path) -> Path | None:
    """Nearest Assets directory above path, preferring one beside ProjectSettings."""
    candidates = [p for p in path.resolve().parents if p.name.lower() == "assets"]
    for p in candidates:
        if (p.parent / "ProjectSettings").is_dir():
            return p
    return candidates[0] if candidates else None


def guid_index(assets_dir: Path) -> dict[str, Path]:
    """GUID -> file for every font asset and font file under Assets via Path.walk()."""
    key = os.path.normcase(str(assets_dir))
    if key not in _GUID_INDEXES:
        index: dict[str, Path] = {}
        for root, _dirs, files in Path(assets_dir).walk():
            for name in files:
                low = name.lower()
                if not low.endswith(".meta") or not low[:-5].endswith(_INDEXED_SUFFIXES):
                    continue
                try:
                    with (root / name).open("rb") as fh:
                        head = fh.read(1024)
                except OSError:
                    continue
                m = _META_GUID_RE.search(head)
                if m:
                    index.setdefault(m.group(1).decode("ascii").lower(), root / name[:-5])
        _GUID_INDEXES[key] = index
    return _GUID_INDEXES[key]
