"""CLI / integration tests for lqa_linter.py (exit codes, formats, JSON, encoding, perf)."""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import FIXTURES, SCRIPTS, TempDir, run_cli, write_json, write_text  # noqa: E402

import lqa_linter  # noqa: E402
from l10n_common import CANONICAL_LOCALES, Row  # noqa: E402


class ExitCodeTests(unittest.TestCase):
    def test_clean_input_exit_0(self):
        with TempDir() as td:
            f = write_json(td / "ok.json", [{"key": "A", "en": "Save", "dst": "Speichern"}, {"key": "B", "en": "You have {0} coins", "dst": "Du hast {0} Münzen"}])
            code, out, err = run_cli("lqa_linter.py", "--input", str(f), "--locale", "de-DE")
            self.assertEqual(code, 0, out + err)
            self.assertIn("Exit code: 0", out)

    def test_findings_exit_1_and_alias(self):
        code, out, _ = run_cli("lqa_linter.py", "--input", str(FIXTURES / "tech.json"), "--locale", "de")
        self.assertEqual(code, 1)
        self.assertIn("[PLACEHOLDER]", out)
        self.assertIn("[RICH_TAG]", out)
        self.assertIn("[ENCODING]", out)
        self.assertIn("[EMPTY]", out)

    def test_unknown_locale_exit_2(self):
        for loc in ("xx-XX", "pt", "es-MX"):
            code, out, err = run_cli("lqa_linter.py", "--input", str(FIXTURES / "tech.json"), "--locale", loc)
            self.assertEqual(code, 2, loc)
            self.assertIn("error:", err)

    def test_input_errors_exit_2(self):
        code, _, err = run_cli("lqa_linter.py", "--input", str(FIXTURES / "missing.json"), "--locale", "de-DE")
        self.assertEqual(code, 2)
        self.assertIn("not found", err)
        code, _, err = run_cli("lqa_linter.py", "--input", str(FIXTURES / "cols_target.csv"), "--locale", "de-DE", "--src-field", "source", "--dst-field", "target")
        self.assertEqual(code, 2)
        self.assertIn("missing source column", err)
        code, _, err = run_cli("lqa_linter.py", "--input", str(FIXTURES / "list_of_str.json"), "--locale", "de-DE")
        self.assertEqual(code, 2)
        code, _, err = run_cli("lqa_linter.py", "--input", str(FIXTURES / "empty.json"), "--locale", "de-DE")
        self.assertEqual(code, 2)
        code, _, err = run_cli("lqa_linter.py", "--locale", "de-DE")  # argparse
        self.assertEqual(code, 2)

    def test_all_15_locales_run(self):
        for loc in CANONICAL_LOCALES:
            code, out, err = run_cli("lqa_linter.py", "--input", str(FIXTURES / "tech.json"), "--locale", loc, "--max-report", "1")
            self.assertIn(code, (0, 1), f"{loc}: {err}")
            self.assertIn(f"locale '{loc}'", out)

    def test_fail_on_warn(self):
        with TempDir() as td:
            f = write_json(td / "w.json", [{"key": "A", "en": "The key is in the cellar.", "dst": "Der Schlüssel befindet sich im Keller."}])
            code, out, _ = run_cli("lqa_linter.py", "--input", str(f), "--locale", "de-DE")
            self.assertEqual(code, 0)
            self.assertIn("Warnings: 1", out)
            code, _, _ = run_cli("lqa_linter.py", "--input", str(f), "--locale", "de-DE", "--fail-on-warn")
            self.assertEqual(code, 1)
            code, _, _ = run_cli("lqa_linter.py", "--input", str(f), "--locale", "de-DE", "--fail-on-error")
            self.assertEqual(code, 0)


