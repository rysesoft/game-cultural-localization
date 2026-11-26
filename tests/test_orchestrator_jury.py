"""P14: orchestrator_stub.py jury flow (Phase 0-3 end to end with the fake provider) and the legacy --provider flow."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import TempDir, run_cli, write_json, write_text  # noqa: E402

import orchestrator_stub as orch  # noqa: E402
import text_style  # noqa: E402
import tm as tmmod  # noqa: E402
from providers import FakeScenario, Router, load_providers_config  # noqa: E402

NO_KEYS = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "", "GCL_OFFLINE": "1"}
SOURCE = [
    {"key": "BTN_SAVE", "en": "Save your progress", "category": "ui"},
    {"key": "DLG_1", "en": "Take your time, kid. The generator is not going anywhere tonight.", "category": "dialogue", "speaker": "Mentor"},
    {"key": "TIP_1", "en": "Press <b>X</b> to use {0}", "category": "tutorial"},
]
SCENARIO = {"scores": [{"key": "DLG_1", "tier": "J1", "score": 3, "issue_type": "translationese", "reason": "English word order"},
                       {"key": "DLG_1", "tier": "J2", "score": 3, "issue_type": "translationese", "reason": "still a calque"},
                       {"key": "DLG_1", "tier": "J3", "score": 3, "issue_type": "translationese", "reason": "agreed calque"}],
            "pass2": [{"key": "DLG_1", "candidates": ["Acele etme evlat, jeneratör bu gece hiçbir yere kaçmıyor.",
                                                     "Yavaş ol evlat, jeneratör kaçmıyor ya.", "Sakin evlat, jeneratör burada."]}],
            "picks": [{"contains": "Acele etme", "prefer": "Acele etme"}]}


class JuryFlowTests(unittest.TestCase):
    def test_dry_run_end_to_end(self):
        with TempDir() as td:
            src = write_json(td / "src.json", SOURCE)
            sc = write_json(td / "sc.json", SCENARIO)
            code, out, err = run_cli("orchestrator_stub.py", "--dry-run", "--locale", "tr-TR", "--input", str(src), "--workdir", str(td / "w"),
                                     "--fake-scenario", str(sc), "--no-budget-caps", "--langpack-dir", str(td / "np"), "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 0, err + out)
            data = json.loads(out)
            self.assertEqual(data["flow"], "jury")
            self.assertTrue(data["passed"])
            self.assertEqual(data["trust_level"], "rule_based")
            w = td / "w"
            for name in ("tr-TR_BIBLE.md", "pass1_batch_01.json", "blind_tr-TR_01.json", "verdicts_tr-TR_01.json", "rewrites_tr-TR_01.json",
                         "final_batch_01.json", "changes_tr-TR_01.json", "changes_tr-TR_01.md", "budget.jsonl"):
                self.assertTrue((w / name).is_file(), name)
            blind = json.loads((w / "blind_tr-TR_01.json").read_text(encoding="utf-8"))
            self.assertNotIn("en", blind["entries"][0])
            verdicts = {v["key"]: v for v in json.loads((w / "verdicts_tr-TR_01.json").read_text(encoding="utf-8"))["verdicts"]}
            self.assertEqual((verdicts["DLG_1"]["final_tier"], verdicts["DLG_1"]["status"]), ("J3", "rewrite"))
            self.assertEqual(verdicts["BTN_SAVE"]["status"], "pass")
            final = {r["key"]: r["tr-TR"] for r in json.loads((w / "final_batch_01.json").read_text(encoding="utf-8"))}
            self.assertEqual(final["DLG_1"], "Acele etme evlat, jeneratör bu gece hiçbir yere kaçmıyor.")
            self.assertEqual(final["BTN_SAVE"], "[tr-TR] Save your progress")
            rep = json.loads((w / "changes_tr-TR_01.json").read_text(encoding="utf-8"))
            self.assertEqual([l["key"] for l in rep["lines"]], ["DLG_1"])
            self.assertEqual(text_style.punctuation_problems((w / "changes_tr-TR_01.md").read_text(encoding="utf-8")), [])
            roles = {json.loads(l)["role"] for l in (w / "budget.jsonl").read_text(encoding="utf-8").splitlines()}
            self.assertTrue({"pass1", "J1", "J2", "J3", "roundtrip", "pass2"} <= roles)
            self.assertIn("Phase 3: gate PASSED", out)

    def test_deterministic(self):
        with TempDir() as td:
            src = write_json(td / "src.json", SOURCE)
            router_a = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(SCENARIO))
            router_b = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(SCENARIO))
            a = orch.run_jury_pipeline(src, "tr-TR", td / "a", router_a, budget_caps=False, langpack_dir=td / "np", workers=1)
            b = orch.run_jury_pipeline(src, "tr-TR", td / "b", router_b, budget_caps=False, langpack_dir=td / "np", workers=4)  # parallel run, same files
            self.assertEqual(a["summary"], b["summary"])
            for name in ("final_batch_01.json", "verdicts_tr-TR_01.json", "changes_tr-TR_01.md"):
                self.assertEqual((td / "a" / name).read_text(encoding="utf-8"), (td / "b" / name).read_text(encoding="utf-8"), name)

    def test_budget_cap_stops_and_reports(self):
        with TempDir() as td:
            src = write_json(td / "src.json", SOURCE)
            router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(SCENARIO))
            res = orch.run_jury_pipeline(src, "tr-TR", td / "w", router, langpack_dir=td / "np")
            self.assertFalse(res["passed"])
            self.assertEqual(res["halted"]["stage"], "J2")             # 1 of 3 lines to J2 is above 30 %
            self.assertFalse((td / "w" / "final_batch_01.json").exists())
            self.assertTrue((td / "w" / "changes_tr-TR_01.md").is_file())
            self.assertTrue(res["summary"]["halted"])
            self.assertIn("Phase 3: skipped", "\n".join(res["log"]))

    def test_unresolved_line_fails_the_run(self):
        sc = {"scores": [{"key": "DLG_1", "tier": "J1", "score": 3}, {"key": "DLG_1", "tier": "J2", "score": 3},
                         {"key": "DLG_1", "tier": "J3", "family": "anthropic", "score": 5},
                         {"key": "DLG_1", "tier": "J3", "family": "google", "score": 2},
                         {"key": "DLG_1", "tier": "J3", "family": "deepseek", "score": 3}]}
        with TempDir() as td:
            src = write_json(td / "src.json", SOURCE)
            router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(sc))
            res = orch.run_jury_pipeline(src, "tr-TR", td / "w", router, budget_caps=False, langpack_dir=td / "np")
            self.assertEqual(res["unresolved"], 1)
            self.assertTrue(res["summary"]["passed"])
            self.assertFalse(res["passed"])
            final = {r["key"]: r["tr-TR"] for r in json.loads((td / "w" / "final_batch_01.json").read_text(encoding="utf-8"))}
            self.assertEqual(final["DLG_1"], "[tr-TR] " + SOURCE[1]["en"])  # unresolved keeps the Pass 1 text

    def test_tm_rag_and_evidence(self):
        with TempDir() as td:
            db = td / "tm.sqlite"
            with tmmod.TranslationMemory(db) as t:
                t.add("tr-TR", "OLD_DLG", "Take your time, kid. The generator is not going anywhere.", "Acele etme evlat, jeneratör kaçmıyor.",
                      category="dialogue", speaker="Mentor", status="approved")
            src = write_json(td / "src.json", SOURCE)
            router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(SCENARIO))
            res = orch.run_jury_pipeline(src, "tr-TR", td / "w", router, budget_caps=False, tm_path=db, langpack_dir=td / "np")
            self.assertIn("TM neighbours for 1", "\n".join(res["log"]))
            v = {x["key"]: x for x in json.loads((td / "w" / "verdicts_tr-TR_01.json").read_text(encoding="utf-8"))["verdicts"]}
            self.assertEqual(v["DLG_1"]["evidence"]["tm_neighbors"][0]["key"], "OLD_DLG")
            self.assertTrue(v["DLG_1"]["evidence"]["roundtrip"]["applied"])

    def test_language_pack_warmup_used(self):
        with TempDir() as td:
            pack = td / "packs" / "tr-TR"
            pack.mkdir(parents=True)
            write_text(pack / "warmup.jsonl", "".join(json.dumps({"text": f"Hadi gidelim {i}!", "register": "dialogue_casual", "source": "reference",
                                                                  "license_class": "bundle"}, ensure_ascii=False) + "\n" for i in range(5)))
            write_json(pack / "trust_card.json", {"trust_level": "estimated", "langpack_version": "tr-TR-x"})
            src = write_json(td / "src.json", SOURCE)
            router = Router(load_providers_config(), dry_run=True)
            res = orch.run_jury_pipeline(src, "tr-TR", td / "w", router, langpack_dir=td / "packs")
            self.assertEqual(res["trust_level"], "estimated")
            self.assertIn("warm-up 5 lines", "\n".join(res["log"]))
            self.assertTrue(res["passed"])


class CliModeTests(unittest.TestCase):
    def test_legacy_provider_still_works(self):
        with TempDir() as td:
            write_text(td / "legacy_llm.py", (
                "import json\n"
                "def complete(system, user):\n"
                "    payload = json.loads(user.split('\\n---\\n', 1)[1])\n"
                "    if payload.get('task') == 'critique':\n"
                "        return json.dumps({'locale': payload['locale'], 'source_file': payload['source_file'], 'entries': [],\n"
                "                           'summary': {'total': len(payload['entries']), 'flagged': 0, 'critical': 0}})\n"
                "    return json.dumps({'rows': [{'key': r['key'], 'target': 'Kaydet'} for r in payload['rows']]})\n"))
            src = write_json(td / "src.json", [{"key": "A", "en": "Save"}])
            code, out, err = run_cli("orchestrator_stub.py", "--provider", "legacy_llm:complete", "--locale", "tr-TR", "--input", str(src),
                                     "--workdir", str(td / "w"), "--json", env_extra={**NO_KEYS, "PYTHONPATH": str(td)})
            self.assertEqual(code, 0, err)
            data = json.loads(out)
            self.assertEqual(data["flow"], "legacy")
            self.assertTrue((td / "w" / "critique_tr-TR_01.json").is_file())

    def test_mode_errors(self):
        with TempDir() as td:
            src = write_json(td / "src.json", [{"key": "A", "en": "Save"}])
            code, _, err = run_cli("orchestrator_stub.py", "--live", "--locale", "tr-TR", "--input", str(src), "--workdir", str(td / "w"), env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("API_KEY", err)
            code, _, err = run_cli("orchestrator_stub.py", "--dry-run", "--live", "--locale", "tr-TR", "--input", str(src), "--workdir", str(td / "w"),
                                   env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("choose one", err)
            code, _, err = run_cli("orchestrator_stub.py", "--locale", "tr-TR", "--input", str(src), "--workdir", str(td / "w"), env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("--live", err)
            code, _, err = run_cli("orchestrator_stub.py", "--dry-run", "--locale", "tr-TR", "--input", str(src), "--workdir", str(td / "w"),
                                   "--tm", str(td / "missing.sqlite"), env_extra=NO_KEYS)
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
