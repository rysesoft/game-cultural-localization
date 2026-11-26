"""Tests for font_glyph_scanner.py with synthetic TTF / TTC / WOFF fonts and TMP assets."""
from __future__ import annotations

import json
import struct
import unittest
import zlib
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import FIXTURES, TempDir, run_cli, write_json, write_text  # noqa: E402

import font_glyph_scanner as fgs  # noqa: E402
from l10n_common import L10nError  # noqa: E402


def cmap_format4(cps):
    """Build a cmap table with one format-4 subtable mapping each code point to a non-zero glyph."""
    cps = sorted(c for c in cps if c < 0xFFFF)
    segs = []
    for cp in cps:
        if segs and segs[-1][1] == cp - 1:
            segs[-1][1] = cp
        else:
            segs.append([cp, cp])
    segs.append([0xFFFF, 0xFFFF])
    n = len(segs)
    ends = struct.pack(f">{n}H", *[e for _s, e in segs])
    starts = struct.pack(f">{n}H", *[s for s, _e in segs])
    deltas = struct.pack(f">{n}h", *([1] * n))  # glyph = cp + 1 (never 0)
    ranges = struct.pack(f">{n}H", *([0] * n))
    # format, length, language, segCountX2, searchRange, entrySelector, rangeShift (7 x uint16 = 14 bytes)
    body = struct.pack(">HHHHHHH", 4, 0, 0, n * 2, 0, 0, 0) + ends + b"\x00\x00" + starts + deltas + ranges
    body = body[:2] + struct.pack(">H", len(body)) + body[4:]
    return body


def cmap_format12(cps):
    cps = sorted(cps)
    groups = []
    for cp in cps:
        if groups and groups[-1][1] == cp - 1:
            groups[-1][1] = cp
        else:
            groups.append([cp, cp])
    body = b"".join(struct.pack(">III", s, e, 1) for s, e in groups)
    return struct.pack(">HHIII", 12, 0, 16 + len(body), 0, len(groups)) + body


def cmap_table(subtables):
    header = struct.pack(">HH", 0, len(subtables))
    off = 4 + 8 * len(subtables)
    recs = b""
    data = b""
    for pid, eid, sub in subtables:
        recs += struct.pack(">HHI", pid, eid, off + len(data))
        data += sub
    return header + recs + data


def sfnt(cmap: bytes, version: int = 0x00010000, base: int = 0) -> bytes:
    """Minimal sfnt with a single cmap table; table offsets are file-absolute (base = font offset inside a TTC)."""
    head = struct.pack(">IHHHH", version, 1, 16, 0, 0)
    rec = struct.pack(">4sIII", b"cmap", 0, base + 12 + 16, len(cmap))
    return head + rec + cmap


def ttc(cmaps):
    """TrueType Collection wrapping one sfnt per cmap table."""
    header = struct.pack(">4sIi", b"ttcf", 0x00010000, len(cmaps))
    off = 12 + 4 * len(cmaps)
    offsets = b""
    body = b""
    for cm in cmaps:
        base = off + len(body)
        offsets += struct.pack(">I", base)
        body += sfnt(cm, base=base)
    return header + offsets + body


def woff(cmap: bytes) -> bytes:
    comp = zlib.compress(cmap)
    header = struct.pack(">4sIIHHIHHIIIII", b"wOFF", 0x00010000, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0)
    rec = struct.pack(">4sIIII", b"cmap", 44 + 20, len(comp), len(cmap), 0)
    return header + rec + comp


