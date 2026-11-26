"""P4: native critic prompts (tr-TR, de-DE), literal.md, template rendering and the house punctuation style."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS, TempDir, write_text  # noqa: E402

import prompt_templates as pt  # noqa: E402
import text_style  # noqa: E402
from l10n_common import L10nError  # noqa: E402
from llm_tasks import ISSUE_TYPES  # noqa: E402

PROMPTS = SCRIPTS.parent / "prompts"
NATIVE = {
    "tr-TR": {"words": ("oyuncu", "puan", "satır", "değil", "görev", "çıktı", "hitap", "kulağ"), "chars": "çğışöüİ",
              "persona": "çevirmen değilsin"},
    "de-DE": {"words": ("Spieler", "Punkte", "Zeile", "nicht", "Reihenfolge", "Ausgabe", "Anrede", "Ohr"), "chars": "äöüß",
              "persona": "kein Übersetzer"},
}
ENGLISH_PROMPT_MARKERS = ("You are", "Score every", "Reply with", "Rules", "Task order", "Who you are")


class CriticPromptTests(unittest.TestCase):
    def test_native_prompts_exist_and_are_in_the_target_language(self):
        for loc, spec in NATIVE.items():
            tpl = pt.find_prompt("critic", loc)
            self.assertTrue(tpl.native, loc)
            self.assertEqual(tpl.meta["locale"], loc)
            body = tpl.body
            prose = text_style.prose_only(body)
            folded = prose.casefold()
            for w in spec["words"]:
                self.assertTrue(w.casefold() in folded, f"{loc}: '{w}' missing")
            self.assertGreaterEqual(sum(prose.count(c) for c in spec["chars"]), 40, f"{loc}: too few native characters")
            for marker in ENGLISH_PROMPT_MARKERS:
                self.assertFalse(marker in prose, f"{loc}: English prompt text '{marker}' in the body")
            self.assertIn(spec["persona"], body)  # persona: a player, not a translator

    def test_structure_slots_rubric_order_schema(self):
        for loc in NATIVE:
            body = pt.find_prompt("critic", loc).body
            self.assertEqual(body.count("{{WARMUP}}"), 1, loc)
            self.assertEqual(body.count("{{CONTRASTIVE}}"), 1, loc)
            for score in range(1, 6):
                self.assertRegex(body, rf"(?m)^\| {score} \|", f"{loc}: rubric row {score}")
            steps = re.findall(r"(?m)^(\d)\. ", body)
            self.assertEqual(steps, [str(i) for i in range(1, 8)], f"{loc}: task order")
            for field in ("key", "score", "issue_type", "reason", "suggested", "votes"):
                self.assertIn(f'"{field}"', body, f"{loc}: schema field {field}")
            for it in ISSUE_TYPES:
                self.assertIn(f"`{it}`", body, f"{loc}: issue type {it}")
            for harness_field in ("tier", "member", "family", "model"):
                self.assertIn(f"`{harness_field}`", body)

    def test_render_fills_slots(self):
        text = pt.render_prompt("critic", "tr-TR", warmup="[ui]\n- Kaydet", contrastive="1. ✓ a\n   ✗ b")
        self.assertIn("- Kaydet", text)
        self.assertIn("✓ a", text)
        self.assertNotIn("{{", text)
        empty = pt.render_prompt("critic", "de-DE")
        self.assertIn("keine Aufwärmzeilen", empty)
        self.assertIn("keine Gegenpaare", empty)

    def test_generic_fallback_for_other_locales(self):
        with TempDir() as td:  # every bundled locale has its own prompt, so the fallback is tested in a folder with only the generic one
            write_text(td / "critic.generic.md", (PROMPTS / "critic.generic.md").read_text(encoding="utf-8"))
            tpl = pt.find_prompt("critic", "fr", prompts_dir=td)
            self.assertFalse(tpl.native)
            text = pt.render_prompt("critic", "fr", prompts_dir=td)
        self.assertIn("fr game text jury", text)
        self.assertNotIn("{{", text)

    def test_unknown_slot_and_missing_template(self):
        with TempDir() as td:
            write_text(td / "x.tr-TR.md", "---\nname: x\n---\nHello {{MYSTERY}}\n")
            with self.assertRaises(L10nError):
                pt.render_prompt("x", "tr-TR", prompts_dir=td)
            self.assertIn("ok", pt.render_prompt("x", "tr-TR", prompts_dir=td, extra={"MYSTERY": "ok"}))
            with self.assertRaises(L10nError):
                pt.find_prompt("nothing", "tr-TR", prompts_dir=td)


class LiteralPromptTests(unittest.TestCase):
    def test_literal_instructions(self):
        tpl = pt.find_prompt("literal", "tr-TR")
        self.assertEqual(tpl.path.name, "literal.md")
        body = tpl.body.lower()
        for needle in ("word for word", "word order", "idioms", "placeholder", "pronoun", "passive"):
            self.assertIn(needle, body)
        text = pt.render_prompt("literal", "tr-TR")
        self.assertIn("into tr-TR", text)
        self.assertIn('"rows"', text)


class ContrastiveRenderTests(unittest.TestCase):
    def test_seeded_and_marked(self):
        pairs = [{"key": f"K{i}", "native": f"doğal {i}", "robot": f"robot {i}"} for i in range(20)]
        pairs.append({"key": "SAME", "native": "aynı", "robot": "aynı"})
        a = pt.render_contrastive(pairs, count=5, seed=3)
        self.assertEqual(a, pt.render_contrastive(list(reversed(pairs)), count=5, seed=3))
        self.assertNotEqual(a, pt.render_contrastive(pairs, count=5, seed=4))
        self.assertEqual(a.count("✓"), 5)
        self.assertEqual(a.count("✗"), 5)
        self.assertNotIn("aynı", a)
        self.assertEqual(pt.render_contrastive([]), "")


class PunctuationStyleTests(unittest.TestCase):
    def test_prompt_files_follow_the_house_style(self):
        for path in sorted(PROMPTS.glob("*.md")):
            self.assertEqual(text_style.punctuation_problems(path.read_text(encoding="utf-8")), [], path.name)

    def test_checker_and_sanitizer(self):
        bad = "Intro: text\nA; b\nC — d\n`code; ok: yes`\n```\nx; y: z\n```\nTime 12:30 is fine\nhttps://x.org/a:b\n|---|---|\n"
        lines = [n for n, _ in text_style.punctuation_problems(bad)]
        self.assertEqual(lines, [1, 2, 3])
        self.assertEqual(text_style.sanitize_prose("Calque: English order; stiff — rewrite."), "Calque, English order, stiff, rewrite.")
        self.assertEqual(text_style.punctuation_problems(text_style.sanitize_prose("a: b; c – d")), [])


# characteristic characters of each locale's script and the minimum count per prompt file
SCRIPT_MARKS = {
    "en": (r"[A-Za-z]", 400), "tr-TR": (r"[çğışöüİ]", 30), "de-DE": (r"[äöüß]", 20), "fr": (r"[éèàçêù]", 20),
    "es-ES": (r"[ñáéíóú¿¡]", 20), "it-IT": (r"[àèéìòù]", 3), "pt-BR": (r"[ãõçáéâêó]", 20), "pt-PT": (r"[ãõçáéâêó]", 20),
    "pl-PL": (r"[ąęłńóśźż]", 20), "lt-LT": (r"[ąčęėįšųūž]", 20), "ru-RU": (r"[а-яё]", 300), "ja-JP": (r"[぀-ゟ]", 100),
    "ko-KR": (r"[가-힯]", 200), "zh-CN": (r"[一-鿿]", 200), "zh-Hant": (r"[一-鿿]", 200),
}
SIMPLIFIED_ONLY = "这们说时语为个么给们还"
TRADITIONAL_ONLY = "這們說時語為個麼給還"
FULLWIDTH_BANNED = ("；", "：", "——", "―")
PASS2_INPUTS = ("source", "target", "register", "category", "speaker", "rationales", "suggestions", "tm")


class AllLocalePromptTests(unittest.TestCase):
    """Every supported locale has a native critic and Pass 2 prompt with the same structure."""

    def test_every_locale_has_native_prompts(self):
        from l10n_common import CANONICAL_LOCALES
        for loc in CANONICAL_LOCALES:
            for name in ("critic", "pass2"):
                with self.subTest(locale=loc, prompt=name):
                    tpl = pt.find_prompt(name, loc)
                    self.assertTrue(tpl.native, f"{name}.{loc}.md missing")
                    self.assertEqual(tpl.meta.get("locale"), loc)
                    self.assertEqual(tpl.meta.get("name"), name)
                    body = tpl.body
                    prose = text_style.prose_only(body)
                    self.assertEqual(body.count("{{WARMUP}}"), 1)
                    self.assertEqual(body.count("{{CONTRASTIVE}}"), 1)
                    self.assertEqual(set(pt.SLOT_RE.findall(body)), {"WARMUP", "CONTRASTIVE"} | ({"LOCALE"} if "{{LOCALE}}" in body else set()))
                    self.assertEqual(re.findall(r"(?m)^(\d)\. ", body), [str(i) for i in range(1, 8)])
                    rx, minimum = SCRIPT_MARKS[loc]
                    self.assertGreaterEqual(len(re.findall(rx, prose)), minimum, f"{name}.{loc}.md is not written in the target script")
                    if loc != "en":
                        for marker in ENGLISH_PROMPT_MARKERS:
                            self.assertFalse(marker in prose, f"{name}.{loc}.md: English prompt text '{marker}'")
                    for ch in FULLWIDTH_BANNED:
                        self.assertNotIn(ch, prose, f"{name}.{loc}.md: banned punctuation {ch!r}")
                    if loc == "zh-CN":
                        self.assertFalse(set(TRADITIONAL_ONLY) & set(prose), "zh-CN prompt uses traditional characters")
                    if loc == "zh-Hant":
                        self.assertFalse(set(SIMPLIFIED_ONLY) & set(prose), "zh-Hant prompt uses simplified characters")
                    if name == "critic":
                        for score in range(1, 6):
                            self.assertRegex(body, rf"(?m)^\| {score} \|")
                        for it in ISSUE_TYPES:
                            self.assertIn(f"`{it}`", body)
                        for field in ("votes", "key", "score", "issue_type", "reason", "suggested"):
                            self.assertIn(f'"{field}"', body)
                        for field in ("tier", "member", "family", "model"):
                            self.assertIn(f"`{field}`", body)
                    else:
                        self.assertIn('"candidates"', body)
                        for field in PASS2_INPUTS:
                            self.assertIn(f"`{field}`", body)
                    rendered = pt.render_prompt(name, loc, warmup="- x", contrastive="1. ✓ a")
                    self.assertNotIn("{{", rendered)


if __name__ == "__main__":
    unittest.main()
