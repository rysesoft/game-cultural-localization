#!/usr/bin/env python3
"""Font missing-glyph ('tofu' box) and full width fallback scanner for localized string tables.

Reads the Unicode 'cmap' table (formats 0, 4, 6, 12 and 13) and the advance widths
('head', 'hhea', 'hmtx') of .ttf / .otf fonts, every sub-font of a .ttc TrueType
Collection and .woff (zlib) files, plus text-serialized Unity TextMeshPro FontAsset
.asset files, then resolves every character of the target strings along the font chain
the way TextMesh Pro does.  Pure Python 3.9+ standard library.

Font chain
  * The order of --font is the fallback order, the first font is the primary.
  * A TMP asset is searched first, then its own m_FallbackFontAssetTable (recursively,
    every asset once, so cycles end), and only then the next --font.  This mirrors TMP,
    which tries the primary asset, its fallback table and then the global fallback list
    (TMP Settings or a game script).  Pass the global list as the later --font entries.
  * Fallback and source font GUIDs resolve through the .meta files of the nearest Assets
    folder above the asset.  A static atlas (m_AtlasPopulationMode 0) covers only its
    character table, a dynamic one (1 or 2) also covers its source font file.

Findings (exit 1)
  * missing: a character no font of the chain has.  When part of the chain cannot be
    resolved (a dynamic asset whose source font is not found, a fallback outside a Unity
    project or with an unknown GUID) the misses are WARN and the exit code stays 0
    unless --strict is given.
  * full width fallback: outside ja-JP, ko-KR, zh-CN and zh-Hant (or with
    --full-width-check on) a character the primary font lacks and the chain serves from
    a font where its advance is at least --full-width-em (0.9 em), such as ’ or …
    falling down to a CJK font.  Characters that are wide by nature (East Asian Width W
    or F, such as ideographs and kana) are never flagged.
Warnings (no effect on the exit code): a static TMP atlas (coverage fixed at build time),
a dynamic TMP atlas with Multi Atlas Textures off (a full atlas drops new glyphs) and
chain links that could not be resolved.
Unreadable / malformed / unsupported font given with --font (e.g. .woff2 needs brotli) -> exit 2.

Characters ignored: ASCII controls, space, NBSP, ideographic space, zero-width
and variation-selector code points, combining marks (after NFC normalisation),
rich-text tags and {placeholders}.  --also-upper additionally scans the
upper-cased text (for runtime .ToUpper() / <uppercase> buttons, e.g. Turkish İ).
"""

from __future__ import annotations

import argparse
import bisect
import os
import re
import struct
import sys
import unicodedata
import zlib
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, resolve_input, emit_report, extract_placeholders, load_config,
    load_target_rows, normalize_locale, pick, read_text_bom, run_main, strip_tags, __version__,
)

TOOL = "font_glyph_scanner"
_SFNT_VERSIONS = {0x00010000, 0x4F54544F, 0x74727565}  # 1.0, 'OTTO', 'true'
_SKIP_CPS = {0x20, 0xA0, 0x3000, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0xAD, 0x034F, 0x061C, 0x180E}
_FONT_FILE_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2")
_METRIC_TABLES = (b"cmap", b"head", b"hhea", b"hmtx")
CJK_LOCALES = ("ja-JP", "ko-KR", "zh-CN", "zh-Hant")
FULL_WIDTH_EM = 0.9


class FontInfo(NamedTuple):
    path: str
    kind: str            # ttf/otf, ttc, woff, tmp-asset
    glyphs: int          # code points the font covers in the chain model
    dynamic: bool = False
    has_fallbacks: bool = False
    sub_fonts: int = 1
    atlas_glyphs: Optional[int] = None   # tmp-asset: characters baked into m_CharacterTable
    multi_atlas: Optional[bool] = None   # tmp-asset: m_IsMultiAtlasTexturesEnabled
    source_font: Optional[str] = None    # dynamic tmp-asset: the resolved source font file
    fallback_of: Optional[str] = None    # the font whose fallback table brought this one into the chain
    coverage_known: bool = True          # False when a source font or a fallback of this font could not be resolved


class FontParseError(L10nError):
    """Malformed or unsupported font file (exit 2)."""


# --------------------------------------------------------------------------- #
# sfnt / cmap parsing
# --------------------------------------------------------------------------- #

def _u(fmt: str, data: bytes, off: int, what: str) -> tuple:
    try:
        return struct.unpack_from(fmt, data, off)
    except struct.error:
        raise FontParseError(f"truncated or malformed font while reading {what} at offset {off}")


