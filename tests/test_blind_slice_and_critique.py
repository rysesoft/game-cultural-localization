"""Tests for make_blind_slice.py and validate_critique.py."""
from __future__ import annotations

import csv
import json
import unittest

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import FIXTURES, TempDir, run_cli, write_json, write_text  # noqa: E402

import validate_critique as vc  # noqa: E402


class BlindSliceTests(unittest.TestCase):
    def test_json_slice_has_no_source(self):
        with TempDir() as td:
            src = write_json(td / "pass1.json", [
                {"key": "A", "en": "Save", "de-DE": "Speichern", "category": "ui", "speaker": ""},
                {"key": "B", "en": "Patch her up, {0}!", "de-DE": "Flick sie zusammen, {0}!", "category": "dialog", "speaker": "A2"},
            ])
            out = td / "blind_de-DE_01.json"
            code, msg, err = run_cli("make_blind_slice.py", str(src), "--locale", "de-DE", "--out", str(out))
            self.assertEqual(code, 0, err)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(data["blind"])
            self.assertEqual(data["locale"], "de-DE")
            self.assertEqual([e["key"] for e in data["entries"]], ["A", "B"])
            self.assertEqual(data["entries"][1], {"key": "B", "category": "dialog", "speaker": "A2", "target": "Flick sie zusammen, {0}!"})
            self.assertNotIn("Save", out.read_text(encoding="utf-8"))
            self.assertNotIn('"en"', out.read_text(encoding="utf-8"))

    def test_refuses_source_as_context_and_leaks(self):
        with TempDir() as td:
            src = write_json(td / "p.json", [{"key": "A", "en": "Save game", "dst": "Spiel speichern", "note": "Save game"}])
            code, _, err = run_cli("make_blind_slice.py", str(src), "--locale", "de", "--out", str(td / "o.json"), "--context-cols", "en")
            self.assertEqual(code, 2)
            self.assertIn("source column", err)
            code, _, err = run_cli("make_blind_slice.py", str(src), "--locale", "de", "--out", str(td / "o.json"), "--context-cols", "note")
            self.assertEqual(code, 2)
            self.assertIn("contains source text", err)
            self.assertFalse((td / "o.json").exists())

    def test_csv_tsv_po_asset_inputs_and_csv_output(self):
        with TempDir() as td:
            out = td / "slice.csv"
            code, _, err = run_cli("make_blind_slice.py", str(FIXTURES / "strings.po"), "--locale", "de-DE", "--out", str(out))
            self.assertEqual(code, 0, err)
            with out.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows[0]["key"], "UI|Save")
            self.assertEqual(rows[0]["target"], "Speichern")
            self.assertNotIn("Save", [r["target"] for r in rows])
            code, _, err = run_cli("make_blind_slice.py", str(FIXTURES / "tech.tsv"), "--locale", "de-DE", "--out", str(td / "s2.json"), "--max-rows", "3")
            self.assertEqual(code, 0, err)
            self.assertEqual(len(json.loads((td / "s2.json").read_text(encoding="utf-8"))["entries"]), 3)
            code, _, err = run_cli("make_blind_slice.py", str(FIXTURES / "UI_de-DE.asset"), "--locale", "de-DE", "--out", str(td / "s3.json"))
            self.assertEqual(code, 0, err)
            multi = write_text(td / "multi.csv", "key,en,de-DE,fr\nA,Save,Speichern,Enregistrer\n")
            code, _, err = run_cli("make_blind_slice.py", str(multi), "--locale", "fr", "--out", str(td / "fr.json"))
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads((td / "fr.json").read_text(encoding="utf-8"))["entries"][0]["target"], "Enregistrer")
            code, _, err = run_cli("make_blind_slice.py", str(multi), "--locale", "ja-JP", "--out", str(td / "ja.json"))
            self.assertEqual(code, 2)


def critique(entries, total=2, flagged=None, critical=None, locale="de-DE"):
    flagged = len(entries) if flagged is None else flagged
    critical = sum(1 for e in entries if e.get("score", 5) <= 2) if critical is None else critical
    return {"locale": locale, "source_file": "blind.json", "entries": entries, "summary": {"total": total, "flagged": flagged, "critical": critical}}


class CritiqueValidatorTests(unittest.TestCase):
    SLICE = {"A": "Du hast {0} Münzen", "B": "<b>Speichern</b>"}

    def test_valid(self):
        data = critique([{"key": "A", "score": 3, "issue_type": "translationese", "reason": "stiff", "suggested": "{0} Münzen hast du"}])
        self.assertEqual(vc.validate(data, self.SLICE, "auto", "auto", "de-DE"), [])
        self.assertEqual(vc.validate(critique([]), self.SLICE, "auto", "auto", None), [])

    def test_invalid_cases(self):
        bad = critique([
            {"key": "A", "score": 5, "issue_type": "other", "reason": "", "suggested": "x"},
            {"key": "A", "score": 0, "issue_type": "nope", "reason": "r", "suggested": 1},
            {"key": "Z", "score": 2, "issue_type": "register", "reason": "r", "suggested": "Du hast Münzen"},
            {"key": "B", "score": 3, "issue_type": "ui_verb", "reason": "r", "suggested": "Speichern</b>"},
        ], total=2, flagged=9, critical=9)
        problems = vc.validate(bad, self.SLICE, "auto", "auto", "fr")
        joined = "\n".join(problems)
        for needle in ("score 5", "duplicate key", "integer 1-5", "issue_type", "'suggested' must be a string", "not present in the blind slice",
                       "tag parity", "summary.flagged", "summary.critical", "does not match expected"):
            self.assertIn(needle, joined)
        self.assertTrue(vc.validate({"locale": "de-DE"}, None, "auto", "auto", None))
        self.assertTrue(vc.validate([], None, "auto", "auto", None))

    def test_placeholder_parity_and_repair_exception(self):
        broken = critique([{"key": "A", "score": 3, "issue_type": "register", "reason": "r", "suggested": "Du hast Münzen"}])
        self.assertTrue(any("placeholder parity" in p for p in vc.validate(broken, self.SLICE, "auto", "auto", None)))
        repair = critique([{"key": "A", "score": 2, "issue_type": "placeholder_grammar", "reason": "r", "suggested": "Du hast {0} Münzen!"}])
        self.assertEqual(vc.validate(repair, self.SLICE, "auto", "auto", None), [])

    def test_cli(self):
        with TempDir() as td:
            slice_path = write_json(td / "blind.json", {"locale": "de-DE", "source_file": "x", "blind": True, "entries": [{"key": k, "target": v} for k, v in self.SLICE.items()]})
            good = write_json(td / "critique_de-DE_01.json", critique([{"key": "A", "score": 4, "issue_type": "register", "reason": "r", "suggested": "{0} Münzen hast du"}]))
            code, out, err = run_cli("validate_critique.py", str(good), "--slice", str(slice_path), "--locale", "de-DE")
            self.assertEqual(code, 0, err)
            bad = write_json(td / "bad.json", critique([{"key": "A", "score": 4, "issue_type": "register", "reason": "r", "suggested": "Münzen"}]))
            code, out, err = run_cli("validate_critique.py", str(bad), "--slice", str(slice_path), "--json")
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(out)["summary"]["problems"], 1)
            code, _, err = run_cli("validate_critique.py", str(td / "missing.json"))
            self.assertEqual(code, 2)
            csv_slice = write_text(td / "slice.csv", "key,target\nA,Du hast {0} Münzen\nB,<b>Speichern</b>\n")
            code, _, err = run_cli("validate_critique.py", str(good), "--slice", str(csv_slice))
            self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
