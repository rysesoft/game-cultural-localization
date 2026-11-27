"""Tests for the Antigravity workflow template, the orchestrator stub and the CLI surface (--help/--version)."""
from __future__ import annotations

import ast
import json
import re
import unittest

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import FIXTURES, SCRIPTS, TempDir, run_cli, write_json  # noqa: E402

import orchestrator_stub as orch  # noqa: E402

ALL_SCRIPTS = ("lqa_linter.py", "ui_expansion_checker.py", "font_glyph_scanner.py", "make_blind_slice.py", "validate_critique.py", "orchestrator_stub.py")


class WorkflowTemplateTests(unittest.TestCase):
    PATH = SCRIPTS / "localization_pipeline_template.workflow.py"

    def test_compiles_with_top_level_await(self):
        src = self.PATH.read_text(encoding="utf-8")
        compile(src, str(self.PATH), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        with self.assertRaises(SyntaxError):
            compile(src, str(self.PATH), "exec")  # documents why the file is not plain Python

    def test_phases_and_scripts(self):
        src = self.PATH.read_text(encoding="utf-8")
        for ph in ("Phase 0", "Phase 1", "Phase 2", "Phase 3"):
            self.assertIn(ph, src)
        for script in ("lqa_linter.py", "ui_expansion_checker.py", "font_glyph_scanner.py", "make_blind_slice.py", "validate_critique.py"):
            self.assertIn(script, src)
            self.assertTrue((SCRIPTS / script).is_file(), script)
        self.assertIn("--fail-on-error", src)
        self.assertIn("--fail-on-high", src)
        self.assertIn("_BIBLE.md", src)
        self.assertIn("pipeline(", src)  # retry path for failed batches
        tree = ast.parse(src, feature_version=(3, 9), type_comments=False) if hasattr(ast, "parse") else None
        self.assertIsNotNone(tree)
        self.assertFalse((SCRIPTS / "localization_pipeline_template.py").exists())

    def test_prompts_follow_the_context_map_first_rule(self):
        # the template runs on the Antigravity runtime, here a fake runtime records every prompt it sends
        import asyncio
        prompts: list = []

        async def agent(prompt, **kw):
            prompts.append((kw.get("role", ""), prompt))
            return {"ok": True, "file": "x", "errors": []}

        async def parallel(items, fn):
            return [await fn(b) for b in items]
        env = {"args": {"locale": "tr-TR", "batches": ["01"], "scratch_dir": "loc_work", "plugin_dir": "P"},
               "agent": agent, "parallel": parallel, "pipeline": parallel, "phase": lambda *a: None, "log": lambda *a: None}
        code = compile(self.PATH.read_text(encoding="utf-8"), str(self.PATH), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        coro = eval(code, env)
        if coro is not None:
            asyncio.run(coro)
        by_role = {role: p for role, p in prompts}
        everything = " ".join(p for _, p in prompts).lower()
        self.assertNotRegex(everything, r"locked (glossary|terminolog|term)")    # no term is ever locked in a list
        self.assertIn("no term is locked in a list", everything)
        pre = by_role["tr-TR pre-flight"]
        self.assertLess(pre.index("loc_work/context/CONTEXT_MAP.md exists"), pre.index("Validate"))   # the map check comes first
        pass1 = by_role["tr-TR Pass-1 Culturalizer 01"]
        for part in ("loc_work/context/CONTEXT_MAP.md", "loc_work/context/CONTEXT_MAP.tr-TR.md", "loc_work/context/line_notes.json"):
            self.assertIn(part, pass1)
        critic = by_role["tr-TR Blind Critic 01"]
        self.assertIn("loc_work/context/CONTEXT_MAP.md", critic)
        self.assertIn("never loc_work/context/CONTEXT_MAP.tr-TR.md", critic)    # the appendix would hand the critic the answer key
        self.assertIn("player_action", critic)
        self.assertIn("CONTEXT_MAP.tr-TR.md", by_role["tr-TR Pass-2 Editor 01"])
        self.assertIn("--context-cols category,speaker,archetype", by_role["tr-TR blind-slice builder"])


class OrchestratorTests(unittest.TestCase):
    def test_dry_run_passes_and_is_deterministic(self):
        with TempDir() as td:
            src = write_json(td / "src.json", [
                {"key": "BTN_APPLY", "en": "APPLY", "category": "ui"},
                {"key": "DLG_1", "en": "Patch her up quick, {0}!", "speaker": "A2"},
                {"key": "TIP", "en": "Press <b>X</b> to jump"},
            ])
            r1 = orch.run_pipeline(src, "de-DE", td / "out1", orch.DryRunProvider("de-DE"), batch_size=2)
            self.assertTrue(r1["passed"], r1)
            self.assertEqual(len(r1["finals"]), 2)
            self.assertTrue((td / "out1" / "de-DE_BIBLE.md").is_file())
            self.assertTrue((td / "out1" / "blind_de-DE_01.json").is_file())
            blind = json.loads((td / "out1" / "blind_de-DE_01.json").read_text(encoding="utf-8"))
            self.assertNotIn("en", blind["entries"][0])
            self.assertEqual(blind["entries"][0]["key"], "BTN_APPLY")
            r2 = orch.run_pipeline(src, "de-DE", td / "out2", orch.DryRunProvider("de-DE"), batch_size=2)
            self.assertEqual(r1["summary"], r2["summary"])
            self.assertEqual((td / "out1" / "final_batch_01.json").read_text(encoding="utf-8"), (td / "out2" / "final_batch_01.json").read_text(encoding="utf-8"))

    def test_gate_fails_on_bad_provider_output(self):
        class BadProvider:
            def complete(self, system, user):
                payload = json.loads(user.split("\n---\n", 1)[1])
                if payload.get("task") == "critique":
                    return json.dumps({"locale": "de-DE", "source_file": "x", "entries": [], "summary": {"total": len(payload["entries"]), "flagged": 0, "critical": 0}})
                return json.dumps({"rows": [{"key": r["key"], "target": "Fokussieren ohne Platzhalter"} for r in payload["rows"]]})
        with TempDir() as td:
            src = write_json(td / "src.json", [{"key": "A", "en": "Use {0}"}])
            r = orch.run_pipeline(src, "de-DE", td / "out", BadProvider())
            self.assertFalse(r["passed"])
            self.assertGreater(r["summary"]["errors"], 0)

    def test_invalid_critique_aborts(self):
        class BadCritic:
            def complete(self, system, user):
                payload = json.loads(user.split("\n---\n", 1)[1])
                if payload.get("task") == "critique":
                    return "not json"
                return json.dumps({"rows": [{"key": r["key"], "target": "Speichern"} for r in payload["rows"]]})
        with TempDir() as td:
            src = write_json(td / "src.json", [{"key": "A", "en": "Save"}])
            with self.assertRaises(orch.L10nError):
                orch.run_pipeline(src, "de-DE", td / "out", BadCritic())

    def test_system_prompt_is_plain_text(self):
        sp = orch.system_prompt("game-culturalizer", "de-DE", "")
        self.assertNotIn("\n---\nname:", sp)
        self.assertIn("A1", sp)

    def test_cli_dry_run(self):
        with TempDir() as td:
            src = write_json(td / "src.json", [{"key": "A", "en": "Save"}])
            code, out, err = run_cli("orchestrator_stub.py", "--dry-run", "--locale", "fr", "--input", str(src), "--workdir", str(td / "w"), "--json")
            self.assertEqual(code, 0, err)
            self.assertTrue(json.loads(out)["passed"])
            code, _, err = run_cli("orchestrator_stub.py", "--locale", "fr", "--input", str(src), "--workdir", str(td / "w"))
            self.assertEqual(code, 2)
            self.assertIn("--dry-run", err)


class CliSurfaceTests(unittest.TestCase):
    def test_help_and_version(self):
        for script in ALL_SCRIPTS:
            code, out, err = run_cli(script, "--help")
            self.assertEqual(code, 0, f"{script} --help: {err}")
            self.assertIn("usage:", out)
            code, out, err = run_cli(script, "--version")
            self.assertEqual(code, 0, f"{script} --version: {err}")
            self.assertRegex(out.strip() + err.strip(), r"\d+\.\d+\.\d+")
            code, _, err = run_cli(script)
            self.assertEqual(code, 2, f"{script} without args should exit 2")

    def test_cli_reference_documents_every_flag(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        for script in ALL_SCRIPTS:
            self.assertIn(script, doc)
            _, help_text, _ = run_cli(script, "--help")
            for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
                self.assertIn(flag, doc, f"{script}: {flag} missing from CLI_REFERENCE.md")
        self.assertIn("localization_pipeline_template.workflow.py", doc)


if __name__ == "__main__":
    unittest.main()