def parse_cmap_table(table: bytes) -> Set[int]:
    """Parse a standalone 'cmap' table (bytes starting at the cmap header) into mapped code points."""
    _ver, num_sub = _u(">HH", table, 0, "cmap header")
    offsets: Set[int] = set()
    for i in range(num_sub):
        _pid, _eid, rel = _u(">HHI", table, 4 + i * 8, "cmap encoding record")
        offsets.add(rel)
    cps: Set[int] = set()
    for off in sorted(offsets):
        if off + 2 > len(table):
            raise FontParseError(f"cmap subtable offset {off} beyond table size {len(table)}")
        fmt = _u(">H", table, off, "cmap subtable format")[0]
        if fmt == 0:
            glyphs = _u(">256B", table, off + 6, "format 0 glyph array")
            cps.update(cp for cp, g in enumerate(glyphs) if g != 0)
        elif fmt == 4:
            _fmt, _length, _lang, seg_x2 = _u(">HHHH", table, off, "format 4 header")
            seg = seg_x2 // 2
            end_off = off + 14
            ends = _u(f">{seg}H", table, end_off, "format 4 endCode")
            start_off = end_off + 2 * seg + 2
            starts = _u(f">{seg}H", table, start_off, "format 4 startCode")
            delta_off = start_off + 2 * seg
            deltas = _u(f">{seg}h", table, delta_off, "format 4 idDelta")
            range_off = delta_off + 2 * seg
            ranges = _u(f">{seg}H", table, range_off, "format 4 idRangeOffset")
            for idx in range(seg):
                sc, ec = starts[idx], ends[idx]
                if sc == 0xFFFF and ec == 0xFFFF:
                    continue
                if ec < sc:
                    raise FontParseError(f"format 4 segment {idx} has endCode < startCode")
                ro, delta = ranges[idx], deltas[idx]
                for cp in range(sc, ec + 1):
                    if ro == 0:
                        gid = (cp + delta) & 0xFFFF
                    else:
                        addr = range_off + 2 * idx + ro + 2 * (cp - sc)
                        if addr + 2 > len(table):
                            continue
                        gid = struct.unpack_from(">H", table, addr)[0]
                        if gid != 0:
                            gid = (gid + delta) & 0xFFFF
                    if gid != 0:
                        cps.add(cp)
        elif fmt == 6:
            _fmt, _length, _lang, first, count = _u(">HHHHH", table, off, "format 6 header")
            glyphs = _u(f">{count}H", table, off + 10, "format 6 glyph array")
            cps.update(first + i for i, g in enumerate(glyphs) if g != 0)
        elif fmt in (12, 13):
            _fmt, _res, _length, _lang, ngroups = _u(">HHIII", table, off, "format 12/13 header")
            goff = off + 16
            for idx in range(ngroups):
                sc, ec, gid = _u(">III", table, goff + idx * 12, "format 12 group")
                if ec < sc or ec - sc > 0x110000:
                    raise FontParseError(f"format {fmt} group {idx} has an invalid range")
                if fmt == 13 and gid == 0:
                    continue
                cps.update(range(sc, min(ec, 0x10FFFF) + 1))
        # formats 2, 8, 10, 14 (variation selectors) carry no additional BMP/SMP coverage for our purpose
    return cps


# Unicode subtables first, so the glyph id comes from the mapping a renderer would use.
_CMAP_PREFERENCE = {(3, 10): 0, (0, 6): 1, (0, 4): 2, (3, 1): 3, (0, 3): 4, (0, 2): 5, (0, 1): 6, (0, 0): 7}


def _subtable_glyph_id(table: bytes, off: int, cp: int) -> int:
    fmt = struct.unpack_from(">H", table, off)[0]
    if fmt == 0:
        return table[off + 6 + cp] if cp < 256 else 0
    if fmt == 4:
        seg = struct.unpack_from(">H", table, off + 6)[0] // 2
        end_off = off + 14
        idx = bisect.bisect_left(struct.unpack_from(f">{seg}H", table, end_off), cp)
        if idx >= seg:
            return 0
        start_off = end_off + 2 * seg + 2
        sc = struct.unpack_from(">H", table, start_off + 2 * idx)[0]
        if cp < sc:
            return 0
        delta_off = start_off + 2 * seg
        delta = struct.unpack_from(">h", table, delta_off + 2 * idx)[0]
        range_off = delta_off + 2 * seg
        ro = struct.unpack_from(">H", table, range_off + 2 * idx)[0]
        if ro == 0:
            return (cp + delta) & 0xFFFF
        gid = struct.unpack_from(">H", table, range_off + 2 * idx + ro + 2 * (cp - sc))[0]
        return (gid + delta) & 0xFFFF if gid else 0
    if fmt == 6:
        first, count = struct.unpack_from(">HH", table, off + 6)
        return struct.unpack_from(">H", table, off + 10 + 2 * (cp - first))[0] if first <= cp < first + count else 0
    if fmt in (12, 13):
        lo, hi = 0, struct.unpack_from(">I", table, off + 12)[0]
        while lo < hi:
            mid = (lo + hi) // 2
            sc, ec, gid = struct.unpack_from(">III", table, off + 16 + mid * 12)
            if cp < sc:
                hi = mid
            elif cp > ec:
                lo = mid + 1
            else:
                return gid + (cp - sc) if fmt == 12 else gid
    return 0


