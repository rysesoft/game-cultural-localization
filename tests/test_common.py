"""Unit tests for l10n_common: locales, placeholders, tags, loaders, glossary, width."""
from __future__ import annotations

import unittest
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import FIXTURES, TempDir, write_json, write_text  # noqa: E402

import l10n_common as lc  # noqa: E402


class LocaleTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(lc.normalize_locale("de"), ("de-DE", None))
        self.assertEqual(lc.normalize_locale("pt_BR"), ("pt-BR", None))
        self.assertEqual(lc.normalize_locale("ZH-tw"), ("zh-Hant", None))
        self.assertEqual(lc.normalize_locale("zh-HK"), ("zh-Hant", "hk"))
        self.assertEqual(lc.normalize_locale("zh"), ("zh-CN", None))
        self.assertEqual(lc.normalize_locale("en-US"), ("en", None))
        for loc in lc.CANONICAL_LOCALES:
            self.assertEqual(lc.normalize_locale(loc)[0], loc)

    def test_unknown_and_ambiguous(self):
        with self.assertRaises(lc.L10nError) as cm:
            lc.normalize_locale("xx-XX")
        self.assertIn("supported", str(cm.exception))
        with self.assertRaises(lc.L10nError):
            lc.normalize_locale("pt")
        with self.assertRaises(lc.L10nError):
            lc.normalize_locale("")


class PlaceholderTests(unittest.TestCase):
    def test_printf_no_false_positive_on_percent_words(self):
        for s in ("100% fertig", "50% de dégâts", "20% sicher", "Bonus 5% x", "5%-10%", "100 % des dégâts"):
            self.assertEqual(lc.extract_placeholders(s).printf, (), s)

    def test_printf_real_tokens(self):
        ps = lc.extract_placeholders("%c %ld %@ %1$s %.2f %-5d %s %%")
        self.assertEqual(ps.printf, ("%c", "%ld", "%@", "%1$s", "%.2f", "%-5d", "%s"))

    def test_printf_order_matters_unless_positional(self):
        a = lc.extract_placeholders("%s has %d", "printf")
        b = lc.extract_placeholders("%d %s", "printf")
        self.assertTrue(lc.compare_placeholders(a, b))
        a = lc.extract_placeholders("%1$s has %2$d", "printf")
        b = lc.extract_placeholders("%2$d %1$s", "printf")
        self.assertEqual(lc.compare_placeholders(a, b), [])

    def test_unity_smart_strings_and_escape(self):
        ps = lc.extract_placeholders("{{literal}} {0:plural:item|items} {name:>10} {1,-10}", "unity")
        self.assertEqual(ps.top, ("0", "name", "1"))
        nested = lc.extract_placeholders("{0:plural:one item|{} items}", "unity")
        self.assertEqual(nested.top, ("0",))
        self.assertEqual(lc.compare_placeholders(nested, lc.extract_placeholders("{0:plural:ein Ding|{} Dinge}", "unity")), [])

    def test_icu_plural_nested(self):
        src = lc.extract_placeholders("{count, plural, one {# item from {place}} other {# items from {place}}}", "icu")
        self.assertEqual(src.top, ("count",))
        self.assertEqual(src.nested, ("place",))
        dst = lc.extract_placeholders("{count, plural, one {# Ding aus {place}} few {# Dinge aus {place}} other {# Dinge aus {place}}}", "icu")
        self.assertEqual(lc.compare_placeholders(src, dst), [])
        bad = lc.extract_placeholders("{count, plural, one {# Ding} other {# Dinge}}", "icu")
        self.assertTrue(lc.compare_placeholders(src, bad))
        quoted = lc.extract_placeholders("'{'literal'}' {n}", "icu")
        self.assertEqual(quoted.top, ("n",))

    def test_unreal_backtick_escape(self):
        ps = lc.extract_placeholders("You have {Count} {Count}|plural(one=item,other=items) and a literal " + chr(96) + "{brace}", "unreal")
        self.assertEqual(ps.top, ("Count", "Count"))

    def test_godot_and_python(self):
        self.assertEqual(lc.extract_placeholders("%s got %d {name}", "godot").printf, ("%s", "%d"))
        self.assertEqual(lc.extract_placeholders("%(name)s has %(n)d", "python").printf, ("%(name)s", "%(n)d"))

    def test_extra_regex(self):
        import re
        ps = lc.extract_placeholders("Hello $NAME$ and [ITEM]", extra_regex=re.compile(r"\$\w+\$|\[[A-Z_]+\]"))
        self.assertEqual(ps.top, ("$NAME$", "[ITEM]"))

    def test_unknown_style(self):
        with self.assertRaises(lc.L10nError):
            lc.extract_placeholders("x", "nope")