class ParserTests(unittest.TestCase):
    def test_ttf_format4_and_12(self):
        with TempDir() as td:
            f = td / "a.ttf"
            f.write_bytes(sfnt(cmap_table([(3, 1, cmap_format4(range(0x20, 0x7F))), (3, 10, cmap_format12([0x1F3AE, 0x4E2D]))])))
            cps, info = fgs.parse_font_file(f)
            self.assertIn(ord("A"), cps)
            self.assertIn(0x1F3AE, cps)
            self.assertIn(0x4E2D, cps)
            self.assertNotIn(0x00E9, cps)
            self.assertEqual(info.kind, "ttf/otf")

    def test_ttc_merges_subfonts(self):
        with TempDir() as td:
            f = td / "c.ttc"
            a = cmap_table([(3, 1, cmap_format4([0x41, 0x42]))])
            b = cmap_table([(3, 1, cmap_format4([0x3042, 0x3044]))])
            f.write_bytes(ttc([a, b]))
            cps, info = fgs.parse_font_file(f)
            self.assertEqual(cps, {0x41, 0x42, 0x3042, 0x3044})
            self.assertEqual(info.kind, "ttc")
            self.assertEqual(info.sub_fonts, 2)

    def test_woff(self):
        with TempDir() as td:
            f = td / "w.woff"
            f.write_bytes(woff(cmap_table([(3, 1, cmap_format4([0x41]))])))
            cps, info = fgs.parse_font_file(f)
            self.assertEqual(cps, {0x41})
            self.assertEqual(info.kind, "woff")
            f2 = td / "w2.woff2"
            f2.write_bytes(b"wOF2" + b"\x00" * 40)
            with self.assertRaises(L10nError):
                fgs.parse_font_file(f2)

    def test_broken_fonts_raise_clean_errors(self):
        with self.assertRaises(L10nError) as cm:
            fgs.parse_font_file(FIXTURES / "fake.ttf")
        self.assertIn("not a TrueType", str(cm.exception))
        with TempDir() as td:
            f = td / "t.ttf"
            f.write_bytes(sfnt(cmap_table([(3, 1, cmap_format4([0x41]))]))[:40])
            with self.assertRaises(L10nError):
                fgs.parse_font_file(f)
            f.write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 8)
            with self.assertRaises(L10nError) as cm:
                fgs.parse_font_file(f)
            self.assertIn("cmap", str(cm.exception))
            with self.assertRaises(L10nError):
                fgs.parse_font_file(td / "missing.ttf")

    def test_tmp_assets(self):
        cps, info = fgs.parse_tmp_asset(FIXTURES / "Bebas SDF.asset")
        self.assertEqual(len(cps), 102)
        self.assertFalse(info.dynamic)
        cps, info = fgs.parse_tmp_asset(FIXTURES / "Bebas Dyn SDF.asset")
        self.assertTrue(info.dynamic)
        self.assertTrue(info.has_fallbacks)
        with self.assertRaises(L10nError):
            fgs.parse_tmp_asset(FIXTURES / "UI_de-DE.asset")

    def test_collect_chars_skips_tags_placeholders_zero_width(self):
        with TempDir() as td:
            f = write_json(td / "s.json", [{"key": "A", "dst": "<b>Ok</b> {itemName} \u200b\u00a0Café"}, {"key": "B", "dst": "Ok"}])
            chars = fgs.collect_target_chars(f, "dst")
            self.assertEqual(set(chars), {ord(c) for c in "OkCafé"})
            self.assertEqual(chars[ord("O")][2], 2)
            upper = fgs.collect_target_chars(write_json(td / "t.json", [{"key": "A", "dst": "iptal"}]), "dst", also_upper=True)
            self.assertIn(ord("I"), upper)


class CliTests(unittest.TestCase):
    def test_exit_codes(self):
        with TempDir() as td:
            font = td / "a.ttf"
            font.write_bytes(sfnt(cmap_table([(3, 1, cmap_format4(range(0x20, 0x7F)))])))
            ok = write_json(td / "ok.json", [{"key": "A", "dst": "Save game"}])
            bad = write_json(td / "bad.json", [{"key": "A", "dst": "Ğ Ş İ"}])
            code, out, err = run_cli("font_glyph_scanner.py", "--input", str(ok), "--font", str(font))
            self.assertEqual(code, 0, err)
            code, out, err = run_cli("font_glyph_scanner.py", "--input", str(bad), "--font", str(font), "--json")
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["summary"]["missing"], 3)
            self.assertEqual(data["missing"][0]["codepoint"], "U+011E")
            code, _, err = run_cli("font_glyph_scanner.py", "--input", str(bad), "--font", str(FIXTURES / "fake.ttf"))
            self.assertEqual(code, 2)
            self.assertIn("not a TrueType", err)
            code, _, err = run_cli("font_glyph_scanner.py", "--input", str(bad), "--font", str(td / "x.png"))
            self.assertEqual(code, 2)
            code, _, err = run_cli("font_glyph_scanner.py", "--input", str(td / "nope.json"), "--font", str(font))
            self.assertEqual(code, 2)

    def test_dynamic_tmp_is_warn_unless_strict(self):
        code, out, _ = run_cli("font_glyph_scanner.py", "--input", str(FIXTURES / "glyphs.json"), "--font", str(FIXTURES / "Bebas Dyn SDF.asset"), "--max-report", "1")
        self.assertEqual(code, 0)
        self.assertIn("WARN", out)
        code, _, _ = run_cli("font_glyph_scanner.py", "--input", str(FIXTURES / "glyphs.json"), "--font", str(FIXTURES / "Bebas Dyn SDF.asset"), "--strict")
        self.assertEqual(code, 1)
        code, _, _ = run_cli("font_glyph_scanner.py", "--input", str(FIXTURES / "glyphs.json"), "--font", str(FIXTURES / "Bebas SDF.asset"))
        self.assertEqual(code, 1)

    def test_real_windows_ttc_if_present(self):
        ttc_path = Path(r"C:\Windows\Fonts\msgothic.ttc")
        if not ttc_path.is_file():
            self.skipTest("msgothic.ttc not available")
        cps, info = fgs.parse_font_file(ttc_path)
        self.assertGreater(len(cps), 5000)
        self.assertIn(0x3042, cps)
        self.assertEqual(info.sub_fonts, 3)


if __name__ == "__main__":
    unittest.main()