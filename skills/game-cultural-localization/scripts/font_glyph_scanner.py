#!/usr/bin/env python3
"""Font missing-glyph ('tofu' box) scanner for localized string tables.

Reads the Unicode 'cmap' table (formats 0, 4, 6, 12 and 13) of .ttf / .otf
fonts, every sub-font of a .ttc TrueType Collection, and .woff (zlib) files,
plus the baked 'm_Unicode' glyph table of Unity TextMeshPro FontAsset .asset
files, then reports every character used by the target strings that none of the
supplied fonts can render.  Pure Python 3.9+ standard library.

Severity model
  * Static TMP atlas / plain font files: missing glyphs are ERR -> exit 1.
  * TMP asset with a dynamic atlas (m_AtlasPopulationMode 1 or 2) or with a
    fallback font table: glyphs are added at runtime, so missing characters are
    reported as WARN and the exit code stays 0 unless --strict is given.
  * Unreadable / malformed / unsupported font (e.g. .woff2 needs brotli) -> exit 2.

Characters ignored: ASCII controls, space, NBSP, ideographic space, zero-width
and variation-selector code points, combining marks (after NFC normalisation),
rich-text tags and {placeholders}.  --also-upper additionally scans the
upper-cased text (for runtime .ToUpper() / <uppercase> buttons, e.g. Turkish İ).
"""

from __future__ import annotations

import argparse
import struct
import sys
import unicodedata
import zlib
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, resolve_input, emit_report, extract_placeholders, load_config,
    load_target_rows, pick, read_text_bom, run_main, strip_tags, __version__,
)

TOOL = "font_glyph_scanner"
_SFNT_VERSIONS = {0x00010000, 0x4F54544F, 0x74727565}  # 1.0, 'OTTO', 'true'
_SKIP_CPS = {0x20, 0xA0, 0x3000, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0xAD, 0x034F, 0x061C, 0x180E}


class FontInfo(NamedTuple):
    path: str
    kind: str            # ttf/otf, ttc, woff, tmp-asset
    glyphs: int
    dynamic: bool = False
    has_fallbacks: bool = False
    sub_fonts: int = 1


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


def _parse_sfnt_at(data: bytes, base: int, label: str) -> Set[int]:
    sfnt_ver, num_tables = _u(">IH", data, base, f"{label} sfnt header")
    if sfnt_ver not in _SFNT_VERSIONS:
        raise FontParseError(f"{label}: not a TrueType/OpenType font (sfnt version 0x{sfnt_ver:08X})")
    for i in range(num_tables):
        tag, _csum, offset, length = _u(">4sIII", data, base + 12 + i * 16, f"{label} table record")
        if tag == b"cmap":
            if offset + length > len(data):
                raise FontParseError(f"{label}: cmap table extends beyond end of file")
            return parse_cmap_table(data[offset:offset + length])
    raise FontParseError(f"{label}: no 'cmap' table found")


def parse_font_file(font_path: Path) -> Tuple[Set[int], FontInfo]:
    """Return (code points, info) for .ttf/.otf/.ttc/.woff; raise FontParseError when unreadable."""
    try:
        data = font_path.read_bytes()
    except FileNotFoundError:
        raise FontParseError(f"font file not found: {font_path}")
    except (IsADirectoryError, PermissionError) as exc:
        raise FontParseError(f"cannot read font {font_path}: {exc}")
    if len(data) < 12:
        raise FontParseError(f"{font_path}: file too small to be a font ({len(data)} bytes)")
    magic = data[:4]
    name = str(font_path)
    if magic == b"ttcf":
        _tag, _ver, num_fonts = _u(">4sIi", data, 0, "ttc header")
        if num_fonts <= 0 or num_fonts > 512:
            raise FontParseError(f"{font_path}: invalid TrueType Collection (numFonts={num_fonts})")
        cps: Set[int] = set()
        for i in range(num_fonts):
            off = _u(">I", data, 12 + i * 4, "ttc offset table")[0]
            cps |= _parse_sfnt_at(data, off, f"{font_path.name}[{i}]")
        return cps, FontInfo(name, "ttc", len(cps), sub_fonts=num_fonts)
    if magic == b"wOFF":
        _sig, _flavor, _length, num_tables = _u(">4sIIH", data, 0, "woff header")
        for i in range(num_tables):
            tag, offset, comp_len, orig_len, _csum = _u(">4sIIII", data, 44 + i * 20, "woff table record")
            if tag == b"cmap":
                blob = data[offset:offset + comp_len]
                if comp_len < orig_len:
                    try:
                        blob = zlib.decompress(blob)
                    except zlib.error as exc:
                        raise FontParseError(f"{font_path}: cmap table zlib error: {exc}")
                cps = parse_cmap_table(blob)
                return cps, FontInfo(name, "woff", len(cps))
        raise FontParseError(f"{font_path}: no 'cmap' table in WOFF")
    if magic == b"wOF2":
        raise FontParseError(f"{font_path}: WOFF2 needs brotli decoding; convert to .ttf/.woff first")
    cps = _parse_sfnt_at(data, 0, font_path.name)
    return cps, FontInfo(name, "ttf/otf", len(cps))


