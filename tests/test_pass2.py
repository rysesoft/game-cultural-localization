"""P12: Pass 2 with three candidates (prompts/pass2.<locale>.md), blind J1 pick, validate_critique check."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS, TempDir, run_cli, write_json  # noqa: E402

import pass2_rewrite as p2  # noqa: E402
import prompt_templates as pt  # noqa: E402
import text_style  # noqa: E402
import validate_critique  # noqa: E402
from providers import FakeScenario, Router, load_providers_config  # noqa: E402

NO_KEYS = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "", "GCL_OFFLINE": "1"}
SOURCES = {
    "DLG": {"en": "Take your time, kid.", "target": "Zamanını al, çocuk.", "category": "dialogue", "speaker": "Mentor", "archetype": "A1", "register": "dialogue_casual"},
    "PH": {"en": "Use {0} now", "target": "{0} şimdi kullan", "category": "ui", "speaker": "", "archetype": "", "register": "ui"},
    "BAD": {"en": "Press <b>X</b>", "target": "<b>X</b> tuşuna bas", "category": "ui", "speaker": "", "archetype": "", "register": "ui"},
    "OK": {"en": "Save", "target": "Kaydet", "category": "ui", "speaker": "", "archetype": "", "register": "ui"},
}


def verdict(key: str, status: str, score: int, issue: str = "translationese") -> Dict[str, Any]:
    votes = [{"key": key, "tier": "J1", "member": i, "family": f, "model": m, "score": score, "issue_type": issue if score < 5 else "none",
              "reason": "English word order" if score < 5 else "", "suggested": ""}
             for i, (f, m) in enumerate((("anthropic", "claude-haiku-5-5"), ("deepseek", "deepseek-flash"), ("google", "gemini-4-hydrogen")))]
    if key == "DLG":
        votes[0]["suggested"] = "Acele etme evlat."
    return {"key": key, "final_tier": "J1", "score": score, "status": status, "votes": votes,
            "evidence": {"ban_hits": [], "tm_neighbors": [{"dst": "Yavaş ol evlat.", "category": "dialogue"}], "roundtrip": {"applied": False}},
            "rationales": [v["reason"] for v in votes]}


VERDICTS = [verdict("DLG", "rewrite", 3), verdict("PH", "rewrite_light", 4), verdict("BAD", "critical", 2, "ui_verb"), verdict("OK", "pass", 5)]
SCENARIO = {
    "pass2": [{"contains": "{0} şimdi", "candidates": ["Şimdi kullan", "{0} hemen kullan", "{0} kullan hadi"]},
              {"contains": "tuşuna", "candidates": ["X tuşuna bas", "Şimdi X'e bas", "X'e dokun"]}],
    "picks": [{"contains": "Şimdi kullan", "prefer": "Şimdi kullan"},
              {"contains": "Acele etme", "family": "deepseek", "prefer": "(3)"},
              {"contains": "Acele etme", "prefer": "(2)"}],
}


def run(scenario: Dict[str, Any] = SCENARIO, **kw: Any) -> Dict[str, Any]:
    router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(scenario))
    return p2.rewrite_lines(VERDICTS, SOURCES, "tr-TR", router, pass2_system="P2", pick_system="CRITIC", **kw)


class PromptTests(unittest.TestCase):
    def test_pass2_prompts_native(self):
        for loc, words in (("tr-TR", ("aday", "kaynak", "jüri", "oyuncu")), ("de-DE", ("Fassung", "Ausgangstext", "Jury", "Spiel"))):
            tpl = pt.find_prompt("pass2", loc)
            self.assertTrue(tpl.native)
            prose = text_style.prose_only(tpl.body).casefold()
            for w in words:
                self.assertTrue(w.casefold() in prose, f"{loc}: {w}")
            self.assertEqual(tpl.body.count("{{WARMUP}}"), 1)
            self.assertEqual(tpl.body.count("{{CONTRASTIVE}}"), 1)
            self.assertEqual(re.findall(r"(?m)^(\d)\. ", tpl.body), [str(i) for i in range(1, 8)])
            self.assertIn('"candidates"', tpl.body)
            self.assertNotIn("Reply with", prose)
        self.assertTrue(pt.find_prompt("pass2", "fr").native)
        self.assertTrue((SCRIPTS.parent / "prompts" / "pass2.generic.md").is_file())
        for path in sorted((SCRIPTS.parent / "prompts").glob("pass2.*.md")):
            self.assertEqual(text_style.punctuation_problems(path.read_text(encoding="utf-8")), [], path.name)


class RewriteTests(unittest.TestCase):
    def test_three_candidates_blind_pick_and_validation(self):
        res = run()
        lines = {l["key"]: l for l in res["lines"]}
        self.assertEqual(set(lines), {"DLG", "PH", "BAD"})                  # pass lines are left alone
        self.assertTrue(all(len(l["candidates"]) == 4 for l in lines.values()))   # three rewrites and the current line
        dlg = lines["DLG"]
        self.assertEqual(dlg["candidates"], ["Acele etme evlat.", "Acele etme evlat. (2)", "Acele etme evlat. (3)", "Zamanını al, çocuk."])
        self.assertEqual(dlg["votes_per_candidate"], [0, 2, 1, 0])         # majority of the three J1 members
        self.assertEqual(dlg["recheck"], [5, 5, 5])                          # the new winner is judged once more
        self.assertEqual(dlg["new"], "Acele etme evlat. (2)")
        self.assertTrue(dlg["valid"])
        ph = lines["PH"]
        self.assertEqual(ph["votes_per_candidate"], [3, 0, 0, 0])
        self.assertEqual(ph["new"], "{0} hemen kullan")                     # top pick lost the placeholder, next one is valid
        self.assertTrue(any("placeholder" in p for p in ph["problems"]))
        bad = lines["BAD"]
        self.assertFalse(bad["valid"])                                       # every candidate drops the <b> tag
        self.assertEqual(bad["new"], bad["old"])
        crit = res["critique"]
        self.assertEqual(validate_critique.validate(crit, {k: v["target"] for k, v in SOURCES.items()}, "auto", "auto", "tr-TR"), [])
        self.assertEqual([e["key"] for e in crit["entries"]], ["DLG", "PH"])

    def test_jurors_never_see_the_source(self):
        seen: List[Dict[str, Any]] = []
        real = p2.pick_candidates

        def spy(provider, items, locale, **kw):
            seen.extend(items)
            return real(provider, items, locale, **kw)
        with mock.patch.object(p2, "pick_candidates", spy):
            run()
        self.assertTrue(seen)
        blob = json.dumps(seen, ensure_ascii=False)
        for s in SOURCES.values():
            self.assertNotIn(s["en"], blob)
        self.assertTrue(all(set(c) == {"id", "text"} for it in seen for c in it["candidates"]))
        self.assertEqual({c["id"] for c in seen[0]["candidates"]}, {"c1", "c2", "c3", "c4"})

    def test_the_current_line_can_win_and_a_rewrite_must_be_confirmed(self):
        # a line the jurors still prefer stays, and a winner the J1 jurors do not pass again does not replace the line
        sc = dict(SCENARIO, picks=[{"contains": "Zamanını al", "prefer": "Zamanını al"}] + SCENARIO["picks"])
        lines = {l["key"]: l for l in run(sc)["lines"]}
        self.assertTrue(lines["DLG"]["kept_by_pick"])
        self.assertEqual((lines["DLG"]["new"], lines["DLG"]["valid"]), ("Zamanını al, çocuk.", True))
        sc = dict(SCENARIO, scores=[{"contains": "hemen kullan", "tier": "J1", "score": 3, "reason": "stiff"}])
        res = run(sc)
        ph = {l["key"]: l for l in res["lines"]}["PH"]
        self.assertEqual((ph["new"], ph["valid"], ph["recheck"]), ("{0} şimdi kullan", False, [3, 3, 3]))
        self.assertIn("did not confirm", ph["problems"][-1])
        self.assertNotIn("PH", [e["key"] for e in res["critique"]["entries"]])

    def test_candidate_order_is_seeded(self):
        a = run(seed=1)
        b = run(seed=1)
        self.assertEqual(a, b)

    def test_parallel_workers_give_the_same_result(self):
        self.assertEqual(run(seed=1, workers=1), run(seed=1, workers=4))

    def test_status_filter(self):
        res = run(statuses=("critical",))
        self.assertEqual([l["key"] for l in res["lines"]], ["BAD"])


class CliTests(unittest.TestCase):
    def test_jury_then_pass2(self):
        with TempDir() as td:
            src = write_json(td / "pass1_tr-TR_01.json", [{"key": k, "en": v["en"], "dst": v["target"], "category": v["category"], "speaker": v["speaker"]}
                                                         for k, v in SOURCES.items()])
            blind = td / "blind_tr-TR_01.json"
            code, _, err = run_cli("make_blind_slice.py", str(src), "--locale", "tr-TR", "--out", str(blind), "--target-col", "dst")
            self.assertEqual(code, 0, err)
            sc = write_json(td / "sc.json", {"scores": [{"key": "DLG", "score": 3, "issue_type": "translationese", "reason": "calque"},
                                                        {"key": "PH", "family": "google", "score": 4, "reason": "stiff"}]})
            code, _, err = run_cli("jury.py", str(blind), "--locale", "tr-TR", "--dry-run", "--fake-scenario", str(sc), "--no-budget-caps",
                                   "--langpack-dir", str(td / "np"), env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            verdicts = td / "verdicts_tr-TR_01.json"
            code, out, err = run_cli("pass2_rewrite.py", str(verdicts), "--source-table", str(src), "--locale", "tr-TR", "--dry-run",
                                     "--critique-out", str(td / "critique_tr-TR_01.json"), "--langpack-dir", str(td / "np"), env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            rew = json.loads((td / "rewrites_tr-TR_01.json").read_text(encoding="utf-8"))
            self.assertEqual({l["key"] for l in rew["lines"]}, {"DLG", "PH"})
            code, _, err = run_cli("validate_critique.py", str(td / "critique_tr-TR_01.json"), "--slice", str(blind))
            self.assertEqual(code, 0, err)  # the selected lines pass the fixed critique schema against the blind slice
            crit = json.loads((td / "critique_tr-TR_01.json").read_text(encoding="utf-8"))
            self.assertEqual(crit["summary"], {"total": 4, "flagged": 2, "critical": 0})

    def test_exit_1_and_2(self):
        with TempDir() as td:
            src = write_json(td / "src.json", [{"key": "BAD", "en": "Press <b>X</b>", "dst": "<b>X</b> tuşuna bas", "category": "ui"}])
            v = write_json(td / "verdicts_tr-TR_09.json", {"source_file": "src.json", "verdicts": [verdict("BAD", "critical", 2, "ui_verb")]})
            sc = write_json(td / "sc.json", SCENARIO)
            code, out, err = run_cli("pass2_rewrite.py", str(v), "--source-table", str(src), "--locale", "tr-TR", "--dry-run", "--fake-scenario", str(sc),
                                     "--langpack-dir", str(td / "np"), env_extra=NO_KEYS)
            self.assertEqual(code, 1, err)
            self.assertIn("KEPT OLD", out)
            self.assertEqual(run_cli("pass2_rewrite.py", str(v), "--source-table", str(src), "--locale", "tr-TR", "--candidates", "9", "--dry-run", env_extra=NO_KEYS)[0], 2)
            self.assertEqual(run_cli("pass2_rewrite.py", str(src), "--source-table", str(src), "--locale", "tr-TR", "--dry-run", env_extra=NO_KEYS)[0], 2)
            ghost = write_json(td / "g.json", {"verdicts": [verdict("GHOST", "rewrite", 3)]})
            self.assertEqual(run_cli("pass2_rewrite.py", str(ghost), "--source-table", str(src), "--locale", "tr-TR", "--dry-run", env_extra=NO_KEYS)[0], 2)
            code, _, err = run_cli("pass2_rewrite.py", str(v), "--source-table", str(src), "--locale", "tr-TR", env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("ANTHROPIC_API_KEY", err)

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertTrue("pass2_rewrite.py" in doc, "pass2_rewrite.py missing from CLI_REFERENCE.md")
        code, help_text, _ = run_cli("pass2_rewrite.py", "--help")
        self.assertEqual(code, 0)
        for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
            self.assertTrue(flag in doc, f"pass2_rewrite.py: {flag} missing from CLI_REFERENCE.md")


if __name__ == "__main__":
    unittest.main()
