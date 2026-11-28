"""P13: report_changes.py (B3.8 developer report, JSON + Markdown in the house punctuation style)."""

import json
import re
import unittest
from pathlib import Path
from typing import Any

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS, TempDir, run_cli, write_json, write_text  # noqa: E402

import report_changes as rcg  # noqa: E402
import text_style  # noqa: E402

NASTY = "Calque: English order; the mentor — sounds like a manual – rewrite."


def votes(key: str, tier: str, scores: list[int], issue: str = "translationese") -> list[dict[str, Any]]:
    fams = ("anthropic", "deepseek", "google")
    return [{"key": key, "tier": tier, "member": i, "family": fams[i], "model": f"m{i}", "score": s,
             "issue_type": issue if s < 5 else "none", "reason": NASTY if s < 5 else "", "suggested": ""} for i, s in enumerate(scores)]


def verdict(key: str, status: str, tier: str, score: int, vs: list[dict[str, Any]], ban: bool = False, calque: bool = False) -> dict[str, Any]:
    return {"key": key, "final_tier": tier, "score": score, "status": status, "votes": vs,
            "evidence": {"ban_hits": [{"rule": "TR-X", "severity": "WARN", "message": "m"}] if ban else [], "tm_neighbors": [],
                         "roundtrip": {"applied": calque, "calque_score": 0.95, "suspect": calque} if calque else {"applied": False}},
            "rationales": [v["reason"] for v in vs if v["tier"] == tier]}


VERDICTS = {
    "locale": "tr-TR", "source_file": "pass1_tr-TR_01.json", "langpack_version": "tr-TR-abc", "stats": {"lines": 5}, "halted": None, "notes": [],
    "verdicts": [
        verdict("OK", "pass", "J1", 5, votes("OK", "J1", [5, 5, 5])),
        verdict("LIGHT", "rewrite_light", "J1", 4, votes("LIGHT", "J1", [4, 5, 5])),
        verdict("CRIT", "critical", "J3", 2, votes("CRIT", "J1", [2, 5, 5], "ui_verb") + votes("CRIT", "J3", [2, 2, 3], "ui_verb"), ban=True),
        verdict("DLB", "rewrite", "deliberation", 3, votes("DLB", "J3", [5, 3, 2]) + votes("DLB", "deliberation", [3, 3, 5]), calque=True),
        verdict("UNR", "unresolved", "J3", 2, votes("UNR", "J3", [5, 3, 2])),
    ]}
REWRITES = {"lines": [
    {"key": "LIGHT", "en": "Open settings", "old": "Ayarları aç", "new": "Ayarlar", "valid": True},
    {"key": "CRIT", "en": "Save", "old": "Kaydetmek; şimdi", "new": "Kaydet", "valid": True},
    {"key": "DLB", "en": "Take your time, kid.", "old": "Zamanını al, çocuk.", "new": "Acele etme evlat.", "valid": True},
    {"key": "UNR", "en": "Hold the line | now", "old": "Hattı tut | şimdi", "new": "Hattı tut | şimdi", "valid": False},
]}


def make_pack(root: Path, measured: bool = True, calibrated: bool = True, secondary: Any = None) -> Path:
    pack = root / "tr-TR"
    pack.mkdir(parents=True)
    cal = {"gate": {"passed": True}, **({"secondary": {"passed": secondary}} if secondary is not None else {})}
    write_json(pack / "trust_card.json", {"locale": "tr-TR", "langpack_version": "tr-TR-abc", "trust_level": "measured" if measured else "estimated",
                                          "calibration": cal if calibrated else None})
    return pack