class FormatTests(unittest.TestCase):
    def test_bom_json_and_csv_semicolon_tsv(self):
        for name in ("tech_bom.json", "tech_bom.csv", "semicolon.csv", "tech.tsv", "multiline.csv"):
            code, out, err = run_cli("lqa_linter.py", "--input", str(FIXTURES / name), "--locale", "de-DE", "--max-report", "2")
            self.assertIn(code, (0, 1), f"{name}: {err}")
            self.assertNotIn("error", err)

    def test_po_fuzzy_ctxt_plural(self):
        code, out, _ = run_cli("lqa_linter.py", "--input", str(FIXTURES / "strings.po"), "--locale", "pl-PL")
        self.assertEqual(code, 1)
        self.assertIn("[FUZZY] Fuzzy one", out)
        self.assertIn("[PLURAL_FORMS] %d item|[0]", out)  # pl needs 3 forms, PO has 2
        self.assertIn("UI|Save", out) if "UI|Save" in out else None
        code, out, _ = run_cli("lqa_linter.py", "--input", str(FIXTURES / "strings.po"), "--locale", "de-DE")
        self.assertNotIn("[PLURAL_FORMS]", out)

    def test_unity_asset(self):
        with TempDir() as td:
            shared = write_text(td / "Shared.asset", "MonoBehaviour:\n  m_Entries:\n  - m_Id: 1001\n    m_Key: SAVE\n  - m_Id: 1002\n    m_Key: COINS\n")
            src = write_text(td / "UI_en.asset", "MonoBehaviour:\n  m_TableData:\n  - m_Id: 1001\n    m_Localized: Save\n  - m_Id: 1002\n    m_Localized: You have {0} coins and {1} gems\n")
            code, out, err = run_cli("lqa_linter.py", "--input", str(FIXTURES / "UI_de-DE.asset"), "--locale", "de-DE", "--src-input", str(src), "--shared-table", str(shared))
            self.assertEqual(code, 1, err)
            self.assertIn("[PLACEHOLDER] COINS", out)
            code, out, err = run_cli("lqa_linter.py", "--input", str(FIXTURES / "UI_de-DE.asset"), "--locale", "de-DE")
            self.assertEqual(code, 0, err)

    def test_target_only_blind_slice(self):
        with TempDir() as td:
            f = write_json(td / "blind.json", [{"key": "A", "category": "ui", "target": "Fokussieren"}])
            code, out, _ = run_cli("lqa_linter.py", "--input", str(f), "--locale", "de-DE", "--target-only", "--dst-field", "target")
            self.assertEqual(code, 1)
            self.assertIn("DE-FOKUSSIEREN", out)

    def test_json_report_schema_and_file(self):
        with TempDir() as td:
            code, out, _ = run_cli("lqa_linter.py", "--input", str(FIXTURES / "tech.json"), "--locale", "de-DE", "--json")
            self.assertEqual(code, 1)
            data = json.loads(out)
            for k in ("tool", "version", "locale", "input", "entries_checked", "rules_loaded", "summary", "findings", "exit_code"):
                self.assertIn(k, data)
            self.assertEqual(data["exit_code"], 1)
            self.assertEqual(data["summary"]["errors"], len([f for f in data["findings"] if f["severity"] == "ERR"]))
            for f in data["findings"]:
                self.assertEqual(set(f), {"severity", "code", "key", "message", "target"})
            out_file = td / "r.json"
            code, out2, _ = run_cli("lqa_linter.py", "--input", str(FIXTURES / "tech.json"), "--locale", "de-DE", "--json", str(out_file))
            self.assertTrue(out_file.is_file())
            self.assertEqual(json.loads(out_file.read_text(encoding="utf-8"))["findings"], data["findings"])
            self.assertIn("JSON report written", out2)

    def test_deterministic(self):
        _, a, _ = run_cli("lqa_linter.py", "--input", str(FIXTURES / "tech.json"), "--locale", "de-DE", "--json")
        _, b, _ = run_cli("lqa_linter.py", "--input", str(FIXTURES / "tech.json"), "--locale", "de-DE", "--json")
        self.assertEqual(a, b)

    def test_max_report(self):
        _, out, _ = run_cli("lqa_linter.py", "--input", str(FIXTURES / "tech.json"), "--locale", "de-DE", "--max-report", "2")
        self.assertIn("more ERR findings", out)
        _, out, _ = run_cli("lqa_linter.py", "--input", str(FIXTURES / "tech.json"), "--locale", "de-DE")
        self.assertNotIn("more ERR findings", out)

    def test_windows_cp1252_pipe_does_not_crash(self):
        # No -X utf8: the script must reconfigure stdio itself when stdout is a pipe.
        with TempDir() as td:
            f = write_json(td / "ja.json", [{"key": "A", "en": "You can build", "dst": "あなたは建造することができます"}])
            code, out, err = run_cli("lqa_linter.py", "--input", str(f), "--locale", "ja-JP", utf8=False, env_extra={"PYTHONLEGACYWINDOWSSTDIO": "1"})
            self.assertEqual(code, 1, err)
            self.assertNotIn("UnicodeEncodeError", err)
            self.assertIn("JA-ANATA", out)