def cmap_glyph_id(table: bytes, cp: int) -> int:
    """Glyph id of a code point in a 'cmap' table (Unicode subtables first), 0 when it is not mapped."""
    try:
        num_sub = struct.unpack_from(">H", table, 2)[0]
        recs = [struct.unpack_from(">HHI", table, 4 + i * 8) for i in range(num_sub)]
    except struct.error:
        return 0
    seen: Set[int] = set()
    for pid, eid, off in sorted(recs, key=lambda r: _CMAP_PREFERENCE.get((r[0], r[1]), 9 if r[0] == 1 else 8)):
        if off in seen:
            continue
        seen.add(off)
        try:
            gid = _subtable_glyph_id(table, off, cp)
        except (struct.error, IndexError):
            gid = 0
        if gid:
            return gid
    return 0


class SfntFace(NamedTuple):
    """The tables of one sfnt face that the scanner reads (head, hhea and hmtx may be absent)."""
    cmap: bytes
    head: Optional[bytes] = None
    hhea: Optional[bytes] = None
    hmtx: Optional[bytes] = None


def _face_advance_em(face: SfntFace, gid: int) -> Optional[float]:
    if not (face.head and face.hhea and face.hmtx):
        return None
    try:
        upm = struct.unpack_from(">H", face.head, 18)[0]
        n_metrics = struct.unpack_from(">H", face.hhea, 34)[0]
        if not upm or not n_metrics:
            return None
        advance = struct.unpack_from(">H", face.hmtx, 4 * min(gid, n_metrics - 1))[0]
    except struct.error:
        return None
    return advance / upm


class SfntFont:
    """A .ttf/.otf/.ttc/.woff file, the code points it maps and the advance width of each one."""

    def __init__(self, path: Path, kind: str, faces: List[SfntFace]) -> None:
        self.path, self.kind, self.faces = path, kind, faces
        self.cps: Set[int] = set()
        for face in faces:
            self.cps |= parse_cmap_table(face.cmap)
        self.info = FontInfo(str(path), kind, len(self.cps), sub_fonts=len(faces))

    def advance_em(self, cp: int) -> Optional[float]:
        """Advance width of the code point as a fraction of the em, None when unmapped or without metrics."""
        for face in self.faces:
            gid = cmap_glyph_id(face.cmap, cp)
            if gid:
                return _face_advance_em(face, gid)
        return None


def _sfnt_face_at(data: bytes, base: int, label: str) -> SfntFace:
    sfnt_ver, num_tables = _u(">IH", data, base, f"{label} sfnt header")
    if sfnt_ver not in _SFNT_VERSIONS:
        raise FontParseError(f"{label}: not a TrueType/OpenType font (sfnt version 0x{sfnt_ver:08X})")
    found: Dict[bytes, bytes] = {}
    for i in range(num_tables):
        tag, _csum, offset, length = _u(">4sIII", data, base + 12 + i * 16, f"{label} table record")
        if tag in _METRIC_TABLES and tag not in found:
            if offset + length > len(data):
                if tag == b"cmap":
                    raise FontParseError(f"{label}: cmap table extends beyond end of file")
                continue
            found[tag] = data[offset:offset + length]
    if b"cmap" not in found:
        raise FontParseError(f"{label}: no 'cmap' table found")
    return SfntFace(found[b"cmap"], found.get(b"head"), found.get(b"hhea"), found.get(b"hmtx"))


