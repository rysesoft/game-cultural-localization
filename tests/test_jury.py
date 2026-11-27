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
import text_style  # noqa: E402
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


def run(scenario: Dict[str, Any], doc: Dict[str, Any], caps: bool = True, sample: Any = (0, 0), **kw: Any) -> Dict[str, Any]:
    """sample = (min_judged, min_escalated) of the budget caps, None keeps the bundled config."""
    router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(scenario))
    if sample is not None:
        router.config.budget_caps.update(min_judged=sample[0], min_escalated=sample[1])
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


class EverydayWordTests(unittest.TestCase):
    """The first question of a juror, set by the studio. Is every word of the line part of everyday use of the language?"""

    def test_two_jurors_who_find_such_a_word_cap_the_tier(self):
        from llm_tasks import EVERYDAY_CAP, EVERYDAY_MIN_JURORS, INSTRUCTIONS, everyday_check, everyday_rule, normalize_vote
        self.assertEqual((EVERYDAY_CAP, EVERYDAY_MIN_JURORS), (3, 2))
        self.assertTrue(INSTRUCTIONS["jury"].startswith("First ask of every word"))     # asked before the score
        for task in ("jury", "deliberate", "pass2"):
            self.assertIn("odd_words", INSTRUCTIONS[task])
        line = "Mevcut bakiyeniz yetersizdir."

        def vote(**kw):
            return everyday_check(normalize_vote(kw), line)
        # one vote keeps its score, only the words the line holds count, placeholders and tags are no words
        v = vote(score=5, odd_words=["Mevcut", "müstakbel", "{0}", "<b>", "123"])
        self.assertEqual((v["score"], v["odd_words"]), (5, ["Mevcut"]))
        # one juror alone is evidence, the tier keeps its scores
        tier = [vote(score=5, odd_words=["Mevcut"]), vote(score=5), vote(score=4, issue_type="register", reason="stiff")]
        self.assertFalse(everyday_rule(tier))
        self.assertEqual([x["score"] for x in tier], [5, 5, 4])
        # two jurors cap every score of the tier, every reason names the words, a lower score stays
        tier = [vote(score=5, odd_words=["Mevcut"]), vote(score=4, reason="stiff.", odd_words="yetersizdir"), vote(score=2, issue_type="ui_verb", reason="x")]
        self.assertTrue(everyday_rule(tier))
        self.assertEqual([x["score"] for x in tier], [3, 3, 2])
        self.assertEqual(tier[0]["issue_type"], "translationese")
        self.assertTrue(tier[1]["reason"].startswith("stiff. 2 jurors found words a native would not use every day (Mevcut, yetersizdir)"))
        self.assertTrue(all(text_style.punctuation_problems(x["reason"]) == [] for x in tier))

    def test_one_juror_is_evidence_two_jurors_send_the_line_on(self):
        one = {"scores": [{"key": "ESC", "tier": "J1", "family": "google", "score": 5, "odd_words": ["koyulalım"]}]}
        v = {x["key"]: x for x in run(one, slice_doc())["verdicts"]}
        self.assertEqual((v["ESC"]["status"], v["ESC"]["final_tier"]), ("pass", "J1"))       # a single flag does not cap
        self.assertEqual([x["odd_words"] for x in v["ESC"]["votes"] if x["family"] == "google"], [["koyulalım"]])   # but it is kept
        two = {"scores": [{"key": "ESC", "tier": "J1", "family": f, "score": 5, "odd_words": ["koyulalım"]} for f in ("google", "deepseek")]}
        v = {x["key"]: x for x in run(two, slice_doc())["verdicts"]}
        esc = v["ESC"]
        self.assertEqual([x["score"] for x in esc["votes"] if x["tier"] == "J1"], [3, 3, 3])   # the whole tier is capped
        self.assertEqual(esc["final_tier"], "J2")
        self.assertEqual(v["OK"]["status"], "pass")
        three = {"scores": [{"key": "ESC", "family": f, "score": 5, "odd_words": ["koyulalım"]} for f in ("google", "deepseek")]}
        esc = {x["key"]: x for x in run(three, slice_doc())["verdicts"]}["ESC"]
        self.assertEqual((esc["final_tier"], esc["status"], esc["score"]), ("J3", "rewrite", 3))   # J3 agrees, Pass 2 rewrites it
        import pass2_rewrite as p2
        rows: List[Dict[str, Any]] = []
        real = p2.pass2_candidates

        def spy(provider, rws, locale, **kw):
            rows.extend(rws)
            return real(provider, rws, locale, **kw)
        router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario({}))
        from unittest import mock
        with mock.patch.object(p2, "pass2_candidates", spy):
            p2.rewrite_lines([esc], {"ESC": {"en": "Let's get to work.", "target": "Hadi bakalım, işe koyulalım."}}, "tr-TR", router,
                             pass2_system="P2", pick_system="CRITIC")
        self.assertEqual(rows[0]["odd_words"], ["koyulalım"])

    def test_a_changed_instruction_never_reuses_cached_batches(self):
        import llm_tasks
        router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario({}))
        m = router.jury("J1")[0]
        with TempDir() as td:
            memo = llm_tasks.BatchMemo(td / "memo.json")
            entries = [{"key": "A", "target": "Kaydet"}]
            llm_tasks.score_entries(m.provider, entries, "tr-TR", system="S", memo=memo)
            self.assertEqual(len(memo), 1)
            with mock_dict(llm_tasks.INSTRUCTIONS, "jury", llm_tasks.INSTRUCTIONS["jury"] + " Changed."):
                llm_tasks.score_entries(m.provider, entries, "tr-TR", system="S", memo=memo)
            self.assertEqual(len(memo), 2)                                              # a new batch, not the old answer


