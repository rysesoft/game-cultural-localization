"""P10: deliberate.py (anonymous rationales, evidence package, one re-vote, majority, unresolved)."""
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

import deliberate as dl  # noqa: E402
import jury  # noqa: E402
from providers import ChatResult, FakeScenario, Router, load_providers_config, split_envelope  # noqa: E402

NO_KEYS = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "", "GCL_OFFLINE": "1"}
MODEL_NAMES = ("claude", "anthropic", "gemini", "google", "deepseek", "opus", "carbon", "v4pro", "deepseek-v4-pro", "gemini-4-carbon",
               "claude-opus-5-5", "sonnet", "haiku")

ENTRY = {"key": "DIS", "target": "Atölyeyi bu gece kapatmadan önce bütün aletleri yerine koymayı sakın unutma evlat.",
         "register": "dialogue_casual", "speaker": "Mentor", "category": "dialogue"}
J3 = [
    {"key": "DIS", "tier": "J3", "member": 0, "family": "anthropic", "model": "claude-opus-5-5", "score": 5, "issue_type": "none",
     "reason": "Claude here, sounds native to me.", "suggested": ""},
    {"key": "DIS", "tier": "J3", "member": 1, "family": "deepseek", "model": "deepseek-v4-pro", "score": 3, "issue_type": "translationese",
     "reason": "As DeepSeek V4 Pro I see English word order.", "suggested": "Bu gece kapatmadan aletleri yerine koy evlat."},
    {"key": "DIS", "tier": "J3", "member": 2, "family": "google", "model": "gemini-4-carbon", "score": 2, "issue_type": "register",
     "reason": "Gemini thinks the register is off; opus would disagree.", "suggested": "Aletleri yerine koymayı unutma."},
]
EVIDENCE = {"ban_hits": [{"rule": "TR-KNOWN-CALQUE", "severity": "WARN", "message": "calque"}],
            "tm_neighbors": [{"src": "SECRET ENGLISH", "dst": f"Onaylı satır {i}", "category": "dialogue", "similarity": 0.9 - i / 10,
                              "status": "approved"} for i in range(5)],
            "roundtrip": {"applied": True, "calque_score": 0.91, "back": "SECRET BACK", "suspect": True}}


class SpyProvider:
    """Captures deliberation payloads and answers with a fixed score."""

    def __init__(self, model: str, score: int, odd: Any = ()) -> None:
        self.model = model
        self.score = score
        self.odd = list(odd)
        self.payloads: List[Dict[str, Any]] = []
        self.systems: List[str] = []

    def complete(self, system: str, user: str, **kw: Any) -> ChatResult:
        _i, p = split_envelope(user)
        self.payloads.append(p)
        self.systems.append(system)
        return ChatResult(json.dumps({"score": self.score, "issue_type": "translationese", "reason": f"revote {self.score}", "suggested": "",
                                      "odd_words": self.odd}), 1, 1, self.model, 0)


class Seat:
    def __init__(self, index: int, family: str, provider: SpyProvider) -> None:
        self.index, self.family, self.provider = index, family, provider


def seats(scores: List[int], odd: Any = ((), (), ())) -> List[Seat]:
    fams = ("anthropic", "deepseek", "google")
    models = ("claude-opus-5-5", "deepseek-v4-pro", "gemini-4-carbon")
    return [Seat(i, fams[i], SpyProvider(models[i], s, odd[i])) for i, s in enumerate(scores)]