def load_font_file(font_path: Path) -> SfntFont:
    """Read a .ttf/.otf/.ttc/.woff file; raise FontParseError when unreadable."""
    try:
        data = font_path.read_bytes()
    except FileNotFoundError:
        raise FontParseError(f"font file not found: {font_path}")
    except (IsADirectoryError, PermissionError) as exc:
        raise FontParseError(f"cannot read font {font_path}: {exc}")
    if len(data) < 12:
        raise FontParseError(f"{font_path}: file too small to be a font ({len(data)} bytes)")
    magic = data[:4]
    if magic == b"ttcf":
        _tag, _ver, num_fonts = _u(">4sIi", data, 0, "ttc header")
        if num_fonts <= 0 or num_fonts > 512:
            raise FontParseError(f"{font_path}: invalid TrueType Collection (numFonts={num_fonts})")
        faces = []
        for i in range(num_fonts):
            off = _u(">I", data, 12 + i * 4, "ttc offset table")[0]
            faces.append(_sfnt_face_at(data, off, f"{font_path.name}[{i}]"))
        return SfntFont(font_path, "ttc", faces)
    if magic == b"wOFF":
        _sig, _flavor, _length, num_tables = _u(">4sIIH", data, 0, "woff header")
        found: Dict[bytes, bytes] = {}
        for i in range(num_tables):
            tag, offset, comp_len, orig_len, _csum = _u(">4sIIII", data, 44 + i * 20, "woff table record")
            if tag in _METRIC_TABLES and tag not in found:
                blob = data[offset:offset + comp_len]
                if comp_len < orig_len:
                    try:
                        blob = zlib.decompress(blob)
                    except zlib.error as exc:
                        if tag == b"cmap":
                            raise FontParseError(f"{font_path}: cmap table zlib error: {exc}")
                        continue
                found[tag] = blob
        if b"cmap" not in found:
            raise FontParseError(f"{font_path}: no 'cmap' table in WOFF")
        return SfntFont(font_path, "woff", [SfntFace(found[b"cmap"], found.get(b"head"), found.get(b"hhea"), found.get(b"hmtx"))])
    if magic == b"wOF2":
        raise FontParseError(f"{font_path}: WOFF2 needs brotli decoding; convert to .ttf/.woff first")
    return SfntFont(font_path, "ttf/otf", [_sfnt_face_at(data, 0, font_path.name)])


def parse_font_file(font_path: Path) -> Tuple[Set[int], FontInfo]:
    """Return (code points, info) for .ttf/.otf/.ttc/.woff; raise FontParseError when unreadable."""
    font = load_font_file(font_path)
    return font.cps, font.info


# --------------------------------------------------------------------------- #
# Unity TextMeshPro FontAsset (.asset)
# --------------------------------------------------------------------------- #

_NUM = r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
_TOP_KEY_RE = re.compile(r"^  ([A-Za-z_]\w*):[ \t]*(.*?)[ \t]*$", re.MULTILINE)
_REF_RE = re.compile(r"\{\s*fileID:\s*(-?\d+)(?:\s*,\s*guid:\s*([0-9A-Fa-f]+))?")
_GUID_RE = re.compile(r"guid:\s*([0-9A-Fa-f]{32})")


class TmpAssetData(NamedTuple):
    """What the scanner reads from a text-serialized TMP FontAsset."""
    path: Path
    unicodes: Set[int]
    char_glyph: Dict[int, Tuple[int, float]]     # unicode -> (glyph index, character scale)
    glyph_advance: Dict[int, float]              # glyph index -> m_HorizontalAdvance x glyph scale
    point_size: float
    face_scale: float
    mode: int                                    # m_AtlasPopulationMode, 0 static, 1 dynamic, 2 dynamic OS
    multi_atlas: Optional[bool]
    source_guids: Tuple[str, ...]
    fallbacks: Tuple[Tuple[int, Optional[str]], ...]   # (fileID, guid) of every non-empty fallback slot


def _font_asset_doc(txt: str) -> str:
    """The MonoBehaviour document of a TMP FontAsset file (the file may also hold its material and atlas textures)."""
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


def _top_level(doc: str) -> Dict[str, Tuple[str, str]]:
    """Top level keys of a MonoBehaviour body, key -> (inline value, the indented block below it)."""
    out: Dict[str, Tuple[str, str]] = {}
    matches = list(_TOP_KEY_RE.finditer(doc))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(doc)
        out.setdefault(m.group(1), (m.group(2), doc[m.end():end]))
    return out


def _float(rx: str, text: str, default: float) -> float:
    m = re.search(rx + r":\s*" + _NUM, text)
    return float(m.group(1)) if m else default