def mock_dict(d: Dict[str, Any], key: str, value: Any) -> Any:
    from unittest import mock
    return mock.patch.dict(d, {key: value})


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
        self.assertEqual(set(vote), {"key", "tier", "member", "family", "model", "score", "issue_type", "reason", "suggested", "odd_words"})
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

    def test_parallel_workers_give_the_same_verdicts(self):
        from deliberate import make_deliberator
        outs = []
        for workers in (1, 4):
            router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(SCENARIO))
            with TempDir() as td:
                entries, _ = jury.load_blind_slice(write_json(td / "blind_tr-TR_01.json", slice_doc()))
            res = jury.run_jury(entries, "tr-TR", router, system="SYS", budget_caps=False,
                                deliberator=make_deliberator(router, "tr-TR", "SYS"), workers=workers)
            outs.append((res["verdicts"], res["stats"], sorted((r["model"], r["role"]) for r in router.budget.records)))
        self.assertEqual(outs[0], outs[1])   # same verdicts, votes in member order and the same calls
        tiers = {v["key"]: v["final_tier"] for v in outs[1][0]}
        self.assertEqual((tiers["OK"], tiers["ESC"], tiers["CRIT"]), ("J1", "J2", "J3"))
        self.assertEqual(tiers["DIS"], "deliberation")

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

    def test_a_small_sample_never_stops_the_run(self):
        # the bundled config stops only after 100 judged lines with at least 10 over the cap
        res = run(SCENARIO, slice_doc(extra_fillers=4), sample=None)   # 10 lines, 20 % to J3
        self.assertIsNone(res["halted"])
        self.assertEqual(res["pending"], [])
        self.assertEqual(res["stats"]["run_to_J3_ratio"], 0.2)

    def test_caps_read_the_whole_run(self):
        # two of ten lines go to J3. Alone that is 20 %, after 90 clean lines judged before it is 2 %
        tally = jury.EscalationTally(lines=90)
        res = run(SCENARIO, slice_doc(extra_fillers=4), tally=tally)
        self.assertIsNone(res["halted"])
        self.assertEqual((res["stats"]["to_J3_ratio"], res["stats"]["run_to_J3_ratio"]), (0.2, 0.02))
        self.assertEqual((tally.lines, tally.to_j3), (100, 2))
        res = run(SCENARIO, slice_doc(extra_fillers=4), tally=jury.EscalationTally(lines=10, to_j3=2))
        self.assertEqual(res["halted"]["stage"], "J3")                    # 2 earlier plus CRIT, 3 of 20 lines, 15 %
        self.assertEqual((res["halted"]["lines"], res["halted"]["judged"]), (3, 20))
        self.assertEqual(res["halted"]["keys"], ["CRIT"])                 # the line of this batch that tripped it
        self.assertIn("CRIT", res["halted"]["reason"])

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

    def test_cache_resumes_without_calls(self):
        with TempDir() as td:
            blind = write_json(td / "blind_tr-TR_01.json", slice_doc())
            sc = write_json(td / "sc.json", SCENARIO)
            log = td / "budget.jsonl"
            args = ("jury.py", str(blind), "--locale", "tr-TR", "--dry-run", "--fake-scenario", str(sc), "--langpack-dir", str(td / "np"),
                    "--cache", str(td / "votes.json"), "--budget-log", str(log), "--no-budget-caps")
            run_cli(*args, env_extra=NO_KEYS)
            first = (td / "verdicts_tr-TR_01.json").read_text(encoding="utf-8")
            calls = len(log.read_text(encoding="utf-8").splitlines())
            self.assertGreater(calls, 0)
            run_cli(*args, env_extra=NO_KEYS)
            again = {json.loads(l)["role"] for l in log.read_text(encoding="utf-8").splitlines()[calls:]}
            self.assertFalse(again & {"J1", "J2"})                             # every vote batch came from the cache
            self.assertEqual((td / "verdicts_tr-TR_01.json").read_text(encoding="utf-8"), first)

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