# --------------------------------------------------------------------------- #
# Unity TextMeshPro FontAsset (.asset)
# --------------------------------------------------------------------------- #

def parse_tmp_asset(asset_path: Path) -> Tuple[Set[int], FontInfo]:
    import re
    txt = read_text_bom(asset_path)
    unicodes = {int(m) for m in re.findall(r"\bm_Unicode:\s*(\d+)", txt)}
    if not unicodes:
        legacy = {int(m) for m in re.findall(r"^\s*-\s*id:\s*(\d+)\s*$", txt, re.MULTILINE)} if "m_glyphInfoList" in txt else set()
        unicodes = legacy
    mode = re.search(r"\bm_AtlasPopulationMode:\s*(\d+)", txt)
    dynamic = bool(mode and mode.group(1) in ("1", "2"))
    has_fb = bool(re.search(r"m_FallbackFontAssetTable:\s*\r?\n\s*-\s*\{fileID:\s*-?\d+", txt))
    if not unicodes and not dynamic:
        raise FontParseError(f"{asset_path}: no 'm_Unicode' character table found; is this a text-serialized TMP FontAsset?")
    return unicodes, FontInfo(str(asset_path), "tmp-asset", len(unicodes), dynamic, has_fb)


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
    ap = argparse.ArgumentParser(prog=TOOL, description="Scan localized strings for glyphs missing from TTF/OTF/TTC/WOFF fonts or Unity TMP FontAssets (exit 0 ok / 1 missing / 2 bad input)")
    add_input_argument(ap, "Localized JSON, CSV/TSV, PO, Unity .asset string table, or plain text file")
    ap.add_argument("--dst-field", default=None, help="Target text column (default: dst)")
    ap.add_argument("--font", action="append", required=True, help="Font file: .ttf, .otf, .ttc, .woff or Unity TMP FontAsset .asset (repeatable; coverage is the union)")
    ap.add_argument("--strict", action="store_true", help="Treat missing glyphs as ERR even for dynamic TMP atlases / fallback chains")
    ap.add_argument("--also-upper", action="store_true", help="Also scan the upper-cased text (runtime .ToUpper() / <uppercase> buttons)")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    cfg = load_config(Path(args.config)) if args.config else {}
    supported: Set[int] = set()
    infos: List[FontInfo] = []
    for fp_str in args.font:
        fp = Path(fp_str)
        if fp.suffix.lower() == ".asset":
            cps, info = parse_tmp_asset(fp)
        elif fp.suffix.lower() in (".ttf", ".otf", ".ttc", ".woff", ".woff2", ".otc"):
            cps, info = parse_font_file(fp)
        else:
            raise L10nError(f"unsupported font file type '{fp.suffix}': {fp} (use .ttf/.otf/.ttc/.woff or a TMP .asset)")
        supported |= cps
        infos.append(info)
    lenient = (not args.strict) and any(i.dynamic or i.has_fallbacks for i in infos)
    used = collect_target_chars(Path(args.input), pick(args.dst_field, cfg, "dst_field", "dst"), args.also_upper, pick(None, cfg, "placeholder_style", "auto"))
    missing = sorted(cp for cp in used if cp not in supported)
    exit_code = EXIT_FINDINGS if (missing and not lenient) else EXIT_OK
    level = "WARN" if lenient else "ERR"

    lines = ["Font Coverage Report:"]
    for i in infos:
        extra = f", {i.sub_fonts} sub-fonts" if i.kind == "ttc" else ""
        extra += f", dynamic={i.dynamic}, has_fallbacks={i.has_fallbacks}" if i.kind == "tmp-asset" else ""
        lines.append(f"  * {Path(i.path).name}: {i.glyphs} code points ({i.kind}{extra})")
    lines.append(f"  Unique target characters used: {len(used)}")
    lines.append(f"  Missing characters (tofu)     : {len(missing)}" + (" [WARN: dynamic atlas / fallbacks present; pass --strict to fail]" if lenient and missing else ""))
    limit = args.max_report if args.max_report is not None else len(missing)
    blocks: Dict[str, int] = {}
    for cp in missing:
        ch, key, n = used[cp]
        blocks[_block_name(ch)] = blocks.get(_block_name(ch), 0) + 1
    for cp in missing[:limit]:
        ch, key, n = used[cp]
        lines.append(f"  {level} U+{cp:04X} {ch!r} {unicodedata.name(ch, 'UNKNOWN')} x{n}, first seen in '{key}'")
    if len(missing) > limit:
        lines.append(f"  ... and {len(missing) - limit} more (raise --max-report or use --json).")
    if blocks:
        lines.append("  By script/block: " + ", ".join(f"{b}: {n}" for b, n in sorted(blocks.items())))
    lines.append(f"  Exit code: {exit_code}")
    payload = {
        "tool": TOOL, "version": __version__, "input": str(args.input),
        "fonts": [i._asdict() for i in infos], "lenient": lenient,
        "unique_chars": len(used), "summary": {"missing": len(missing), "severity": level},
        "missing": [{"codepoint": f"U+{cp:04X}", "char": used[cp][0], "name": unicodedata.name(used[cp][0], "UNKNOWN"),
                     "count": used[cp][2], "first_key": used[cp][1]} for cp in missing],
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