def read_tmp_asset(asset_path: Path) -> TmpAssetData:
    """Read the character table, glyph metrics, atlas mode, source font and fallback table of a TMP FontAsset."""
    txt = read_text_bom(asset_path)
    doc = _font_asset_doc(txt)
    keys = _top_level(doc)

    def inline(key: str) -> str:
        return keys.get(key, ("", ""))[0]

    def block(key: str) -> str:
        return keys.get(key, ("", ""))[1]

    char_glyph: Dict[int, Tuple[int, float]] = {}
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
    glyph_advance: Dict[int, float] = {}
    for entry in re.split(r"\n  - ", block("m_GlyphTable")):
        i = re.search(r"m_Index:\s*(\d+)", entry)
        a = re.search(r"m_HorizontalAdvance:\s*" + _NUM, entry)
        if i and a:
            scale = re.search(r"\n    m_Scale:\s*" + _NUM, entry)
            glyph_advance[int(i.group(1))] = float(a.group(1)) * (float(scale.group(1)) if scale else 1.0)
    face = block("m_FaceInfo")
    mode_txt = inline("m_AtlasPopulationMode")
    multi_txt = inline("m_IsMultiAtlasTexturesEnabled")
    guids: List[str] = []
    for key in ("m_SourceFontFile", "m_SourceFontFile_EditorRef"):
        m = _GUID_RE.search(inline(key))
        if m:
            guids.append(m.group(1).lower())
    if re.fullmatch(r"[0-9A-Fa-f]{32}", inline("m_SourceFontFileGUID")):
        guids.append(inline("m_SourceFontFileGUID").lower())
    m = re.search(r"sourceFontFileGUID:\s*([0-9A-Fa-f]{32})", block("m_CreationSettings"))
    if m:
        guids.append(m.group(1).lower())
    table_key = "m_FallbackFontAssetTable" if "m_FallbackFontAssetTable" in keys else "fallbackFontAssets"
    fallbacks = []
    for ref in _REF_RE.finditer(inline(table_key) + block(table_key)):
        file_id, guid = int(ref.group(1)), ref.group(2)
        if file_id != 0 or guid:  # {fileID: 0} is an empty slot, TMP skips it
            fallbacks.append((file_id, guid.lower() if guid else None))
    return TmpAssetData(
        asset_path, unicodes, char_glyph, glyph_advance,
        _float(r"m_PointSize", face, 0.0), _float(r"m_Scale", face, 1.0),
        int(mode_txt) if mode_txt.isdigit() else 0,
        (multi_txt == "1") if multi_txt in ("0", "1") else None,
        tuple(dict.fromkeys(guids)), tuple(fallbacks),
    )


def parse_tmp_asset(asset_path: Path) -> Tuple[Set[int], FontInfo]:
    """Return (baked code points, info) of a TMP FontAsset without following its source font or fallbacks."""
    d = read_tmp_asset(asset_path)
    dynamic = d.mode in (1, 2)
    if not d.unicodes and not dynamic:
        raise FontParseError(f"{asset_path}: no 'm_Unicode' character table found; is this a text-serialized TMP FontAsset?")
    return set(d.unicodes), FontInfo(str(asset_path), "tmp-asset", len(d.unicodes), dynamic, bool(d.fallbacks),
                                     atlas_glyphs=len(d.unicodes), multi_atlas=d.multi_atlas)


# --------------------------------------------------------------------------- #
# Unity project lookup (GUID -> file through .meta)
# --------------------------------------------------------------------------- #

_META_GUID_RE = re.compile(rb"(?m)^guid:\s*([0-9A-Fa-f]{32})")
_INDEXED_SUFFIXES = (".asset", ".ttf", ".otf", ".ttc", ".otc")
_GUID_INDEXES: Dict[str, Dict[str, Path]] = {}


def find_assets_dir(path: Path) -> Optional[Path]:
    """The nearest folder named Assets above the path, preferring one that sits next to ProjectSettings."""
    candidates = [p for p in path.resolve().parents if p.name.lower() == "assets"]
    for p in candidates:
        if (p.parent / "ProjectSettings").is_dir():
            return p
    return candidates[0] if candidates else None


def guid_index(assets_dir: Path) -> Dict[str, Path]:
    """GUID -> file for every font asset and font file under the Assets folder (built once per folder)."""
    key = os.path.normcase(str(assets_dir))
    if key not in _GUID_INDEXES:
        index: Dict[str, Path] = {}
        for root, _dirs, files in os.walk(assets_dir):
            for name in files:
                low = name.lower()
                if not low.endswith(".meta") or not low[:-5].endswith(_INDEXED_SUFFIXES):
                    continue
                try:
                    with open(os.path.join(root, name), "rb") as fh:
                        head = fh.read(1024)
                except OSError:
                    continue
                m = _META_GUID_RE.search(head)
                if m:
                    index.setdefault(m.group(1).decode("ascii").lower(), Path(root) / name[:-5])
        _GUID_INDEXES[key] = index
    return _GUID_INDEXES[key]


# --------------------------------------------------------------------------- #
# Font chain
# --------------------------------------------------------------------------- #

class ChainFont:
    """One font of the chain, what it covers, how wide each glyph is and which fonts it falls back to."""

    def __init__(self, path: Path, info: FontInfo, cps: Set[int], advance: Callable[[int], Optional[float]],
                 fallback_paths: Optional[List[Path]] = None, notes: Optional[List[Tuple[str, str]]] = None) -> None:
        self.path, self.info, self.cps, self.advance = path, info, cps, advance
        self.fallback_paths: List[Path] = fallback_paths or []
        self.notes: List[Tuple[str, str]] = notes or []  # (code, message)


