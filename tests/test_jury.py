"""P9: jury.py (J1-J3 tiers, A4 agreement rule, critical shortcut, budget caps, B3.4 verdicts)."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, Dict, List

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS, TempDir, run_cli, write_json  # noqa: E402

import jury  # noqa: E402
from l10n_common import L10nError  # noqa: E402
from providers import FakeScenario, Router, load_providers_config  # noqa: E402

NO_KEYS = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "", "GCL_OFFLINE": "1"}
AG = {"pass_min": 4, "max_spread": 1, "critical_max": 2}
LONG_DLG = "Atölyeyi bu gece kapatmadan önce bütün aletleri yerine koymayı sakın unutma evlat."

SCENARIO = {"scores": [
    {"key": "ESC", "tier": "J1", "family": "google", "score": 3, "issue_type": "register", "reason": "stiff"},
    {"key": "CRIT", "tier": "J1", "family": "anthropic", "score": 2, "issue_type": "ui_verb", "reason": "broken button"},
    {"key": "CRIT", "tier": "J3", "score": 2, "issue_type": "ui_verb", "reason": "agreed broken"},
    {"key": "DIS", "tier": "J1", "family": "google", "score": 3, "reason": "maybe"},
    {"key": "DIS", "tier": "J2", "family": "google", "score": 3, "reason": "still maybe"},
    {"key": "DIS", "tier": "J3", "family": "anthropic", "score": 5, "reason": ""},
    {"key": "DIS", "tier": "J3", "family": "google", "score": 2, "issue_type": "register", "reason": "wrong register"},
    {"key": "DIS", "tier": "J3", "family": "deepseek", "score": 3, "issue_type": "translationese", "reason": "calque"},
    {"key": "LIGHT", "tier": "J1", "family": "deepseek", "score": 4, "issue_type": "translationese", "reason": "a bit stiff"},
]}


def slice_doc(extra_fillers: int = 16) -> Dict[str, Any]:
    entries = [
        {"key": "OK", "category": "ui", "target": "Kaydet"},
        {"key": "LIGHT", "category": "ui", "target": "Ayarları aç"},
        {"key": "ESC", "category": "dialogue", "speaker": "Mentor", "target": "Hadi bakalım, işe koyulalım."},
        {"key": "CRIT", "category": "ui", "target": "Kaydetmek"},
        {"key": "DIS", "category": "dialogue", "speaker": "Mentor", "target": LONG_DLG},
        {"key": "BAN", "category": "ui_toast", "target": "Burada zaten bir eşya bulunmaktadır!"},
    ]
    entries += [{"key": f"F{i:02d}", "category": "ui", "target": f"Menü {i}"} for i in range(extra_fillers)]
    return {"locale": "tr-TR", "source_file": "pass1_tr-TR_01.json", "blind": True, "entries": entries}


def run(scenario: Dict[str, Any], doc: Dict[str, Any], caps: bool = True, **kw: Any) -> Dict[str, Any]:
    router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(scenario))
    with TempDir() as td:
        entries, _ = jury.load_blind_slice(write_json(td / "blind_tr-TR_01.json", doc))
    res = jury.run_jury(entries, "tr-TR", router, system="SYS", budget_caps=caps, **kw)
    res["router"] = router
    return res


class RuleTests(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(jury.classify([5, 5, 4], AG), "pass")
        self.assertEqual(jury.classify([4, 4, 4], AG), "pass")
        self.assertEqual(jury.classify([5, 4, 3], AG), "escalate")      # a 3
        self.assertEqual(jury.classify([5, 5, 3], AG), "escalate")      # spread 2
        self.assertEqual(jury.classify([3, 3, 3], AG), "escalate")      # agreement on a low score still escalates below J3
        self.assertEqual(jury.classify([5, 5, 2], AG), "critical")
        self.assertEqual(jury.classify([1, 1, 1], AG), "critical")
        self.assertTrue(jury.agrees([3, 3, 2], AG))
        self.assertFalse(jury.agrees([5, 3, 2], AG))
        self.assertEqual([jury.status_for(s) for s in (5, 4, 3, 2, 1)], ["pass", "rewrite_light", "rewrite", "critical", "critical"])


class RunTests(unittest.TestCase):
    def test_pass_escalate_critical_unresolved(self):
        res = run(SCENARIO, slice_doc())
        v = {x["key"]: x for x in res["verdicts"]}
        self.assertIsNone(res["halted"])
        self.assertEqual(res["pending"], [])
        self.assertEqual((v["OK"]["final_tier"], v["OK"]["status"], v["OK"]["score"]), ("J1", "pass", 5))
        self.assertEqual((v["LIGHT"]["final_tier"], v["LIGHT"]["status"], v["LIGHT"]["score"]), ("J1", "rewrite_light", 4))
        self.assertEqual((v["ESC"]["final_tier"], v["ESC"]["status"]), ("J2", "pass"))
        self.assertEqual([x["tier"] for x in v["ESC"]["votes"]], ["J1"] * 3 + ["J2"] * 3)
        # critical shortcut: J1 -> J3, J2 never sees the line
        self.assertEqual([x["tier"] for x in v["CRIT"]["votes"]], ["J1"] * 3 + ["J3"] * 3)
        self.assertEqual((v["CRIT"]["final_tier"], v["CRIT"]["status"], v["CRIT"]["score"]), ("J3", "critical", 2))
        # J3 disagreement without a deliberation round -> unresolved with three rationales
        self.assertEqual((v["DIS"]["final_tier"], v["DIS"]["status"]), ("J3", "unresolved"))
        self.assertEqual(len(v["DIS"]["rationales"]), 3)
        self.assertEqual(res["stats"]["status"]["unresolved"], 1)
        self.assertEqual(res["stats"]["J1"], {"lines": 22, "settled": 19, "to_J2": 2, "critical_to_J3": 1})

    def test_vote_and_verdict_schema(self):
        res = run(SCENARIO, slice_doc())
        v = {x["key"]: x for x in res["verdicts"]}
        self.assertEqual(set(v["OK"]), {"key", "final_tier", "score", "status", "votes", "evidence", "rationales"})
        vote = v["CRIT"]["votes"][0]
        self.assertEqual(set(vote), {"key", "tier", "member", "family", "model", "score", "issue_type", "reason", "suggested"})
        self.assertEqual({x["family"] for x in v["CRIT"]["votes"][:3]}, {"anthropic", "google", "deepseek"})
        self.assertEqual({x["model"] for x in v["CRIT"]["votes"][3:]}, {"claude-opus-5-5", "deepseek-v4-pro", "gemini-4-carbon"})
        self.assertEqual(set(v["BAN"]["evidence"]), {"ban_hits", "tm_neighbors", "roundtrip"})
        self.assertIn("TR-BULUNMAKTADIR", [b["rule"] for b in v["BAN"]["evidence"]["ban_hits"]])
        self.assertEqual(v["OK"]["evidence"]["ban_hits"], [])
        self.assertEqual(v["OK"]["evidence"]["roundtrip"], {"applied": False, "reason": "not_needed"})

    def test_roundtrip_evidence_only_for_j3_lines(self):
        seen: List[str] = []

        def rt(lines):
            seen.extend(e["key"] for e in lines)
            return {e["key"]: {"applied": True, "calque_score": 0.4, "back": "x", "suspect": False} for e in lines}
        res = run(SCENARIO, slice_doc(), roundtrip_fn=rt)
        self.assertEqual(sorted(seen), ["CRIT", "DIS"])
        v = {x["key"]: x for x in res["verdicts"]}
        self.assertTrue(v["DIS"]["evidence"]["roundtrip"]["applied"])

    def test_deliberator_hook(self):
        def deliberate(entry, j3_votes, evidence):
            return {"score": 3, "status": "rewrite", "rationales": ["a", "b", "c"], "revotes": []}
        res = run(SCENARIO, slice_doc(), deliberator=deliberate)
        v = {x["key"]: x for x in res["verdicts"]}
        self.assertEqual((v["DIS"]["final_tier"], v["DIS"]["status"], v["DIS"]["score"]), ("deliberation", "rewrite", 3))

    def test_budget_cap_stops_the_run(self):
        doc = slice_doc(extra_fillers=4)   # 10 lines, ESC + DIS escalate (20 %), CRIT + DIS reach J3 (20 % > 10 %)
        res = run(SCENARIO, doc)
        self.assertEqual(res["halted"]["stage"], "J3")
        self.assertEqual(sorted(res["pending"]), ["CRIT", "DIS"])
        self.assertNotIn("J3", {r["role"] for r in res["router"].budget.records})
        sc = dict(SCENARIO)
        sc["scores"] = SCENARIO["scores"] + [{"contains": "Menü", "tier": "J1", "family": "google", "score": 3}]
        res = run(sc, slice_doc(extra_fillers=4))
        self.assertEqual(res["halted"]["stage"], "J2")
        self.assertEqual({r["role"] for r in res["router"].budget.records}, {"J1"})
        self.assertIn("Pass 1", res["halted"]["reason"])
        res = run(sc, slice_doc(extra_fillers=4), caps=False)
        self.assertIsNone(res["halted"])
        self.assertEqual(res["pending"], [])

    def test_slice_validation(self):
        with TempDir() as td:
            with self.assertRaises(L10nError):
                jury.load_blind_slice(write_json(td / "a.json", {"entries": [{"key": "A", "en": "Save", "target": "Kaydet"}]}))
            with self.assertRaises(L10nError):
                jury.load_blind_slice(write_json(td / "b.json", {"entries": [{"key": "A", "target": "x"}, {"key": "A", "target": "y"}]}))
            with self.assertRaises(L10nError):
                jury.load_blind_slice(write_json(td / "c.json", {"entries": []}))
        self.assertEqual(jury.juror_view({"key": "A", "target": "x", "register": "ui", "notes": "secret", "speaker": ""}),
                         {"key": "A", "target": "x", "register": "ui"})


class CliTests(unittest.TestCase):
    def test_cli_paths(self):
        with TempDir() as td:
            blind = write_json(td / "blind_tr-TR_01.json", slice_doc())
            sc = write_json(td / "sc.json", SCENARIO)
            src = write_json(td / "pass1.json", [{"key": e["key"], "en": "Long English source line for the back translation test here.",
                                                  "dst": e["target"]} for e in slice_doc()["entries"]])
            code, out, err = run_cli("jury.py", str(blind), "--locale", "tr-TR", "--dry-run", "--fake-scenario", str(sc), "--source-table", str(src),
                                     "--langpack-dir", str(td / "nopacks"), "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 1, err)           # DIS is unresolved
            doc = json.loads((td / "verdicts_tr-TR_01.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["stats"]["status"]["unresolved"], 1)
            dis = [v for v in doc["verdicts"] if v["key"] == "DIS"][0]
            self.assertTrue(dis["evidence"]["roundtrip"]["applied"])
            self.assertTrue((td / "budget.jsonl").is_file())
            first = (td / "verdicts_tr-TR_01.json").read_text(encoding="utf-8")
            run_cli("jury.py", str(blind), "--locale", "tr-TR", "--dry-run", "--fake-scenario", str(sc), "--source-table", str(src),
                    "--langpack-dir", str(td / "nopacks"), env_extra=NO_KEYS)
            self.assertEqual((td / "verdicts_tr-TR_01.json").read_text(encoding="utf-8"), first)
            clean = write_json(td / "blind_tr-TR_02.json", {"entries": [{"key": "A", "target": "Kaydet"}]})
            code, out, err = run_cli("jury.py", str(clean), "--locale", "tr-TR", "--dry-run", "--out", str(td / "v2.json"), env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            self.assertIn("pass 1", out)

    def test_exit_2(self):
        with TempDir() as td:
            leak = write_json(td / "leak.json", {"entries": [{"key": "A", "source": "Save", "target": "Kaydet"}]})
            code, _, err = run_cli("jury.py", str(leak), "--locale", "tr-TR", "--dry-run", env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("source column", err)
            cfg = json.loads((SCRIPTS / "providers.config.json").read_text(encoding="utf-8"))
            cfg["roles"]["J2"] = ["sonnet", "opus", "neon"]
            pc = write_json(td / "p.json", cfg)
            blind = write_json(td / "blind.json", {"entries": [{"key": "A", "target": "Kaydet"}]})
            code, _, err = run_cli("jury.py", str(blind), "--locale", "tr-TR", "--dry-run", "--providers-config", str(pc), env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("same family", err)
            code, _, err = run_cli("jury.py", str(blind), "--locale", "tr-TR", env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("API_KEY", err)

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertTrue("jury.py" in doc, "jury.py missing from CLI_REFERENCE.md")
        code, help_text, _ = run_cli("jury.py", "--help")
        self.assertEqual(code, 0)
        for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
            self.assertTrue(flag in doc, f"jury.py: {flag} missing from CLI_REFERENCE.md")


if __name__ == "__main__":
    unittest.main()