class TagTests(unittest.TestCase):
    def test_full_tmp_tag_set(self):
        text = ("<sprite=3><sprite name=\"x\"><link=\"id\">a</link><br><mark=#ffff00aa>b</mark><font=\"F\">c</font>"
                "<align=center>d</align><size=20>e</size><color=red>f</color><style=X>g</style><b>h</b><i>i</i><u>j</u><s>k</s>"
                "<nobr>l</nobr><sup>m</sup><sub>n</sub><voffset=1em>o</voffset><cspace=1>p</cspace><indent=5%>q</indent>"
                "<line-height=120%>r</line-height><alpha=#80><gradient=\"g\">s</gradient><#ff0000>t</color>")
        names = {t.name for t in lc.extract_tags(text)}
        for n in ("sprite", "link", "br", "mark", "font", "align", "size", "color", "style", "b", "i", "u", "s", "nobr",
                  "sup", "sub", "voffset", "cspace", "indent", "line-height", "alpha", "gradient"):
            self.assertIn(n, names)

    def test_reversed_and_unclosed(self):
        src = lc.extract_tags("<b>Warning</b>")
        self.assertTrue(lc.compare_tags(src, lc.extract_tags("</b>Warnung<b>")))
        self.assertTrue(lc.compare_tags(src, lc.extract_tags("<b>Warnung")))
        self.assertEqual(lc.compare_tags(src, lc.extract_tags("<B>Warnung</B>")), [])
        self.assertTrue(lc.tag_structure_error(lc.extract_tags("<b><i>x</b></i>")))

    def test_color_equivalence(self):
        self.assertEqual(lc.norm_tag("<color=red>"), lc.norm_tag("<color = \"#FF0000\">"))
        self.assertEqual(lc.norm_tag("<color=#ff0000ff>"), "<color=#ff0000>")
        self.assertEqual(lc.compare_tags(lc.extract_tags("<color=red>x</color>"), lc.extract_tags("<#ff0000>y</color>")), [])

    def test_bbcode_and_styles(self):
        tags = lc.extract_tags("[b]x[/b] [color=red]y[/color] [E] Interact", "bbcode")
        self.assertEqual([t.name for t in tags], ["b", "b", "color", "color"])
        self.assertEqual(lc.extract_tags("<custom>x</custom>", "tmp"), [])
        self.assertEqual(len(lc.extract_tags("<custom>x</custom>", "auto")), 2)
        self.assertEqual(lc.strip_tags("<b>OK</b><sprite=3>[b]x[/b]"), "OKx")


class WidthTests(unittest.TestCase):
    def test_widths(self):
        self.assertEqual(lc.visual_width("Café"), 4.0)
        self.assertEqual(lc.visual_width("Cafe\u0301"), 4.0)
        self.assertEqual(lc.visual_width("Ok\u200bOk"), 4.0)
        self.assertEqual(lc.visual_width("<sprite=3>OK"), 2.0)
        self.assertEqual(lc.visual_width("セーブ", cell=2.0), 6.0)
        self.assertEqual(lc.visual_width("…", ambiguous_wide=True, cell=2.0), 2.0)
        self.assertEqual(lc.visual_width("…"), 1.0)
        self.assertEqual(lc.visual_width("a\nabc"), 3.0)
        self.assertEqual(lc.line_count("a\r\nb"), 2)


class PoTests(unittest.TestCase):
    def test_po_parse(self):
        rows = lc.parse_po((FIXTURES / "strings.po").read_text(encoding="utf-8"))
        keys = [r.key for r in rows]
        self.assertEqual(keys, ["UI|Save", "You have {0} coins", "Long text", "Fuzzy one", "%d item|[0]", "%d item|[1]", 'He said "hi"'])
        by = {r.key: r for r in rows}
        self.assertEqual(by["Long text"].dst, "Zeile eins Zeile zwei")
        self.assertTrue(by["Fuzzy one"].meta["fuzzy"])
        self.assertEqual(by["UI|Save"].meta["msgctxt"], "UI")
        self.assertEqual(by["%d item|[1]"].src, "%d items")
        self.assertEqual(by["%d item|[1]"].meta["plural_nforms"], 2)
        self.assertEqual(by['He said "hi"'].dst, 'Er sagte "hallo"')

    def test_po_crlf_same(self):
        a = lc.parse_po((FIXTURES / "strings.po").read_text(encoding="utf-8"))
        b = lc.parse_po((FIXTURES / "strings_crlf.po").read_text(encoding="utf-8"))
        self.assertEqual(a, b)

    def test_po_unicode_escapes(self):
        rows = lc.parse_po('msgid "a"\nmsgstr "\\u00e9\\t\\101"\n')
        self.assertEqual(rows[0].dst, "é\tA")