class ChainEntry(NamedTuple):
    font: ChainFont
    parent: Optional[ChainFont]   # the font whose fallback table brought this one in, None for a --font entry
    depth: int


def _key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


class FontChain:
    """Loads fonts once each and lays out the order in which TMP searches them."""

    def __init__(self) -> None:
        self._fonts: Dict[str, ChainFont] = {}
        self._files: Dict[str, SfntFont] = {}

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
        notes: List[Tuple[str, str]] = []
        if dynamic and d.multi_atlas is False:
            notes.append(("dynamic_single_atlas", "dynamic atlas with Multi Atlas Textures off, once the atlas texture is full new characters are dropped"))
        elif not dynamic:
            notes.append(("static_atlas", "static atlas, its characters are fixed at build time and any other character falls through to the next font"))
        assets_dir = find_assets_dir(path) if (dynamic or d.fallbacks) else None
        index = guid_index(assets_dir) if assets_dir else {}
        known = True
        if (dynamic or d.fallbacks) and assets_dir is None:
            known = False
            notes.append(("outside_unity_project", "no Assets folder above the asset, so its source font and fallback table are not followed"))
        cps = set(d.unicodes)
        source: Optional[SfntFont] = None
        if dynamic and assets_dir is not None:
            for guid in d.source_guids:
                p = index.get(guid)
                if p is None or p.suffix.lower() not in _FONT_FILE_SUFFIXES or not p.is_file():
                    continue
                try:
                    source = self.font_file(p)
                    break
                except FontParseError as exc:
                    notes.append(("unreadable_source_font", f"source font {p.name} cannot be read ({exc})"))
            if source is None:
                known = False
                notes.append(("unresolved_source_font", "dynamic atlas whose source font file was not found, only its baked characters are counted"))
            else:
                cps |= source.cps
        fallback_paths: List[Path] = []
        if assets_dir is not None:
            for file_id, guid in d.fallbacks:
                p = index.get(guid) if guid else None
                if p is None or p.suffix.lower() != ".asset" or not p.is_file():
                    known = False
                    notes.append(("unresolved_fallback", f"fallback {guid or f'fileID {file_id}'} was not found in the project, that branch is not followed"))
                else:
                    fallback_paths.append(p)

        def advance(cp: int) -> Optional[float]:
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

    def search_order(self, roots: List[ChainFont]) -> List[ChainEntry]:
        """Every font in TMP search order, each --font followed by its fallback table (depth first, every font once)."""
        order: List[ChainEntry] = []
        seen: Set[str] = set()
        for root in roots:
            stack: List[ChainEntry] = [ChainEntry(root, None, 0)]
            while stack:
                entry = stack.pop()
                key = _key(entry.font.path)
                if key in seen:
                    continue
                seen.add(key)
                order.append(entry)
                children: List[ChainFont] = []
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
    served: Dict[int, Optional[int]]          # code point -> index in the search order, None when missing
    missing: List[int]
    full_width: List[Tuple[int, int, float]]  # (code point, index in the search order, advance in em)


def resolve_chars(order: List[ChainEntry], cps: Any, check_full_width: bool, threshold: float = FULL_WIDTH_EM) -> ChainResult:
    """Find the font that serves every code point and the full width fallbacks among them."""
    served: Dict[int, Optional[int]] = {}
    wide: List[Tuple[int, int, float]] = []
    for cp in sorted(cps):
        idx = next((i for i, e in enumerate(order) if cp in e.font.cps), None)
        served[cp] = idx
        if not check_full_width or not idx or unicodedata.east_asian_width(chr(cp)) in ("W", "F"):
            continue  # idx 0 is the primary font itself
        em = order[idx].font.advance(cp)
        if em is not None and em >= threshold:
            wide.append((cp, idx, em))
    return ChainResult(served, [cp for cp, i in served.items() if i is None], wide)


# --------------------------------------------------------------------------- #
# Target characters
# --------------------------------------------------------------------------- #