class UnitTests(unittest.TestCase):
    def test_confidence(self):
        v = {x["key"]: x for x in VERDICTS["verdicts"]}
        self.assertEqual(rcg.confidence(v["OK"], None), 0.9)
        self.assertEqual(rcg.confidence(v["LIGHT"], True), 0.8)                     # spread 1
        self.assertEqual(rcg.confidence(v["CRIT"], True), 0.65)                     # J3 0.70 - 0.10 + ban 0.05
        self.assertEqual(rcg.confidence(v["DLB"], True), 0.45)                      # 0.60 - 0.20 + calque 0.05
        self.assertEqual(rcg.confidence(v["UNR"], False), 0.0)                      # 0.30 - 0.30, halved
        self.assertTrue(all(0 <= rcg.confidence(x, None) <= 1 for x in v.values()))

    def test_trust_levels(self):
        with TempDir() as td:
            self.assertEqual(rcg.trust_level(td / "none"), ("rule_based", None))
            self.assertEqual(rcg.trust_level(make_pack(td / "a")), ("measured", "tr-TR-abc"))
            self.assertEqual(rcg.trust_level(make_pack(td / "b", calibrated=False))[0], "estimated")
            self.assertEqual(rcg.trust_level(make_pack(td / "c", measured=False))[0], "estimated")
            self.assertIsNone(rcg.secondary_passed(td / "a" / "tr-TR"))
            self.assertFalse(rcg.secondary_passed(make_pack(td / "d", secondary=False)))

    def test_failed_secondary_check_is_named(self):
        # a measured pack whose absolute scores missed the second check says so, the level itself stays measured
        with TempDir() as td:
            for sec, expect in ((False, False), (True, True)):
                rep = rcg.build_report(VERDICTS, "tr-TR", "01", rewrites=REWRITES, sources={}, budget=None,
                                       pack_dir=make_pack(td / str(sec), secondary=sec))
                self.assertEqual((rep["header"]["trust_level"], rep["header"]["secondary_passed"]), ("measured", expect))
                self.assertEqual(rcg.SECONDARY_FAILED in rep["header"]["trust_text"], not expect)
                md = rcg.render_markdown(rep)
                self.assertEqual("ranking and not as a grade" in md, not expect)
                self.assertEqual(text_style.punctuation_problems(md), [])

    def test_reason_is_house_style(self):
        r = rcg.reason_of(VERDICTS["verdicts"][2])
        self.assertTrue(r.startswith("ui verb"))
        self.assertEqual(text_style.punctuation_problems(r), [])


class ReportTests(unittest.TestCase):
    def _build(self, td: Path) -> dict[str, Any]:
        return rcg.build_report(VERDICTS, "tr-TR", "01", rewrites=REWRITES, sources={}, pack_dir=make_pack(td),
                                budget={"calls": 12, "errors": 0, "input_tokens": 1000, "output_tokens": 200, "latency_ms": 0,
                                        "cost_usd": 0.0123, "priced": False, "unpriced_models": ["gemini-4-hydrogen"]})

    def test_json_report(self):
        with TempDir() as td:
            rep = self._build(td)
        self.assertEqual(rep["header"]["trust_level"], "measured")
        self.assertEqual(rep["header"]["langpack_version"], "tr-TR-abc")
        self.assertEqual(rep["header"]["budget"]["calls"], 12)
        self.assertEqual(rep["summary"], {"critical": 1, "unresolved": 1, "rewrite": 1, "rewrite_light": 1, "pass": 1})
        self.assertEqual([l["key"] for l in rep["lines"]], ["CRIT", "UNR", "DLB", "LIGHT"])  # most urgent first, pass lines left out
        line = rep["lines"][0]
        for k in ("key", "en", "old", "new", "status", "reason", "evidence", "confidence", "votes", "decision"):
            self.assertIn(k, line)
        self.assertEqual(line["votes"], {"J1": [2, 5, 5], "J3": [2, 2, 3]})
        self.assertEqual(line["decision"], "")
        self.assertEqual(rep["changed"], 3)
        self.assertEqual(len(rep["unresolved"]), 1)
        u = rep["unresolved"][0]
        self.assertEqual(len(u["rationales"]), 3)
        self.assertEqual(u["proposal"], "")

    def test_markdown_style_and_verbatim_lines(self):
        with TempDir() as td:
            md = rcg.render_markdown(self._build(td))
        self.assertEqual(text_style.punctuation_problems(md), [])
        self.assertIn("`Kaydetmek; şimdi`", md)            # the game text stays verbatim inside code
        self.assertIn("`Hattı tut \\| şimdi`", md)         # pipes escaped in table cells
        self.assertIn("## Unresolved lines", md)
        self.assertIn("- Current line `Hattı tut | şimdi`", md)   # outside tables the pipe stays as is
        self.assertIn(rcg.NO_OBJECTION, md)
        self.assertIn("plus models without a price", md)
        self.assertNotIn("—", text_style.prose_only(md))