class LoaderTests(unittest.TestCase):
    def test_bom_json_and_csv(self):
        rows = lc.load_table(FIXTURES / "tech_bom.json")
        self.assertTrue(rows)
        rows = lc.load_table(FIXTURES / "tech_bom.csv")
        self.assertTrue(rows)

    def test_csv_sniff_semicolon_and_multiline(self):
        rows = lc.load_table(FIXTURES / "semicolon.csv")
        self.assertEqual(rows[0].src, "You have {0} coins")
        rows = lc.load_table(FIXTURES / "multiline.csv")
        self.assertIn("\n", rows[0].src)

    def test_missing_columns(self):
        with self.assertRaises(lc.L10nError) as cm:
            lc.load_table(FIXTURES / "cols_target.csv", "source", "target")
        self.assertIn("available columns", str(cm.exception))
        rows = lc.load_table(FIXTURES / "cols_target.csv", "source", "target", target_only=True)
        self.assertTrue(rows)

    def test_json_shapes(self):
        rows = lc.load_table(FIXTURES / "kvmap.json")
        self.assertEqual({r.key: r.dst for r in rows}["SAVE"], "Speichern")
        with self.assertRaises(lc.L10nError):
            lc.load_table(FIXTURES / "list_of_str.json")
        with self.assertRaises(lc.L10nError):
            lc.load_table(FIXTURES / "empty.json")
        with self.assertRaises(lc.L10nError):
            lc.load_table(FIXTURES / "does_not_exist.json")
        with self.assertRaises(lc.L10nError):
            lc.load_table(FIXTURES / "tech.xlsx")

    def test_unity_yaml(self):
        rows = lc.load_table(FIXTURES / "UI_de-DE.asset")
        self.assertEqual([(r.key, r.dst) for r in rows], [("1001", "Speichern"), ("1002", "Du hast {0} Münzen")])
        with TempDir() as td:
            shared = write_text(td / "Shared.asset", "MonoBehaviour:\n  m_Entries:\n  - m_Id: 1001\n    m_Key: SAVE\n  - m_Id: 1002\n    m_Key: COINS\n")
            src = write_text(td / "UI_en.asset", "MonoBehaviour:\n  m_LocaleId:\n    m_Code: en\n  m_TableData:\n  - m_Id: 1001\n    m_Localized: Save\n  - m_Id: 1002\n    m_Localized: \"You have {0} coins\"\n  - m_Id: 1003\n    m_Localized: |-\n      Line one\n      Line two\n")
            rows = lc.load_table(FIXTURES / "UI_de-DE.asset", src_input=src, shared_table=shared)
            self.assertEqual(rows[0].key, "SAVE")
            self.assertEqual(rows[1].src, "You have {0} coins")
            data = lc.parse_unity_yaml(src.read_text(encoding="utf-8"))
            self.assertEqual(data["entries"][2]["text"], "Line one\nLine two")
            with self.assertRaises(lc.L10nError):
                lc.load_table(shared)


class GlossaryTests(unittest.TestCase):
    def test_wide_layout(self):
        with TempDir() as td:
            g = write_text(td / "g.csv", "term_en,de-DE,fr,notes\nReactor,Reaktor,réacteur,\"forbidden: Reaktion; Kernreaktor\"\nContract,Auftrag|Vertrag,,\n")
            terms = lc.load_glossary(g, "de-DE")
            self.assertEqual(len(terms), 2)
            self.assertEqual(lc.glossary_violations("Build a reactor", "Bau einen Reaktor", terms), [])
            self.assertEqual(lc.glossary_violations("Build a reactor", "Bau einen Reaktorkern", terms), [])
            self.assertTrue(lc.glossary_violations("Build a reactor", "Bau eine Kernreaktion", terms))
            self.assertEqual(lc.glossary_violations("New contract", "Neuer Vertrag", terms), [])
            self.assertEqual(lc.load_glossary(g, "fr")[0].targets, ("réacteur",))
            with self.assertRaises(lc.L10nError):
                lc.load_glossary(g, "ja-JP")

    def test_long_layout(self):
        with TempDir() as td:
            g = write_text(td / "g.csv", "source,target,locale\nReactor,Reaktor,de-DE\nReactor,re:r[ée]acteur,fr\n")
            self.assertEqual(len(lc.load_glossary(g, "de-DE")), 1)
            fr = lc.load_glossary(g, "fr")
            self.assertEqual(lc.glossary_violations("Reactor", "le réacteur", fr), [])
            bad = write_text(td / "bad.csv", "a,b\n1,2\n")
            with self.assertRaises(lc.L10nError):
                lc.load_glossary(bad, "fr")


class ConfigTests(unittest.TestCase):
    def test_config(self):
        with TempDir() as td:
            cfg = write_json(td / "l10n.config.json", {"locales": ["de-DE"], "dst_field": "de", "placeholder_style": "unity", "glossary": "g.csv", "_comment": "x"})
            data = lc.load_config(cfg)
            self.assertEqual(data["dst_field"], "de")
            self.assertTrue(Path(data["glossary"]).is_absolute())
            self.assertEqual(lc.pick(None, data, "dst_field", "dst"), "de")
            self.assertEqual(lc.pick("x", data, "dst_field", "dst"), "x")
            bad = write_json(td / "bad.json", {"unknown_key": 1})
            with self.assertRaises(lc.L10nError):
                lc.load_config(bad)
            bad2 = write_json(td / "bad2.json", {"fail_on_warn": "yes"})
            with self.assertRaises(lc.L10nError):
                lc.load_config(bad2)


if __name__ == "__main__":
    unittest.main()