def collect_target_chars(input_path: Path, dst_field: str, also_upper: bool = False, placeholder_style: str = "auto") -> Dict[int, Tuple[str, str, int]]:
    """Map code point -> (char, first key, occurrence count) for every renderable character in the targets."""
    chars: Dict[int, Tuple[str, str, int]] = {}
    for key, text in load_target_rows(input_path, dst_field):
        cleaned = strip_tags(text)
        for ph in extract_placeholders(cleaned, placeholder_style).top:
            cleaned = cleaned.replace("{" + ph + "}", "")
        variants = [unicodedata.normalize("NFC", cleaned)]
        if also_upper:
            variants.append(unicodedata.normalize("NFC", cleaned.upper()))
        for variant in variants:
            for ch in variant:
                cp = ord(ch)
                if cp in _SKIP_CPS or cp < 0x20 or unicodedata.combining(ch) or 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF:
                    continue
                if cp in chars:
                    c, k, n = chars[cp]
                    chars[cp] = (c, k, n + 1)
                else:
                    chars[cp] = (ch, key, 1)
    return chars


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Scan localized strings for glyphs missing from a font chain of TTF/OTF/TTC/WOFF fonts "
                                 "and Unity TMP FontAssets, and for marks that fall back to a full width glyph (exit 0 ok, 1 findings, 2 bad input)")
    add_input_argument(ap, "Localized JSON, CSV/TSV, PO, Unity .asset string table, or plain text file")
    ap.add_argument("--dst-field", default=None, help="Target text column (default: dst)")
    ap.add_argument("--font", action="append", required=True,
                    help="Font file, .ttf, .otf, .ttc, .woff or a Unity TMP FontAsset .asset. Repeatable, the order is the fallback order "
                         "and the first font is the primary. A TMP asset brings its own fallback table along")
    ap.add_argument("--locale", default=None,
                    help="Target locale. The full width check is skipped for ja-JP, ko-KR, zh-CN and zh-Hant. "
                         "Without it a --dst-field that names a locale counts")
    ap.add_argument("--full-width-check", choices=("auto", "on", "off"), default="auto",
                    help="auto checks every locale except the CJK ones, on checks any locale, off never checks (default auto)")
    ap.add_argument("--full-width-em", type=float, default=FULL_WIDTH_EM,
                    help=f"Advance, as a fraction of the em, from which a fallback glyph counts as full width (default {FULL_WIDTH_EM})")
    ap.add_argument("--strict", action="store_true", help="Treat missing glyphs as ERR even when part of the font chain could not be resolved")
    ap.add_argument("--also-upper", action="store_true", help="Also scan the upper-cased text (runtime .ToUpper() / <uppercase> buttons)")
    add_common_args(ap, TOOL)
    return ap


def _resolve_locale(explicit: Optional[str], dst_field: str) -> Optional[str]:
    if explicit:
        return normalize_locale(explicit)[0]  # an unknown locale is a usage error (exit 2)
    try:
        return normalize_locale(dst_field)[0]
    except L10nError:
        return None


