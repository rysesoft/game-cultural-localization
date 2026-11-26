"""P5: build_contrastive_set.py (native / robot / unknown pairs, B3.5)."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, Dict, List

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS, TempDir, run_cli, write_text  # noqa: E402

import build_contrastive_set as bcs  # noqa: E402
from l10n_common import L10nError  # noqa: E402
from providers import ChatResult, FakeProvider, envelope, extract_json, split_envelope  # noqa: E402

NO_KEYS = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "", "GCL_OFFLINE": "1"}
REF = ("key,en,tr-TR,category,speaker,archetype\n"
       "UI_SAVE,Save,Kaydet,ui,,\n"
       "DLG_1,Take your time kid.,Acele etme evlat.,dialogue,Mentor,A1\n"
       "TIP_1,Use {0} to jump,Zıplamak için {0} tuşuna bas,tutorial,,\n"
       "LTR_1,We regret to inform you.,Üzülerek bildiririz.,letter,Bank,\n"
       "EMPTY,Nothing here,,ui,,\n")


class SpyProvider:
    """Records system prompts and answers with a fixed mapping or a marker."""

    def __init__(self, model: str, mapping: Dict[str, str] = None) -> None:
        self.model = model
        self.mapping = mapping or {}
        self.systems: List[str] = []

    def complete(self, system: str, user: str, **kw: Any) -> ChatResult:
        self.systems.append(system)
        _i, p = split_envelope(user)
        rows = [{"key": r["key"], "target": self.mapping.get(r["key"], f"<{self.model}> {r['source']}")} for r in p["rows"]]
        return ChatResult(json.dumps({"rows": rows}, ensure_ascii=False), 1, 1, self.model, 0)


class BuildTests(unittest.TestCase):
    def _rows(self, td: Path) -> List[Dict[str, Any]]:
        return bcs.load_reference_rows(write_text(td / "ref.csv", REF), "tr-TR")

    def test_reference_loading_and_registers(self):
        with TempDir() as td:
            rows = self._rows(td)
        self.assertEqual([r["key"] for r in rows], ["UI_SAVE", "DLG_1", "TIP_1", "LTR_1"])  # empty target skipped
        regs = {r["key"]: r["register"] for r in rows}
        self.assertEqual(regs, {"UI_SAVE": "ui", "DLG_1": "dialogue_casual", "TIP_1": "tutorial", "LTR_1": "dialogue_formal"})
        self.assertEqual(rows[1]["archetype"], "A1")

    def test_pairs_schema_and_literal_prompt(self):
        with TempDir() as td:
            rows = self._rows(td)
        robot = SpyProvider("robot-m", {"UI_SAVE": "Kaydet", "TIP_1": "Kullan zıplamak için"})
        unk = SpyProvider("strong-m")
        pairs, stats = bcs.build_contrastive(rows, "tr-TR", robot, {"strong-m": unk})
        self.assertIn("word for word", robot.systems[0])            # prompts/literal.md was used
        self.assertIn("tr-TR", robot.systems[0])
        self.assertNotIn("word for word", unk.systems[0])           # unknown lines use the plain pass1 prompt
        self.assertEqual(stats["dropped"], {"robot_equals_native": 1, "robot_broke_placeholders": 1})
        self.assertEqual([p["key"] for p in pairs], ["DLG_1", "LTR_1"])
        p = pairs[0]
        self.assertEqual(set(p), {"key", "en", "native", "robot", "unknown", "register", "speaker", "archetype"})
        self.assertEqual(p["native"], "Acele etme evlat.")
        self.assertEqual(p["robot"], "<robot-m> Take your time kid.")
        self.assertEqual(p["unknown"], {"strong-m": "<strong-m> Take your time kid."})

    def test_seeded_limit(self):
        rows = [{"key": f"K{i}", "en": "x", "native": "y", "register": "ui", "speaker": "", "archetype": ""} for i in range(50)]
        a = bcs.select_rows(rows, 10, 7)
        self.assertEqual(a, bcs.select_rows(rows, 10, 7))
        self.assertNotEqual(a, bcs.select_rows(rows, 10, 8))
        self.assertEqual([r["key"] for r in a], sorted([r["key"] for r in a], key=lambda k: int(k[1:])))
        self.assertEqual(len(bcs.select_rows(rows, 0, 7)), 50)

    def test_missing_target_column(self):
        with TempDir() as td:
            path = write_text(td / "ref.csv", "key,en,fr\nA,Save,Sauver\n")
            with self.assertRaises(L10nError):
                bcs.load_reference_rows(path, "tr-TR")


class CliTests(unittest.TestCase):
    def test_dry_run_exit_0_deterministic_and_budget(self):
        with TempDir() as td:
            ref = write_text(td / "ref.csv", REF)
            args = [str(ref), "--locale", "tr", "--out", str(td / "c.json"), "--dry-run", "--min-pairs", "3", "--json"]
            code, out, err = run_cli("build_contrastive_set.py", *args, env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            first = (td / "c.json").read_text(encoding="utf-8")
            data = json.loads(first)
            self.assertEqual(data["locale"], "tr-TR")
            self.assertEqual(data["source_ref"], str(ref))
            self.assertEqual(len(data["pairs"]), 4)
            self.assertEqual(data["pairs"][0]["robot"], "[tr-TR literal] Save")
            self.assertEqual(data["pairs"][0]["unknown"], {"claude-sonnet-5-5": "[tr-TR] Save"})
            budget = [json.loads(l) for l in (td / "budget.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual({b["role"] for b in budget}, {"literal", "pass1"})
            self.assertEqual({b["model"] for b in budget}, {"deepseek-flash", "claude-sonnet-5-5"})
            run_cli("build_contrastive_set.py", *args, env_extra=NO_KEYS)
            self.assertEqual((td / "c.json").read_text(encoding="utf-8"), first)

    def test_unknown_models_flag_and_exit_1(self):
        with TempDir() as td:
            ref = write_text(td / "ref.csv", REF)
            code, out, err = run_cli("build_contrastive_set.py", str(ref), "--locale", "tr-TR", "--out", str(td / "c.json"), "--dry-run",
                                     "--unknown-models", "sonnet,neon", "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 1, err)  # 4 pairs < default --min-pairs 30
            data = json.loads((td / "c.json").read_text(encoding="utf-8"))
            self.assertEqual(set(data["pairs"][0]["unknown"]), {"claude-sonnet-5-5", "gemini-4-neon"})
            code, _, _ = run_cli("build_contrastive_set.py", str(ref), "--locale", "tr-TR", "--out", str(td / "d.json"), "--dry-run",
                                 "--no-unknown", "--min-pairs", "1", env_extra=NO_KEYS)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads((td / "d.json").read_text(encoding="utf-8"))["pairs"][0]["unknown"], {})

    def test_exit_2(self):
        with TempDir() as td:
            ref = write_text(td / "ref.csv", REF)
            code, _, err = run_cli("build_contrastive_set.py", str(ref), "--locale", "tr-TR", "--out", str(td / "c.json"), env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("DEEPSEEK_API_KEY", err)
            self.assertEqual(run_cli("build_contrastive_set.py", str(ref), "--locale", "xx", "--dry-run", env_extra=NO_KEYS)[0], 2)
            self.assertEqual(run_cli("build_contrastive_set.py", str(ref), "--locale", "tr-TR", "--dst-field", "nope", "--dry-run",
                                     "--out", str(td / "c.json"), env_extra=NO_KEYS)[0], 2)
            self.assertEqual(run_cli("build_contrastive_set.py", str(ref), "--locale", "tr-TR", "--unknown-models", "gpt", "--dry-run",
                                     "--out", str(td / "c.json"), env_extra=NO_KEYS)[0], 2)

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertTrue("build_contrastive_set.py" in doc, "build_contrastive_set.py missing from CLI_REFERENCE.md")
        code, help_text, _ = run_cli("build_contrastive_set.py", "--help")
        self.assertEqual(code, 0)
        for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
            self.assertTrue(flag in doc, f"build_contrastive_set.py: {flag} missing from CLI_REFERENCE.md")


if __name__ == "__main__":
    unittest.main()