class DeliberationTests(unittest.TestCase):
    def setUp(self):
        self.scrub = dl.name_scrubber(load_providers_config())

    def test_majority(self):
        res = dl.deliberate_line(ENTRY, J3, EVIDENCE, seats([4, 3, 3]), "tr-TR", "SYS", self.scrub)
        self.assertEqual((res["score"], res["status"]), (3, "rewrite"))
        self.assertEqual(res["deliberation"], {"first": [5, 3, 2], "revote": [4, 3, 3], "majority": 3})
        self.assertEqual(len(res["revotes"]), 3)
        self.assertEqual({v["tier"] for v in res["revotes"]}, {"deliberation"})
        self.assertEqual(len(res["rationales"]), 3)
        # one juror who still calls the line broken is not overruled, the developer decides (it passed with 5 before)
        res = dl.deliberate_line(ENTRY, J3, EVIDENCE, seats([5, 5, 2]), "tr-TR", "SYS", self.scrub)
        self.assertEqual((res["score"], res["status"], res["deliberation"]["critical_holdout"]), (2, "unresolved", True))
        self.assertEqual(len(res["rationales"]), 3)
        res = dl.deliberate_line(ENTRY, J3, EVIDENCE, seats([5, 5, 3]), "tr-TR", "SYS", self.scrub)
        self.assertEqual((res["score"], res["status"]), (5, "pass"))             # a mild doubt does not block a majority

    def test_the_everyday_word_check_keeps_its_weight_in_the_revote(self):
        one = dl.deliberate_line(ENTRY, J3, EVIDENCE, seats([5, 5, 5], ((), ["aletleri"], ())), "tr-TR", "SYS", self.scrub)
        self.assertEqual((one["score"], one["status"]), (5, "pass"))              # one juror's word is evidence only
        two = dl.deliberate_line(ENTRY, J3, EVIDENCE, seats([5, 5, 4], (["sakın"], ["aletleri"], ())), "tr-TR", "SYS", self.scrub)
        self.assertEqual((two["score"], two["status"], two["deliberation"]["revote"]), (3, "rewrite", [3, 3, 3]))
        self.assertIn("2 jurors found words a native would not use every day (sakın, aletleri)", two["rationales"][2])

    def test_unresolved_keeps_three_rationales(self):
        res = dl.deliberate_line(ENTRY, J3, EVIDENCE, seats([5, 3, 2]), "tr-TR", "SYS", self.scrub)
        self.assertEqual(res["status"], "unresolved")
        self.assertEqual(res["rationales"], ["revote 5", "revote 3", "revote 2"])
        self.assertIsNone(res["deliberation"]["majority"])

    def test_anonymity_and_evidence_package(self):
        members = seats([4, 3, 3])
        dl.deliberate_line(ENTRY, J3, EVIDENCE, members, "tr-TR", "SYS", self.scrub)
        for seat in members:
            p = seat.provider.payloads[0]
            self.assertEqual(p["task"], "deliberate")
            self.assertEqual(p["own"]["score"], J3[seat.index]["score"])
            self.assertEqual([o["juror"] for o in p["others"]], ["A", "B"])
            shown = json.dumps(p["others"], ensure_ascii=False).lower()
            for name in MODEL_NAMES:
                self.assertNotRegex(shown, rf"(?<![\w-]){re.escape(name)}(?![\w-])", f"'{name}' leaked to member {seat.index}")
            self.assertNotIn("family", json.dumps(p["others"]))
            self.assertNotIn("model", json.dumps(p["others"]))
            ev = p["evidence"]
            self.assertEqual(ev["ban_hits"], [{"rule": "TR-KNOWN-CALQUE", "message": "calque"}])
            self.assertEqual([n["target"] for n in ev["tm_neighbors"]], ["Onaylı satır 0", "Onaylı satır 1", "Onaylı satır 2"])
            self.assertEqual(ev["roundtrip"], {"applied": True, "calque_score": 0.91, "suspect": True})
            blob = json.dumps(p, ensure_ascii=False)
            self.assertNotIn("SECRET ENGLISH", blob)  # no source text of TM neighbours
            self.assertNotIn("SECRET BACK", blob)
        self.assertEqual(dl.anonymize("Claude and gemini-4-carbon and V4Pro agree", self.scrub),
                         "another juror and another juror and another juror agree")
        self.assertEqual(dl.anonymize("As DeepSeek V4 Pro I disagree", self.scrub), "As another juror I disagree")

    def test_decide(self):
        self.assertEqual(dl.decide([3, 3, 5]), 3)
        self.assertEqual(dl.decide([2, 2, 2]), 2)
        self.assertIsNone(dl.decide([1, 3, 5]))


