"""Tests for font_glyph_scanner.py with synthetic TTF / TTC / WOFF fonts and TMP assets."""

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


def sfnt_tables(tables) -> bytes:
    """sfnt with the given tables (tag -> bytes), offsets file-absolute and 4-byte aligned."""
    tags = sorted(tables)
    head = struct.pack(">IHHHH", 0x00010000, len(tags), 16, 0, 0)
    off = 12 + 16 * len(tags)
    recs, body = b"", b""
    for tag in tags:
        data = tables[tag]
        recs += struct.pack(">4sIII", tag, 0, off + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    return head + recs + body


def metric_font(advances, upm: int = 1000, short_hmtx: bool = False) -> bytes:
    """TTF mapping each code point of advances (cp -> advance in font units) to its own glyph, with head, hhea and hmtx.

    short_hmtx keeps a single long metric, so every glyph takes the advance of glyph 0 (upm / 2).
    """
    cps = sorted(advances)
    groups = b"".join(struct.pack(">III", cp, cp, i + 1) for i, cp in enumerate(cps))
    sub = struct.pack(">HHIII", 12, 0, 16 + len(groups), 0, len(cps)) + groups
    head = b"\0" * 18 + struct.pack(">H", upm) + b"\0" * 34
    n_metrics = 1 if short_hmtx else len(cps) + 1
    hhea = b"\0" * 34 + struct.pack(">H", n_metrics)
    hmtx = struct.pack(">Hh", upm // 2, 0)
    hmtx += b"".join(struct.pack(">Hh", advances[cp], 0) for cp in cps) if not short_hmtx else struct.pack(f">{len(cps)}h", *([0] * len(cps)))
    return sfnt_tables({b"cmap": cmap_table([(3, 10, sub)]), b"head": head, b"hhea": hhea, b"hmtx": hmtx})


def tmp_asset(name: str, advances, point_size: float = 100, mode: int = 0, multi: int = 0, source_guid: str = "", fallbacks=()) -> str:
    """Minimal text-serialized TMP FontAsset (material before it, atlas texture after it, as Unity writes them).

    advances maps code point -> m_HorizontalAdvance in points at point_size.
    """
    cps = sorted(advances)
    glyphs = "".join(
        f"\n  - m_Index: {i + 1}\n    m_Metrics:\n      m_Width: 10\n      m_Height: 10\n      m_HorizontalBearingX: 0\n"
        f"      m_HorizontalBearingY: 10\n      m_HorizontalAdvance: {advances[cp]}\n    m_GlyphRect:\n      m_X: 0\n      m_Y: 0\n"
        f"      m_Width: 10\n      m_Height: 10\n    m_Scale: 1\n    m_AtlasIndex: 0\n    m_ClassDefinitionType: 0" for i, cp in enumerate(cps)) or " []"
    chars = "".join(f"\n  - m_ElementType: 1\n    m_Unicode: {cp}\n    m_GlyphIndex: {i + 1}\n    m_Scale: 1" for i, cp in enumerate(cps)) or " []"
    fb = "".join(f"\n  - {{fileID: 11400000, guid: {g}, type: 2}}" for g in fallbacks) or " []"
    src = f"{{fileID: 12800000, guid: {source_guid}, type: 3}}" if source_guid else "{fileID: 0}"
    return (
        "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
        "--- !u!21 &2100000\nMaterial:\n  m_Name: " + name + " Material\n  m_Unicode: 9999\n"
        "--- !u!114 &11400000\nMonoBehaviour:\n  m_Name: " + name + "\n  m_Version: 1.1.0\n"
        f"  m_SourceFontFileGUID: {source_guid}\n  m_SourceFontFile_EditorRef: {src}\n"
        f"  m_SourceFontFile: {src if mode else '{fileID: 0}'}\n  m_AtlasPopulationMode: {mode}\n"
        f"  m_FaceInfo:\n    m_FaceIndex: 0\n    m_PointSize: {point_size}\n    m_Scale: 1\n    m_UnitsPerEM: 1000\n"
        f"  m_GlyphTable:{glyphs}\n  m_CharacterTable:{chars}\n  m_AtlasTextures:\n  - {{fileID: 2800000}}\n"
        f"  m_IsMultiAtlasTexturesEnabled: {multi}\n  fallbackFontAssets: []\n  m_FallbackFontAssetTable:{fb}\n"
        f"  m_CreationSettings:\n    sourceFontFileGUID: {source_guid}\n    pointSize: {point_size}\n"
        "--- !u!28 &2800000\nTexture2D:\n  m_Name: " + name + " Atlas\n  image data: 4\n  _typelessdata: 00000000\n"
    )


def guid(n: int) -> str:
    return f"{n:032x}"


G_LATIN, G_CYR, G_CJKS, G_CJKD, G_TTF, G_MULTI = (guid(n) for n in range(1, 7))
LATIN = {**{cp: 50 for cp in range(0x21, 0x7F)}, 0xAB: 50, 0xBB: 50, 0xE9: 50}


def put(path: Path, content, file_guid: str) -> Path:
    """Write a project file and its .meta with the given GUID."""
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    write_text(path.with_name(path.name + ".meta"), f"fileFormatVersion: 2\nguid: {file_guid}\nNativeFormatImporter:\n  mainObjectFileID: 11400000\n")
    return path


def unity_project(td: Path) -> Path:
    """Synthetic Unity project, a Latin primary with a Cyrillic fallback (which points back, a cycle), a static CJK atlas
    whose own fallback is a dynamic CJK atlas built from cjk.ttf. Returns the fonts folder."""
    (td / "Game" / "ProjectSettings").mkdir(parents=True)
    fonts = td / "Game" / "Assets" / "Fonts"
    fonts.mkdir(parents=True)
    put(fonts / "Latin SDF.asset", tmp_asset("Latin SDF", LATIN, fallbacks=[G_CYR]), G_LATIN)
    put(fonts / "Cyr SDF.asset", tmp_asset("Cyr SDF", {ord(c): 55 for c in "Привет"}, fallbacks=[G_LATIN]), G_CYR)
    put(fonts / "CJK Static SDF.asset", tmp_asset("CJK Static SDF", {ord(c): 100 for c in "中文“”"}, fallbacks=[G_CJKD]), G_CJKS)
    put(fonts / "CJK Dyn SDF.asset", tmp_asset("CJK Dyn SDF", {0x2026: 100}, mode=1, multi=0, source_guid=G_TTF), G_CJKD)
    put(fonts / "cjk.ttf", metric_font({ord("中"): 1000, ord("文"): 1000, ord("字"): 1000, 0x2019: 1000, 0x2013: 540, 0x2026: 1000}), G_TTF)
    put(fonts / "CJK Multi SDF.asset", tmp_asset("CJK Multi SDF", {}, mode=1, multi=1, source_guid=G_TTF), G_MULTI)
    return fonts


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


def scan(*args: str):
    """Run the scanner with --json and return (exit code, parsed report or None, stderr)."""
    code, out, err = run_cli("font_glyph_scanner.py", *args, "--json")
    return code, (json.loads(out) if out.strip().startswith("{") else None), err


class MetricTests(unittest.TestCase):
    def test_cmap_glyph_id_prefers_unicode_subtables(self):
        table = cmap_table([(1, 0, cmap_format4([0x41])), (3, 1, cmap_format4([0x41, 0x42])), (3, 10, cmap_format12([0x1F3AE, 0x1F3AF]))])
        self.assertEqual(fgs.cmap_glyph_id(table, 0x42), 0x43)    # the format 4 test subtables map glyph = cp + 1
        self.assertEqual(fgs.cmap_glyph_id(table, 0x1F3AF), 2)    # format 12 group that starts at glyph 1
        self.assertEqual(fgs.cmap_glyph_id(table, 0x43), 0)
        self.assertEqual(fgs.cmap_glyph_id(b"\x00", 0x41), 0)

    def test_hmtx_advances(self):
        with TempDir() as td:
            f = td / "m.ttf"
            f.write_bytes(metric_font({0x2019: 1000, 0x41: 600}, upm=2000))
            font = fgs.load_font_file(f)
            self.assertEqual(font.cps, {0x41, 0x2019})
            self.assertAlmostEqual(font.advance_em(0x2019), 0.5)
            self.assertAlmostEqual(font.advance_em(0x41), 0.3)
            self.assertIsNone(font.advance_em(0x42))
            f.write_bytes(metric_font({0x41: 600}, short_hmtx=True))
            self.assertAlmostEqual(fgs.load_font_file(f).advance_em(0x41), 0.5)   # past numberOfHMetrics the last advance repeats
            f.write_bytes(sfnt(cmap_table([(3, 1, cmap_format4([0x41]))])))
            self.assertIsNone(fgs.load_font_file(f).advance_em(0x41))             # no hmtx, coverage only

    def test_read_tmp_asset(self):
        with TempDir() as td:
            p = write_text(td / "a.asset", tmp_asset("A", {0x41: 25, 0x2026: 50}, point_size=50, mode=1, multi=1, source_guid=G_TTF, fallbacks=[G_CYR]))
            d = fgs.read_tmp_asset(p)
            self.assertEqual(d.unicodes, {0x41, 0x2026})   # the m_Unicode line of the material document is not part of the table
            self.assertEqual((d.mode, d.multi_atlas, d.point_size), (1, True, 50.0))
            self.assertEqual(d.glyph_advance[d.char_glyph[0x2026][0]], 50.0)
            self.assertEqual(d.source_guids, (G_TTF,))
            self.assertEqual(d.fallbacks, ((11400000, G_CYR),))
            _cps, info = fgs.parse_tmp_asset(p)
            self.assertTrue(info.dynamic and info.has_fallbacks)
            self.assertFalse(fgs.read_tmp_asset(write_text(td / "b.asset", tmp_asset("B", {0x41: 25}))).fallbacks)


class ChainTests(unittest.TestCase):
    def test_search_order_follows_fallback_tables_once(self):
        with TempDir() as td:
            fonts = unity_project(td)
            chain = fgs.FontChain()
            order = chain.search_order([chain.load(fonts / n) for n in ("Latin SDF.asset", "Cyr SDF.asset", "CJK Static SDF.asset")])
            self.assertEqual([e.font.path.name for e in order], ["Latin SDF.asset", "Cyr SDF.asset", "CJK Static SDF.asset", "CJK Dyn SDF.asset"])
            self.assertEqual([e.parent.path.name if e.parent else None for e in order], [None, "Latin SDF.asset", None, "CJK Static SDF.asset"])
            self.assertEqual([e.depth for e in order], [0, 1, 0, 1])
            dyn = order[3].font
            self.assertTrue(dyn.info.coverage_known)
            self.assertEqual(Path(dyn.info.source_font).name, "cjk.ttf")
            self.assertIn(ord("字"), dyn.cps)                    # a dynamic atlas covers its source font
            self.assertNotIn(ord("字"), order[2].font.cps)       # a static atlas only its character table
            self.assertAlmostEqual(dyn.advance(0x2026), 1.0)     # from the asset's glyph table
            self.assertAlmostEqual(dyn.advance(0x2013), 0.54)    # from the source font
            result = fgs.resolve_chars(order, {ord("L"), 0x2019, 0x2013, ord("中")}, True)
            self.assertEqual(result.served[0x2019], 3)
            self.assertEqual([(cp, i) for cp, i, _em in result.full_width], [(0x2019, 3)])

    def test_cli_reports_the_serving_font_and_full_width_fallbacks(self):
        with TempDir() as td:
            fonts = unity_project(td)
            chain = ["--font", str(fonts / "Latin SDF.asset"), "--font", str(fonts / "CJK Static SDF.asset")]
            src = write_json(td / "fr.json", [{"key": "a", "fr": "L’atelier… “ok” – 中 Привет «é»"}, {"key": "b", "fr": "字"}])
            code, data, err = scan("--input", str(src), "--dst-field", "fr", *chain)
            self.assertEqual(code, 1, err)
            self.assertFalse(data["lenient"])
            self.assertEqual((data["locale"], data["full_width_checked"]), ("fr", True))
            self.assertEqual(data["summary"]["missing"], 0)
            self.assertEqual(data["summary"]["full_width"], 4)
            self.assertEqual([m["codepoint"] for m in data["full_width"]], ["U+2019", "U+201C", "U+201D", "U+2026"])
            self.assertEqual({m["advance_em"] for m in data["full_width"]}, {1.0})
            by_cp = {c["codepoint"]: Path(c["font"]).name for c in data["chars"]}
            self.assertEqual(by_cp["U+004C"], "Latin SDF.asset")
            self.assertEqual(by_cp["U+041F"], "Cyr SDF.asset")
            self.assertEqual(by_cp["U+201C"], "CJK Static SDF.asset")
            self.assertEqual(by_cp["U+2019"], "CJK Dyn SDF.asset")
            self.assertEqual(by_cp["U+5B57"], "CJK Dyn SDF.asset")      # 字 only through the source font of the dynamic atlas
            self.assertEqual(by_cp["U+2013"], "CJK Dyn SDF.asset")      # served there at 0.54 em, so no finding
            self.assertEqual([f["fallback_of"] and Path(f["fallback_of"]).name for f in data["fonts"]],
                             [None, "Latin SDF.asset", None, "CJK Static SDF.asset"])
            self.assertEqual(sum(f["served"] for f in data["fonts"]), data["unique_chars"])
            for extra, want_code, want_wide in ((["--locale", "zh-CN"], 0, 0), (["--locale", "ja"], 0, 0),
                                                (["--locale", "zh-CN", "--full-width-check", "on"], 1, 4),
                                                (["--full-width-check", "off"], 0, 0), (["--full-width-em", "1.5"], 0, 0)):
                code, data, err = scan("--input", str(src), "--dst-field", "fr", *chain, *extra)
                self.assertEqual((code, len(data["full_width"])), (want_code, want_wide), extra)
            code, out, _ = run_cli("font_glyph_scanner.py", "--input", str(src), "--dst-field", "fr", *chain)
            self.assertIn("WIDE U+2019", out)
            self.assertIn("fallback of CJK Static SDF.asset", out)
            zh = write_json(td / "zh.json", [{"key": "a", "zh-CN": "中文…“”"}])
            code, data, err = scan("--input", str(zh), "--dst-field", "zh-CN", *chain)   # a locale named by --dst-field counts
            self.assertEqual((code, data["locale"], data["full_width_checked"]), (0, "zh-CN", False), err)
            self.assertEqual(scan("--input", str(src), "--dst-field", "fr", *chain, "--locale", "xx-YY")[0], 2)
            self.assertEqual(scan("--input", str(src), "--dst-field", "fr", *chain, "--full-width-em", "0")[0], 2)

    def test_missing_in_a_resolved_chain_fails_and_atlas_warnings_alone_do_not(self):
        with TempDir() as td:
            fonts = unity_project(td)
            chain = ["--font", str(fonts / "Latin SDF.asset"), "--font", str(fonts / "CJK Static SDF.asset")]
            code, data, err = scan("--input", str(write_json(td / "ok.json", [{"key": "a", "dst": "Hello"}])), *chain)
            self.assertEqual(code, 0, err)
            codes = [(Path(w["font"]).name, w["code"]) for w in data["warnings"]]
            self.assertEqual(codes, [("Latin SDF.asset", "static_atlas"), ("Cyr SDF.asset", "static_atlas"),
                                     ("CJK Static SDF.asset", "static_atlas"), ("CJK Dyn SDF.asset", "dynamic_single_atlas")])
            self.assertEqual(data["summary"]["warnings"], 4)
            code, data, err = scan("--input", str(write_json(td / "bad.json", [{"key": "a", "dst": "Hello ぁ"}])), *chain)
            self.assertEqual(code, 1, err)
            self.assertEqual((data["summary"]["missing"], data["summary"]["severity"]), (1, "ERR"))
            self.assertEqual(data["missing"][0], {"codepoint": "U+3041", "char": "ぁ", "name": "HIRAGANA LETTER SMALL A", "count": 1, "first_key": "a"})
            code, data, err = scan("--input", str(write_json(td / "zi.json", [{"key": "a", "dst": "字"}])), "--font", str(fonts / "CJK Multi SDF.asset"))
            self.assertEqual(code, 0, err)
            self.assertEqual(data["warnings"], [])                                 # dynamic with Multi Atlas Textures on

    def test_unresolved_links_are_lenient_unless_strict(self):
        with TempDir() as td:
            fonts = unity_project(td)
            lost = put(fonts / "Lost SDF.asset", tmp_asset("Lost SDF", LATIN, fallbacks=[guid(99)]), guid(7))
            nosrc = put(fonts / "NoSource SDF.asset", tmp_asset("NoSource SDF", {0x41: 50}, mode=1, multi=1, source_guid=guid(98)), guid(8))
            bad = write_json(td / "bad.json", [{"key": "a", "dst": "Hello ぁ"}])
            for font, want in ((lost, "unresolved_fallback"), (nosrc, "unresolved_source_font")):
                code, data, err = scan("--input", str(bad), "--font", str(font))
                self.assertEqual(code, 0, err)
                self.assertTrue(data["lenient"])
                self.assertEqual(data["summary"]["severity"], "WARN")
                self.assertIn(want, [w["code"] for w in data["warnings"]])
                self.assertFalse(data["fonts"][0]["coverage_known"])
                self.assertEqual(scan("--input", str(bad), "--font", str(font), "--strict")[0], 1)


class GateTests(unittest.TestCase):
    def test_phase3_counts_full_width_fallbacks(self):
        import orchestrator_stub as orch
        with TempDir() as td:
            fonts = unity_project(td)
            put(fonts / "Latin Full SDF.asset", tmp_asset("Latin Full SDF", {**LATIN, 0x2019: 25}, fallbacks=[G_CJKS]), guid(9))
            work = td / "work"
            work.mkdir()
            state = orch.PipelineState("fr", work, "en", "dst", "key", "auto", "auto")
            final = write_json(work / "final_batch_01.json", [{"key": "ui.open", "en": "The workshop is open", "fr": "L’atelier est ouvert"}])
            summary = orch.phase3_gate(state, [final], [fonts / "Latin SDF.asset", fonts / "CJK Static SDF.asset"])
            self.assertEqual((summary["missing_glyphs"], summary["full_width_fallbacks"]), (0, 1), state.log)
            self.assertFalse(summary["passed"])
            summary = orch.phase3_gate(state, [final], [fonts / "Latin Full SDF.asset"])   # the primary has ’, nothing falls back
            self.assertEqual(summary["full_width_fallbacks"], 0)
            self.assertTrue(summary["passed"], state.log)


if __name__ == "__main__":
    unittest.main()