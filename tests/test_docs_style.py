"""P15: documentation style and coverage (house punctuation, maps, changelog, versions, CLI surface of every tool)."""
from __future__ import annotations

import json
import re
import unittest

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import REFS, ROOT, SCRIPTS, TESTS_DIR, run_cli  # noqa: E402

import l10n_common  # noqa: E402
import text_style  # noqa: E402

STYLED_DOCS = (
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "README.md",
    ROOT / "README_TR.md",
    ROOT / "CHANGELOG.md",
    SCRIPTS.parent / "SKILL.md",
    REFS / "methodology_and_qa.md",
    SCRIPTS / "CLI_REFERENCE.md",
    TESTS_DIR / "README.md",
    SCRIPTS / "rules" / "custom" / "README.md",
)
NEW_TOOLS = ("providers_check.py", "build_context_map.py", "build_language_pack.py", "warmup_loader.py", "build_contrastive_set.py", "roundtrip_check.py",
             "eval_critic.py", "budget_report.py", "jury.py", "deliberate.py", "tm.py", "pass2_rewrite.py", "report_changes.py")
CLI_SCRIPTS = ("lqa_linter.py", "ui_expansion_checker.py", "font_glyph_scanner.py", "make_blind_slice.py", "validate_critique.py",
               "orchestrator_stub.py") + NEW_TOOLS


class StyleTests(unittest.TestCase):
    def test_house_punctuation(self):
        for path in STYLED_DOCS:
            problems = text_style.punctuation_problems(path.read_text(encoding="utf-8"))
            self.assertEqual(problems, [], f"{path.relative_to(ROOT)}: {problems[:5]}")


class PlaybookStyleTests(unittest.TestCase):
    """Playbooks, agents and rules/AGENTS.md follow the house style. Target-language examples keep their own punctuation."""

    def test_explanations_follow_the_house_style(self):
        files = sorted(REFS.glob("*.md")) + sorted((ROOT / "agents").glob("*.md")) + [ROOT / "rules" / "AGENTS.md"]
        for path in files:
            problems = text_style.punctuation_problems(path.read_text(encoding="utf-8"), exempt_examples=True)
            self.assertEqual(problems, [], f"{path.name}: {problems[:5]}")

    def test_examples_keep_their_punctuation(self):
        de = (REFS / "de-DE.md").read_text(encoding="utf-8")
        self.assertIn("Mach die Kiste schnell wieder flott – das Podium hol ich mir zurück.", de)
        ru = (REFS / "ru-RU.md").read_text(encoding="utf-8")
        self.assertIn("`Реактор — источник энергии.`", ru)

    def test_checker_exempt_mode(self):
        md = '* **Label.** text with *"Beispiel; mit — Zeichen"* and 「例：テスト」 and "quoted: yes"\n* bad; here\n'
        self.assertEqual([n for n, _ in text_style.punctuation_problems(md, exempt_examples=True)], [2])
        self.assertEqual(text_style.punctuation_problems("* **Label:** text\n"), [(1, "colon inside a sentence")])


class CoverageTests(unittest.TestCase):
    def test_new_tools_are_mapped_and_logged(self):
        skill = (SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
        cli = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        methodology = (REFS / "methodology_and_qa.md").read_text(encoding="utf-8")
        for tool in NEW_TOOLS:
            self.assertIn(f"](./scripts/{tool})", skill, f"{tool} missing from the SKILL.md map")
            self.assertIn(f"## {tool} (", cli, f"{tool} has no CLI_REFERENCE section")
            self.assertIn(f"`scripts/{tool}`", changelog, f"{tool} missing from CHANGELOG")
        for word in ("Deliberation", "J1", "J2", "J3", "Budget caps", "Trust levels", "Language packs"):
            self.assertIn(word, methodology)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Multi-Family Jury (2.2)", readme)

    def test_readme_translations_move_together(self):
        en = (ROOT / "README.md").read_text(encoding="utf-8")
        tr = (ROOT / "README_TR.md").read_text(encoding="utf-8")

        def headings(text: str, level: str) -> list:
            body = re.sub(r"(?ms)^```.*?^```", "", text)   # a '# comment' inside a code block is not a heading
            return re.findall(rf"(?m)^{level} \S.*$", body)
        self.assertEqual(len(headings(en, "##")), len(headings(tr, "##")), "README.md and README_TR.md have different sections")
        self.assertEqual(len(headings(en, "###")), len(headings(tr, "###")))
        self.assertIn("](./README_TR.md)", en)
        self.assertIn("](./README.md)", tr)
        self.assertIn("## Çok Aileli Jüri (2.2)", tr)
        self.assertEqual(re.findall(r"```(\w*)", en), re.findall(r"```(\w*)", tr), "code blocks differ")

    def test_agent_guide_is_the_first_read(self):
        guide = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("\n@AGENTS.md", claude)                        # Claude Code imports the shared guide
        job_a = guide.split("### A.")[1].split("### B.")[0]
        steps = re.findall(r"(?m)^(\d)\. (.*)$", job_a)
        self.assertIn("SKILL.md", steps[0][1])
        self.assertIn("Context map first", steps[1][1])              # the map is the first real step
        for word in ("context-cartographer", "Opus", "context-scout", "Sonnet", "ask the user"):
            self.assertIn(word, steps[1][1])
        for rule in ("Context decides every word", "Ask, do not guess", "API keys", "Tests never call a real API", "House punctuation style"):
            self.assertIn(rule, guide)
        for target in re.findall(r"\]\(\./([^)#]+)\)", guide):            # every link of the guide resolves
            self.assertTrue((ROOT / target).exists(), target)

    def test_every_test_module_is_listed(self):
        listing = (TESTS_DIR / "README.md").read_text(encoding="utf-8")
        for path in sorted(TESTS_DIR.glob("test_*.py")):
            self.assertIn(f"`{path.name}`", listing, f"{path.name} missing from tests/README.md")

    def test_versions_agree(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], l10n_common.__version__)
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertEqual(re.search(r"(?m)^## \[(\d+\.\d+\.\d+)\]", changelog).group(1), l10n_common.__version__)
        cli = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertIn(f"(v{l10n_common.__version__})", cli.splitlines()[0])


class CliSurfaceTests(unittest.TestCase):
    def test_every_tool_help_version_flags(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        for script in CLI_SCRIPTS:
            code, help_text, err = run_cli(script, "--help")
            self.assertEqual(code, 0, f"{script} --help: {err}")
            for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
                self.assertTrue(flag in doc, f"{script}: {flag} missing from CLI_REFERENCE.md")
            code, out, err = run_cli(script, "--version")
            self.assertEqual(code, 0)
            self.assertIn(l10n_common.__version__, out + err)
            code, _, _ = run_cli(script, env_extra={"GCL_OFFLINE": "1"})
            self.assertEqual(code, 2, f"{script} without arguments should exit 2")


if __name__ == "__main__":
    unittest.main()