class IntegrationTests(unittest.TestCase):
    SCEN = {"scores": [
        {"key": "DIS", "tier": "J1", "family": "google", "score": 3},
        {"key": "DIS", "tier": "J2", "family": "google", "score": 3},
        {"key": "DIS", "tier": "J3", "family": "anthropic", "score": 5},
        {"key": "DIS", "tier": "J3", "family": "google", "score": 2, "issue_type": "register", "reason": "Gemini says register"},
        {"key": "DIS", "tier": "J3", "family": "deepseek", "score": 3, "issue_type": "translationese", "reason": "calque"}],
        "deliberate": [{"key": "DIS", "family": "google", "score": 3, "reason": "fine, a calque"}]}

    def _doc(self) -> Dict[str, Any]:
        entries = [dict(ENTRY)] + [{"key": f"F{i}", "target": f"Menü {i}", "category": "ui"} for i in range(19)]
        return {"locale": "tr-TR", "entries": entries}

    def test_jury_runs_deliberation(self):
        router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(self.SCEN))
        with TempDir() as td:
            entries, _ = jury.load_blind_slice(write_json(td / "b.json", self._doc()))
        res = jury.run_jury(entries, "tr-TR", router, system="SYS", deliberator=dl.make_deliberator(router, "tr-TR", "SYS"))
        v = {x["key"]: x for x in res["verdicts"]}["DIS"]
        self.assertEqual((v["final_tier"], v["status"], v["score"]), ("deliberation", "rewrite", 3))
        self.assertEqual(v["deliberation"]["revote"], [5, 3, 3])
        self.assertEqual([x["tier"] for x in v["votes"]].count("deliberation"), 3)

    def test_cli_on_verdict_file(self):
        with TempDir() as td:
            blind = write_json(td / "blind_tr-TR_01.json", self._doc())
            sc = write_json(td / "sc.json", {"scores": self.SCEN["scores"]})
            code, _, err = run_cli("jury.py", str(blind), "--locale", "tr-TR", "--dry-run", "--fake-scenario", str(sc), "--no-deliberation",
                                   "--langpack-dir", str(td / "np"), env_extra=NO_KEYS)
            self.assertEqual(code, 1, err)
            verdicts = td / "verdicts_tr-TR_01.json"
            code, out, err = run_cli("deliberate.py", str(verdicts), "--slice", str(blind), "--locale", "tr-TR", "--dry-run",
                                     "--fake-scenario", str(sc), "--out", str(td / "still.json"), "--langpack-dir", str(td / "np"), env_extra=NO_KEYS)
            self.assertEqual(code, 1, err)  # nobody moves -> still unresolved
            self.assertIn("still unresolved", out)
            sc2 = write_json(td / "sc2.json", self.SCEN)
            code, out, err = run_cli("deliberate.py", str(verdicts), "--slice", str(blind), "--locale", "tr-TR", "--dry-run",
                                     "--fake-scenario", str(sc2), "--langpack-dir", str(td / "np"), "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            doc = json.loads(verdicts.read_text(encoding="utf-8"))
            dis = [v for v in doc["verdicts"] if v["key"] == "DIS"][0]
            self.assertEqual((dis["final_tier"], dis["status"]), ("deliberation", "rewrite"))
            self.assertEqual(doc["stats"]["status"]["unresolved"], 0)
            self.assertEqual(doc["stats"]["deliberation"], {"deliberated": 1, "resolved": 1, "unresolved": 0})

    def test_context_map_on_its_own_and_from_the_config(self):
        # run alone, deliberate.py read no context map before, and like jury.py it never read --config
        import os
        from unittest import mock
        seen: Dict[str, Any] = {}

        def spy(doc, entries, router, locale, system):
            seen["system"], seen["entries"] = system, entries
            return {"deliberated": 0, "resolved": 0, "unresolved": 0}
        with TempDir() as td:
            blind = write_json(td / "blind.json", self._doc())
            verdicts = write_json(td / "v.json", {"verdicts": []})
            ctx = td / "context"
            ctx.mkdir()
            (ctx / "CONTEXT_MAP.md").write_text("MAP-TEXT", encoding="utf-8")
            (ctx / "CONTEXT_MAP.tr-TR.md").write_text("APPENDIX", encoding="utf-8")
            (ctx / "line_notes.json").write_text(json.dumps({"DIS": {"screen": "letter", "notes": "SCOUT"}}), encoding="utf-8")
            cfg = write_json(td / "l10n.config.json", {"context_map": "context/CONTEXT_MAP.md"})
            argv = ["deliberate.py", str(verdicts), "--slice", str(blind), "--locale", "tr-TR", "--dry-run", "--config", str(cfg),
                    "--langpack-dir", str(td / "np")]
            import contextlib
            import io
            with mock.patch.object(dl, "deliberate_verdicts", spy), mock.patch.object(_sys, "argv", argv), mock.patch.dict(os.environ, NO_KEYS), \
                    contextlib.redirect_stdout(io.StringIO()):
                dl.main()
        self.assertIn("MAP-TEXT", seen["system"])
        self.assertNotIn("APPENDIX", seen["system"])                      # jurors never read the locale appendix
        self.assertEqual([e["context"] for e in seen["entries"] if e["key"] == "DIS"], [{"screen": "letter"}])

    def test_exit_2(self):
        with TempDir() as td:
            blind = write_json(td / "b.json", self._doc())
            bad = write_json(td / "v.json", {"nothing": []})
            self.assertEqual(run_cli("deliberate.py", str(bad), "--slice", str(blind), "--locale", "tr-TR", "--dry-run", env_extra=NO_KEYS)[0], 2)
            v = write_json(td / "v2.json", {"verdicts": [{"key": "GHOST", "status": "unresolved", "final_tier": "J3", "votes": J3}]})
            self.assertEqual(run_cli("deliberate.py", str(v), "--slice", str(blind), "--locale", "tr-TR", "--dry-run", env_extra=NO_KEYS)[0], 2)
            code, _, err = run_cli("deliberate.py", str(v), "--slice", str(blind), "--locale", "tr-TR", env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("API_KEY", err)

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertTrue("deliberate.py" in doc, "deliberate.py missing from CLI_REFERENCE.md")
        for script in ("deliberate.py", "jury.py"):
            code, help_text, _ = run_cli(script, "--help")
            self.assertEqual(code, 0)
            for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
                self.assertTrue(flag in doc, f"{script}: {flag} missing from CLI_REFERENCE.md")


if __name__ == "__main__":
    unittest.main()
