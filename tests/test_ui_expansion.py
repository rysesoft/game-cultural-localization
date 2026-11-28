"""Tests for ui_expansion_checker.py."""

import json
import unittest

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import FIXTURES, TempDir, run_cli, write_json  # noqa: E402

import ui_expansion_checker as ui  # noqa: E402
from l10n_common import CANONICAL_LOCALES, Row  # noqa: E402


def check(src: str, dst: str, locale: str = "de-DE", **kw):
    opt = ui.CheckOptions(locale=locale, factor=ui.EXPANSION_FACTORS[locale], **kw)
    return ui.check_rows([Row("K", src, dst, {})], opt)


class ThresholdTests(unittest.TestCase):
    def test_audit_cases_are_flagged(self):
        self.assertEqual(check("ON", "EINGESCHALTET")[0].level, "HIGH")
        self.assertEqual(check("<b>OK</b>", "<color=#ff0000>BESTÄTIGEN</color>")[0].level, "HIGH")
        self.assertEqual(check("APPLY", "ÜBERNEHMEN")[0].level, "WARN")
        self.assertEqual(check("SETTINGS", "EINSTELLUNGEN")[0].level, "WARN")
        self.assertEqual(check("Crafting Station", "Werkstatt für Handwerk")[0].level, "WARN")

    def test_legitimate_expansion_is_quiet(self):
        self.assertEqual(check("ON", "EIN"), [])
        self.assertEqual(check("BUY", "KAUFEN"), [])
        self.assertEqual(check("Craft", "Fabbrica", "it-IT"), [])
        self.assertEqual(check("Confirm", "Onayla", "tr-TR"), [])
        self.assertEqual(check("Save", "Guardar", "es-ES"), [])
        self.assertEqual(check("This is a long tooltip describing the item.", "Dies ist ein langer Tooltip, der den Gegenstand beschreibt."), [])

    def test_every_locale_has_a_factor(self):
        for loc in CANONICAL_LOCALES:
            self.assertIn(loc, ui.EXPANSION_FACTORS)
        self.assertEqual(ui.EXPANSION_FACTORS["de-DE"], 1.35)
        self.assertEqual(ui.EXPANSION_FACTORS["fr"], 1.30)
        self.assertEqual(ui.EXPANSION_FACTORS["it-IT"], 1.25)
        self.assertEqual(ui.EXPANSION_FACTORS["pt-PT"], 1.30)
        self.assertEqual(ui.EXPANSION_FACTORS["tr-TR"], 1.25)

    def test_cjk_and_ambiguous(self):
        self.assertEqual(check("SAVE", "セーブ", "ja-JP"), [])
        risks = check("SAVE", "セーブする", "ja-JP")
        self.assertEqual(risks[0].level, "WARN")
        self.assertEqual(risks[0].dst_width, 9.0)
        self.assertEqual(check("Yes…", "はい…", "ja-JP", ambiguous_wide=True)[0].dst_width, 6.0) if check("Yes…", "はい…", "ja-JP", ambiguous_wide=True) else None
        wide = ui.check_rows([Row("K", "Hello…", "Hallo…", {})], ui.CheckOptions(locale="de-DE", factor=1.35, ambiguous_wide=True))
        self.assertEqual(wide, [])

    def test_budget_and_lines(self):
        r = ui.check_rows([Row("BTN", "OK", "OK", {"max_chars": 1})], ui.CheckOptions(locale="de-DE", factor=1.35))
        self.assertEqual(r[0].level, "HIGH")
        self.assertIn("budget", r[0].reason)
        r = ui.check_rows([Row("BTN", "OK", "OKAY", {})], ui.CheckOptions(locale="de-DE", factor=1.35, max_width=3))
        self.assertEqual(r[0].level, "HIGH")
        r = ui.check_rows([Row("BTN", "OK", "OKAY", {})], ui.CheckOptions(locale="de-DE", factor=1.35, width_table={"BTN": 3}))
        self.assertEqual(r[0].level, "HIGH")
        r = ui.check_rows([Row("K", "Confirm", "Bestätigen\nund weiter", {})], ui.CheckOptions(locale="de-DE", factor=1.35))
        self.assertEqual(r[0].level, "WARN")
        self.assertIn("lines", r[0].reason)
        r = ui.check_rows([Row("K", "", "Nur Ziel", {"max_chars": 4})], ui.CheckOptions(locale="de-DE", factor=1.35))
        self.assertEqual(r[0].level, "HIGH")

    def test_sorted_deterministic(self):
        rows = [Row(k, "ON", d, {}) for k, d in (("B", "EINGESCHALTET"), ("A", "EINGESCHALTET"), ("C", "AKTIVIERT"))]
        r = ui.check_rows(rows, ui.CheckOptions(locale="de-DE", factor=1.35))
        self.assertEqual([x.key for x in r], ["A", "B", "C"])


class CliTests(unittest.TestCase):
    def test_exit_codes(self):
        code, out, err = run_cli("ui_expansion_checker.py", "--input", str(FIXTURES / "ui.json"), "--locale", "de-DE")
        self.assertEqual(code, 0, err)
        self.assertIn("--fail-on-high not given", out)
        code, out, _ = run_cli("ui_expansion_checker.py", "--input", str(FIXTURES / "ui.json"), "--locale", "de-DE", "--fail-on-high")
        self.assertEqual(code, 1)
        self.assertIn("EINGESCHALTET", out)
        code, _, err = run_cli("ui_expansion_checker.py", "--input", str(FIXTURES / "ui.json"), "--locale", "xx")
        self.assertEqual(code, 2)
        code, _, err = run_cli("ui_expansion_checker.py", "--input", str(FIXTURES / "ui.json"), "--locale", "de-DE", "--factor", "-1")
        self.assertEqual(code, 2)

    def test_json_and_config(self):
        with TempDir() as td:
            cfg = write_json(td / "cfg.json", {"expansion": {"de-DE": 3.0}, "max_width": {"ON": 5}})
            code, out, _ = run_cli("ui_expansion_checker.py", "--input", str(FIXTURES / "ui.json"), "--locale", "de-DE", "--config", str(cfg), "--json", "--fail-on-high")
            data = json.loads(out)
            self.assertEqual(data["factor"], 3.0)
            on = [r for r in data["risks"] if r["key"] == "ON"][0]
            self.assertIn("budget", on["reason"])
            self.assertEqual(code, 1)
            for k in ("tool", "version", "locale", "summary", "risks", "exit_code"):
                self.assertIn(k, data)

    def test_bom_po_asset_inputs(self):
        code, _, err = run_cli("ui_expansion_checker.py", "--input", str(FIXTURES / "tech_bom.json"), "--locale", "de-DE")
        self.assertEqual(code, 0, err)
        code, _, err = run_cli("ui_expansion_checker.py", "--input", str(FIXTURES / "strings.po"), "--locale", "de-DE")
        self.assertEqual(code, 0, err)
        code, _, err = run_cli("ui_expansion_checker.py", "--input", str(FIXTURES / "UI_de-DE.asset"), "--locale", "de-DE")
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