class CliTests(unittest.TestCase):
    def test_cli_files_exit_codes_and_tm_flow(self):
        with TempDir() as td:
            make_pack(td / "packs")
            v = write_json(td / "verdicts_tr-TR_01.json", VERDICTS)
            rw = write_json(td / "rewrites_tr-TR_01.json", REWRITES)
            write_text(td / "budget.jsonl", json.dumps({"role": "J1", "provider": "anthropic", "model": "claude-haiku-5-5", "input_tokens": 1000000,
                                                        "output_tokens": 0, "latency_ms": 5}) + "\n")
            code, out, err = run_cli("report_changes.py", str(v), "--locale", "tr-TR", "--rewrites", str(rw), "--budget-log", str(td / "budget.jsonl"),
                                     "--langpack-dir", str(td / "packs"), "--json")
            self.assertEqual(code, 1, err)                       # one unresolved line
            data = json.loads(out)
            self.assertEqual(data["trust_level"], "measured")
            rep = json.loads((td / "changes_tr-TR_01.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(rep["header"]["budget"]["cost_usd"], 0.10)
            md = (td / "changes_tr-TR_01.md").read_text(encoding="utf-8")
            self.assertEqual(text_style.punctuation_problems(md), [])
            for l in rep["lines"]:
                l["decision"] = "accept" if l["key"] != "UNR" else "reject"
            write_json(td / "changes_tr-TR_01.json", rep)
            code, out, err = run_cli("tm.py", str(td / "changes_tr-TR_01.json"), "--db", str(td / "tm.sqlite"), "--locale", "tr-TR", "--mode", "approve", "--json")
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["counts"]["accepted"], 3)
            clean = dict(VERDICTS)
            clean["verdicts"] = VERDICTS["verdicts"][:3]
            v2 = write_json(td / "verdicts_tr-TR_02.json", clean)
            src = write_json(td / "pass1.json", [{"key": "LIGHT", "en": "Open settings", "dst": "Ayarları aç"},
                                                 {"key": "CRIT", "en": "Save", "dst": "Kaydetmek"}])
            code, _, err = run_cli("report_changes.py", str(v2), "--locale", "tr-TR", "--source-table", str(src), "--langpack-dir", str(td / "none"),
                                   "--out-dir", str(td / "out"))
            self.assertEqual(code, 0, err)
            rep2 = json.loads((td / "out" / "changes_tr-TR_02.json").read_text(encoding="utf-8"))
            self.assertEqual(rep2["header"]["trust_level"], "rule_based")
            self.assertEqual(rep2["changed"], 0)                 # no rewrite file, so nothing new yet
            self.assertEqual(rep2["lines"][0]["old"], "Kaydetmek")

    def test_exit_2(self):
        with TempDir() as td:
            bad = write_json(td / "x.json", {"rows": []})
            self.assertEqual(run_cli("report_changes.py", str(bad), "--locale", "tr-TR")[0], 2)
            v = write_json(td / "verdicts_tr-TR_01.json", VERDICTS)
            self.assertEqual(run_cli("report_changes.py", str(v), "--locale", "tr-TR", "--budget-log", str(td / "missing.jsonl"))[0], 2)
            self.assertEqual(run_cli("report_changes.py", str(v), "--locale", "qq")[0], 2)

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertTrue("report_changes.py" in doc, "report_changes.py missing from CLI_REFERENCE.md")
        code, help_text, _ = run_cli("report_changes.py", "--help")
        self.assertEqual(code, 0)
        for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
            self.assertTrue(flag in doc, f"report_changes.py: {flag} missing from CLI_REFERENCE.md")


if __name__ == "__main__":
    unittest.main()
