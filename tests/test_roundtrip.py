"""P6: roundtrip_check.py (back-translation calque score, eligibility, calibration from the contrastive set)."""

import json
import re
import unittest
from pathlib import Path
from typing import Any

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS, TempDir, run_cli, write_json  # noqa: E402

import roundtrip_check as rc  # noqa: E402
from l10n_common import L10nError  # noqa: E402
from providers import Router, load_providers_config  # noqa: E402

NO_KEYS = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "", "GCL_OFFLINE": "1"}
REGS = ("dialogue_casual", "dialogue_formal")
LONG_EN = "Take your time kid, the generator is not going anywhere tonight."


def contrastive(n: int) -> dict[str, Any]:
    pairs = []
    for i in range(n):
        en = f"Take your time kid, generator number {i} is not going anywhere tonight."
        pairs.append({"key": f"D{i}", "en": en, "native": f"Acele etme evlat, {i} numaralı jeneratör bu gece hiçbir yere kaçmıyor.",
                      "robot": f"[tr-TR literal] {en}", "register": "dialogue_casual"})
    pairs.append({"key": "UI", "en": "Save", "native": "Kaydet", "robot": "[tr-TR literal] Save", "register": "ui"})
    return {"locale": "tr-TR", "pairs": pairs}


class ScoreTests(unittest.TestCase):
    def test_calque_score_range(self):
        self.assertEqual(rc.calque_score(LONG_EN, LONG_EN), 1.0)
        reversed_back = " ".join(reversed(LONG_EN.split()))
        self.assertLess(rc.calque_score(LONG_EN, reversed_back), 0.6)
        self.assertGreater(rc.calque_score(LONG_EN, "Take your time kid, the generator will not go anywhere tonight."), 0.8)
        self.assertEqual(rc.calque_score(LONG_EN, ""), 0.0)
        for s in (rc.calque_score("a b c", "c b a"), rc.calque_score("x", "y")):
            self.assertTrue(0.0 <= s <= 1.0)

    def test_eligibility(self):
        self.assertEqual(rc.eligible("Kaydet ve çık buradan hemen şimdi lütfen", "ui", 6, REGS), (False, "register"))
        self.assertEqual(rc.eligible("Acele etme evlat.", "dialogue_casual", 6, REGS), (False, "short"))
        self.assertEqual(rc.eligible("Bir iki üç dört beş altı", "dialogue_casual", 6, REGS), (False, "short"))  # 6 words is not over 6
        self.assertEqual(rc.eligible("Bir iki üç dört beş altı yedi", "dialogue_formal", 6, REGS), (True, ""))

    def test_best_threshold(self):
        t, acc = rc.best_threshold([0.2, 0.3, 0.35], [0.9, 0.95, 1.0])
        self.assertTrue(0.35 < t < 0.9)
        self.assertEqual(acc, 1.0)
        t, acc = rc.best_threshold([0.5, 0.9], [0.6, 0.95])
        self.assertLess(acc, 1.0)


class EvidenceTests(unittest.TestCase):
    def test_only_long_dialogue_costs_a_call(self):
        router = Router(load_providers_config(), dry_run=True)
        prov = router.for_role("roundtrip")
        rows = [{"key": "UI", "en": "Save", "target": "Kaydet", "register": "ui"},
                {"key": "SHORT", "en": "Hi.", "target": "Selam.", "register": "dialogue_casual"},
                {"key": "CALQUE", "en": LONG_EN, "target": f"[tr-TR] {LONG_EN}", "register": "dialogue_casual"},
                {"key": "NATIVE", "en": LONG_EN, "target": "Acele etme evlat, jeneratör bu gece hiçbir yere kaçmıyor.", "register": "dialogue_casual"}]
        ev = rc.roundtrip_evidence(rows, "tr-TR", prov, min_words=6, registers=REGS, threshold=0.85)
        self.assertEqual(ev["UI"], {"applied": False, "reason": "register"})
        self.assertEqual(ev["SHORT"], {"applied": False, "reason": "short"})
        self.assertTrue(ev["CALQUE"]["applied"])
        self.assertEqual(ev["CALQUE"]["calque_score"], 1.0)
        self.assertTrue(ev["CALQUE"]["suspect"])
        self.assertFalse(ev["NATIVE"]["suspect"])
        self.assertLess(ev["NATIVE"]["calque_score"], 0.5)
        self.assertEqual(len(router.budget.records), 1)  # one batch for the two eligible rows
        router2 = Router(load_providers_config(), dry_run=True)
        rc.roundtrip_evidence(rows[:2], "tr-TR", router2.for_role("roundtrip"), min_words=6, registers=REGS, threshold=0.85)
        self.assertEqual(router2.budget.records, [])

    def test_calibration(self):
        router = Router(load_providers_config(), dry_run=True)
        res = rc.calibrate(contrastive(6), "tr-TR", router.for_role("roundtrip"), min_words=6, registers=REGS)
        self.assertEqual((res["n_native"], res["n_robot"]), (6, 6))   # the UI pair is not eligible
        self.assertLess(res["native_mean"], res["robot_mean"])
        self.assertEqual(res["balanced_accuracy"], 1.0)
        self.assertTrue(res["native_mean"] < res["threshold"] <= res["robot_mean"])
        self.assertFalse(res["weak"])
        weak = rc.calibrate(contrastive(3), "tr-TR", router.for_role("roundtrip"), min_words=6, registers=REGS)
        self.assertTrue(weak["weak"])
        with self.assertRaises(L10nError):
            rc.calibrate({"pairs": contrastive(0)["pairs"]}, "tr-TR", router.for_role("roundtrip"), min_words=6, registers=REGS)