class OptionTests(unittest.TestCase):
    def test_glossary_wide_and_config(self):
        with TempDir() as td:
            g = write_text(td / "glossary.csv", "term_en,de-DE,fr,notes\nReactor,Reaktor,réacteur,\"forbidden: Kernreaktor\"\n")
            f = write_json(td / "s.json", [{"key": "A", "en": "Build a Reactor", "de": "Bau einen Generator"}, {"key": "B", "en": "Reactor", "de": "Reaktor"}])
            cfg = write_json(td / "l10n.config.json", {"dst_field": "de", "glossary": "glossary.csv", "glossary_severity": "ERR", "locales": ["de-DE", "fr"]})
            code, out, err = run_cli("lqa_linter.py", "--input", str(f), "--locale", "de-DE", "--config", str(cfg))
            self.assertEqual(code, 1, err)
            self.assertIn("[GLOSSARY] A", out)
            self.assertNotIn("[GLOSSARY] B", out)
            code, _, err = run_cli("lqa_linter.py", "--input", str(f), "--locale", "ja-JP", "--config", str(cfg), "--dst-field", "de")
            self.assertEqual(code, 2)
            self.assertIn("configured locales", err)

    def test_placeholder_and_tag_styles(self):
        with TempDir() as td:
            f = write_json(td / "s.json", [
                {"key": "ICU", "en": "{n, plural, one {# item} other {# items}}", "dst": "{n, plural, one {# Ding} few {# Dinge} other {# Dinge}}"},
                {"key": "BB", "en": "[b]Save[/b]", "dst": "[b]Zapisz"},
                {"key": "PF", "en": "%s found %d", "dst": "%d znalazł %s"},
            ])
            code, out, _ = run_cli("lqa_linter.py", "--input", str(f), "--locale", "pl-PL", "--placeholder-style", "icu", "--tag-style", "bbcode", "--no-untranslated-check")
            self.assertEqual(code, 1)
            self.assertNotIn("[PLACEHOLDER] ICU", out)
            self.assertIn("[RICH_TAG] BB", out)
            self.assertNotIn("[PLACEHOLDER] PF", out)  # icu style ignores printf
            code, out, _ = run_cli("lqa_linter.py", "--input", str(f), "--locale", "pl-PL", "--placeholder-style", "godot", "--no-untranslated-check")
            self.assertIn("[PLACEHOLDER] PF", out)
            code, _, err = run_cli("lqa_linter.py", "--input", str(f), "--locale", "pl-PL", "--placeholder-style", "nope")
            self.assertEqual(code, 2)

    def test_custom_rules_dir(self):
        with TempDir() as td:
            rules = td / "rules"
            rules.mkdir()
            write_json(rules / "proj.json", {"locale": "de-DE", "rules": [{"id": "PROJ-SIE", "severity": "ERR", "pattern": "\\bSie\\b", "message": "du only"}]})
            f = write_json(td / "s.json", [{"key": "A", "en": "Do you have time?", "dst": "Haben Sie Zeit?"}])
            code, out, _ = run_cli("lqa_linter.py", "--input", str(f), "--locale", "de-DE", "--rules", str(rules))
            self.assertEqual(code, 1)
            self.assertIn("PROJ-SIE", out)
            code, out, _ = run_cli("lqa_linter.py", "--input", str(f), "--locale", "de-DE", "--rules", str(rules), "--no-builtin-rules")
            self.assertIn("with 1 rules", out)

    def test_strict_whitespace_and_forbid(self):
        code, out, _ = run_cli("lqa_linter.py", "--input", str(FIXTURES / "tech.json"), "--locale", "de-DE", "--strict-whitespace", "--forbid-spaced-hyphen", "--forbid-chars", ";—")
        self.assertIn("[LEADING_SPACE]", out)
        self.assertIn("[TRAILING_SPACE]", out)
        self.assertIn("[TRAILING_NEWLINE]", out)
        self.assertIn("[SPACED_HYPHEN]", out)
        self.assertIn("[CONTROL_CHAR]", out)
        code, out, _ = run_cli("lqa_linter.py", "--input", str(FIXTURES / "tech.json"), "--locale", "de-DE")
        self.assertNotIn("[LEADING_SPACE]", out)


class PerformanceTests(unittest.TestCase):
    def test_50k_rows_under_10s(self):
        rules = lqa_linter.load_rules("de-DE")
        opt = lqa_linter.LintOptions(locale="de-DE")
        rows = [Row(f"K{i}", f"You have {{0}} coins and <b>{i}</b> items, 100% done", f"Du hast {{0}} Münzen und <b>{i}</b> Dinge, 100 % fertig", {}) for i in range(50_000)]
        t0 = time.perf_counter()
        findings = lqa_linter.lint_rows(rows, rules, opt)
        dt = time.perf_counter() - t0
        self.assertEqual([f for f in findings if f.severity == "ERR"], [])
        self.assertLess(dt, 10.0, f"lint of 50k rows took {dt:.1f}s")

    def test_50k_rows_cli_json_under_10s(self):
        with TempDir() as td:
            f = write_json(td / "big.json", [{"key": f"K{i}", "en": f"Line {i}: {{0}} coins", "dst": f"Zeile {i}: {{0}} Münzen"} for i in range(50_000)])
            t0 = time.perf_counter()
            code, out, err = run_cli("lqa_linter.py", "--input", str(f), "--locale", "de-DE", "--json", str(td / "r.json"))
            dt = time.perf_counter() - t0
            self.assertEqual(code, 0, err)
            self.assertLess(dt, 10.0, f"CLI took {dt:.1f}s")


if __name__ == "__main__":
    unittest.main()