def _sample(chars: List[str], limit: int = 60) -> str:
    text = "".join(chars)
    return text if len(text) <= limit else text[:limit] + " ..."


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    if not args.full_width_em > 0:
        ap.error("--full-width-em must be greater than 0")
    cfg = load_config(Path(args.config)) if args.config else {}
    dst_field = pick(args.dst_field, cfg, "dst_field", "dst")
    locale = _resolve_locale(args.locale, dst_field)
    check_wide = args.full_width_check == "on" or (args.full_width_check == "auto" and locale not in CJK_LOCALES)

    chain = FontChain()
    roots = [chain.load(Path(fp)) for fp in args.font]
    order = chain.search_order(roots)
    used = collect_target_chars(Path(args.input), dst_field, args.also_upper, pick(None, cfg, "placeholder_style", "auto"))
    result = resolve_chars(order, used, check_wide, args.full_width_em)
    missing = result.missing
    lenient = (not args.strict) and any(not e.font.info.coverage_known for e in order)
    exit_code = EXIT_FINDINGS if ((missing and not lenient) or result.full_width) else EXIT_OK
    level = "WARN" if lenient else "ERR"
    warnings = [(e.font, code, msg) for e in order for code, msg in e.font.notes]
    served_count = [0] * len(order)
    served_chars: List[List[str]] = [[] for _ in order]
    for cp, idx in result.served.items():
        if idx is not None:
            served_count[idx] += 1
            served_chars[idx].append(used[cp][0])
    limit = args.max_report

    def cut(items: List[Any]) -> List[Any]:
        return items if limit is None else items[:limit]

    lines = ["Font Coverage Report:"]
    lines.append("  Search order (the first --font is the primary, a TMP asset's own fallback table comes before the next --font)")
    for n, e in enumerate(order):
        i = e.font.info
        desc = [i.kind]
        if i.kind == "ttc":
            desc.append(f"{i.sub_fonts} sub-fonts")
        if i.kind == "tmp-asset":
            desc.append(("dynamic atlas" + (f" from {Path(i.source_font).name}" if i.source_font else "")) if i.dynamic else "static atlas")
        if e.parent is not None:
            desc.append(f"fallback of {e.parent.path.name}")
        lines.append(f"  {n + 1}. {'  ' * e.depth}{e.font.path.name}: {i.glyphs} code points ({', '.join(desc)}), serves {served_count[n]}")
    lines.append(f"  Unique target characters used: {len(used)}")
    lines.append(f"  Missing characters (tofu)     : {len(missing)}" + (" [WARN, part of the font chain could not be resolved, pass --strict to fail]" if lenient and missing else ""))
    blocks: Dict[str, int] = {}
    for cp in missing:
        blocks[_block_name(used[cp][0])] = blocks.get(_block_name(used[cp][0]), 0) + 1
    for cp in cut(missing):
        ch, key, n = used[cp]
        lines.append(f"  {level} U+{cp:04X} {ch!r} {unicodedata.name(ch, 'UNKNOWN')} x{n}, first seen in '{key}'")
    if limit is not None and len(missing) > limit:
        lines.append(f"  ... and {len(missing) - limit} more (raise --max-report or use --json).")
    if blocks:
        lines.append("  By script/block: " + ", ".join(f"{b}: {n}" for b, n in sorted(blocks.items())))
    if check_wide:
        lines.append(f"  Full width fallbacks          : {len(result.full_width)}")
        for cp, idx, em in cut(result.full_width):
            ch, key, n = used[cp]
            lines.append(f"  WIDE U+{cp:04X} {ch!r} {unicodedata.name(ch, 'UNKNOWN')} x{n}, {em:.2f} em in {order[idx].font.path.name} "
                         f"which the primary font lacks, first seen in '{key}'")
        if limit is not None and len(result.full_width) > limit:
            lines.append(f"  ... and {len(result.full_width) - limit} more (raise --max-report or use --json).")
    else:
        lines.append(f"  Full width fallbacks          : not checked ({'--full-width-check off' if args.full_width_check == 'off' else locale})")
    for n, e in enumerate(order):
        if n and served_chars[n]:
            lines.append(f"  Served by {e.font.path.name} ({served_count[n]}) {_sample(served_chars[n])}")
    if warnings:
        lines.append(f"  Font chain warnings           : {len(warnings)}")
        for font, code, msg in cut(warnings):
            lines.append(f"  WARN {font.path.name} {code}, {msg}")
        if limit is not None and len(warnings) > limit:
            lines.append(f"  ... and {len(warnings) - limit} more (raise --max-report or use --json).")
    lines.append(f"  Exit code: {exit_code}")

    fonts = []
    for n, e in enumerate(order):
        entry = e.font.info._replace(fallback_of=str(e.parent.path) if e.parent is not None else None)._asdict()
        entry["served"] = served_count[n]
        fonts.append(entry)
    payload = {
        "tool": TOOL, "version": __version__, "input": str(args.input),
        "fonts": fonts, "lenient": lenient, "locale": locale, "full_width_checked": check_wide,
        "unique_chars": len(used),
        "summary": {"missing": len(missing), "severity": level, "full_width": len(result.full_width), "warnings": len(warnings)},
        "missing": [{"codepoint": f"U+{cp:04X}", "char": used[cp][0], "name": unicodedata.name(used[cp][0], "UNKNOWN"),
                     "count": used[cp][2], "first_key": used[cp][1]} for cp in missing],
        "full_width": [{"codepoint": f"U+{cp:04X}", "char": used[cp][0], "name": unicodedata.name(used[cp][0], "UNKNOWN"),
                        "count": used[cp][2], "first_key": used[cp][1], "font": str(order[idx].font.path), "advance_em": round(em, 3)}
                       for cp, idx, em in result.full_width],
        "chars": [{"codepoint": f"U+{cp:04X}", "char": used[cp][0], "count": used[cp][2], "first_key": used[cp][1],
                   "font": str(order[idx].font.path) if idx is not None else None} for cp, idx in result.served.items()],
        "warnings": [{"font": str(font.path), "code": code, "message": msg} for font, code, msg in warnings],
        "exit_code": exit_code,
    }
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


def _block_name(ch: str) -> str:
    cp = ord(ch)
    if cp < 0x80:
        return "Basic Latin"
    if cp < 0x250:
        return "Latin (accented)"
    if 0x370 <= cp < 0x400:
        return "Greek"
    if 0x400 <= cp < 0x530:
        return "Cyrillic"
    if 0x3040 <= cp < 0x3100:
        return "Kana"
    if 0xAC00 <= cp < 0xD7B0 or 0x1100 <= cp < 0x1200 or 0x3130 <= cp < 0x3190:
        return "Hangul"
    if 0x4E00 <= cp < 0xA000 or 0x3400 <= cp < 0x4DC0 or 0x20000 <= cp < 0x32000:
        return "CJK Ideographs"
    if 0xFF00 <= cp < 0xFFF0:
        return "Fullwidth forms"
    if 0x1F000 <= cp < 0x1FB00 or 0x2600 <= cp < 0x2800:
        return "Emoji / symbols"
    if 0x2000 <= cp < 0x2070:
        return "General punctuation"
    return unicodedata.category(ch)


if __name__ == "__main__":
    run_main(main)