class CliTests(unittest.TestCase):
    def test_calibrate_then_check(self):
        with TempDir() as td:
            cset = write_json(td / "contrastive.json", contrastive(8))
            packs = td / "packs"
            code, out, err = run_cli("roundtrip_check.py", str(cset), "--locale", "tr-TR", "--calibrate", "--dry-run",
                                     "--langpack-dir", str(packs), "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            thr = json.loads((packs / "tr-TR" / "roundtrip_threshold.json").read_text(encoding="utf-8"))
            self.assertTrue(thr["calibrated"])
            table = write_json(td / "pass1.json", [
                {"key": "A", "en": LONG_EN, "dst": "Acele etme evlat, jeneratör bu gece hiçbir yere kaçmıyor.", "category": "dialogue"},
                {"key": "B", "en": "Save", "dst": "Kaydet", "category": "ui"}])
            code, out, err = run_cli("roundtrip_check.py", str(table), "--locale", "tr-TR", "--dry-run", "--langpack-dir", str(packs), "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            data = json.loads(out)
            self.assertEqual(data["threshold"], thr["threshold"])
            self.assertEqual(data["summary"], {"rows": 2, "applied": 1, "suspects": 0})
            write_json(table, [{"key": "C", "en": LONG_EN, "dst": f"[tr-TR] {LONG_EN}", "category": "dialogue"}])
            code, out, err = run_cli("roundtrip_check.py", str(table), "--locale", "tr-TR", "--dry-run", "--threshold", "0.9", env_extra=NO_KEYS)
            self.assertEqual(code, 1, err)
            self.assertIn("CALQUE C", out)

    def test_weak_calibration_exit_1_and_usage_errors(self):
        with TempDir() as td:
            cset = write_json(td / "c.json", contrastive(2))
            code, _, err = run_cli("roundtrip_check.py", str(cset), "--locale", "tr-TR", "--calibrate", "--dry-run", "--out", str(td / "t.json"), env_extra=NO_KEYS)
            self.assertEqual(code, 1, err)
            self.assertTrue((td / "t.json").is_file())
            code, _, err = run_cli("roundtrip_check.py", str(cset), "--locale", "tr-TR", "--calibrate", "--out", str(td / "t.json"), env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("DEEPSEEK_API_KEY", err)
            bad = write_json(td / "bad.json", [{"key": "A", "en": "x"}])
            self.assertEqual(run_cli("roundtrip_check.py", str(bad), "--locale", "tr-TR", "--dry-run", env_extra=NO_KEYS)[0], 2)
            self.assertEqual(run_cli("roundtrip_check.py", str(cset), "--locale", "zz", "--dry-run", env_extra=NO_KEYS)[0], 2)

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertTrue("roundtrip_check.py" in doc, "roundtrip_check.py missing from CLI_REFERENCE.md")
        code, help_text, _ = run_cli("roundtrip_check.py", "--help")
        self.assertEqual(code, 0)
        for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
            self.assertTrue(flag in doc, f"roundtrip_check.py: {flag} missing from CLI_REFERENCE.md")


if __name__ == "__main__":
    unittest.main()
