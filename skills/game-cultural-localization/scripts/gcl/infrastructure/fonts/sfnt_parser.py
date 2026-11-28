"""SFNT (.ttf/.otf/.ttc/.woff) cmap and horizontal metric table parsers."""

import bisect
import struct
from pathlib import Path
from typing import NamedTuple
import zlib

from gcl.domain.errors import L10nError

__layer__ = "infrastructure"
__pattern__ = "Binary Font Parser"
__owns__ = "TTF, OTF, TTC and WOFF sfnt cmap and advance width parsing"

_SFNT_VERSIONS = {0x00010000, 0x4F54544F, 0x74727565}
_FONT_FILE_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2")
_METRIC_TABLES = (b"cmap", b"head", b"hhea", b"hmtx")
_CMAP_PREFERENCE = {(3, 10): 0, (0, 6): 1, (0, 4): 2, (3, 1): 3, (0, 3): 4, (0, 2): 5, (0, 1): 6, (0, 0): 7}


class FontInfo(NamedTuple):
    """Summary metadata describing one font or TMP FontAsset in a fallback chain."""

    path: str
    kind: str
    glyphs: int
    dynamic: bool = False
    has_fallbacks: bool = False
    sub_fonts: int = 1
    atlas_glyphs: int | None = None
    multi_atlas: bool | None = None
    source_font: str | None = None
    fallback_of: str | None = None
    coverage_known: bool = True


class FontParseError(L10nError):
    """Malformed or unsupported font file (exit 2)."""


def _u(fmt: str, data: bytes, off: int, what: str) -> tuple:
    try:
        return struct.unpack_from(fmt, data, off)
    except struct.error:
        raise FontParseError(f"truncated or malformed font while reading {what} at offset {off}")


def _parse_format4(table: bytes, off: int, cps: set[int]) -> None:
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


def parse_cmap_table(table: bytes) -> set[int]:
    """Parse a standalone 'cmap' table into mapped Unicode code points."""
    _ver, num_sub = _u(">HH", table, 0, "cmap header")
    offsets: set[int] = {_u(">HHI", table, 4 + i * 8, "cmap encoding record")[2] for i in range(num_sub)}
    cps: set[int] = set()
    for off in sorted(offsets):
        if off + 2 > len(table):
            raise FontParseError(f"cmap subtable offset {off} beyond table size {len(table)}")
        fmt = _u(">H", table, off, "cmap subtable format")[0]
        if fmt == 0:
            glyphs = _u(">256B", table, off + 6, "format 0 glyph array")
            cps.update(cp for cp, g in enumerate(glyphs) if g != 0)
        elif fmt == 4:
            _parse_format4(table, off, cps)
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
                if not (fmt == 13 and gid == 0):
                    cps.update(range(sc, min(ec, 0x10FFFF) + 1))
    return cps


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
    """Glyph id of a code point in a 'cmap' table (Unicode subtables first), 0 when unmapped."""
    try:
        num_sub = struct.unpack_from(">H", table, 2)[0]
        recs = [struct.unpack_from(">HHI", table, 4 + i * 8) for i in range(num_sub)]
    except struct.error:
        return 0
    seen: set[int] = set()
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
    """The tables of one sfnt face that the scanner reads."""

    cmap: bytes
    head: bytes | None = None
    hhea: bytes | None = None
    hmtx: bytes | None = None


def _face_advance_em(face: SfntFace, gid: int) -> float | None:
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

    def __init__(self, path: Path, kind: str, faces: list[SfntFace]) -> None:
        self.path, self.kind, self.faces = path, kind, faces
        self.cps: set[int] = set()
        for face in faces:
            self.cps |= parse_cmap_table(face.cmap)
        self.info = FontInfo(str(path), kind, len(self.cps), sub_fonts=len(faces))

    def advance_em(self, cp: int) -> float | None:
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
    found: dict[bytes, bytes] = {}
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
        faces = [_sfnt_face_at(data, _u(">I", data, 12 + i * 4, "ttc offset table")[0], f"{font_path.name}[{i}]") for i in range(num_fonts)]
        return SfntFont(font_path, "ttc", faces)
    if magic == b"wOFF":
        return _load_woff(font_path, data)
    if magic == b"wOF2":
        raise FontParseError(f"{font_path}: WOFF2 needs brotli decoding; convert to .ttf/.woff first")
    return SfntFont(font_path, "ttf/otf", [_sfnt_face_at(data, 0, font_path.name)])


def _load_woff(font_path: Path, data: bytes) -> SfntFont:
    _sig, _flavor, _length, num_tables = _u(">4sIIH", data, 0, "woff header")
    found: dict[bytes, bytes] = {}
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


def parse_font_file(font_path: Path) -> tuple[set[int], FontInfo]:
    """Return (code points, info) for .ttf/.otf/.ttc/.woff; raise FontParseError when unreadable."""
    font = load_font_file(font_path)
    return font.cps, font.info
