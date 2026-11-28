"""P3: warmup_loader.py seeded, register-aware, source-balanced warm-up sampling."""

import json
import re
import unittest
from pathlib import Path
from typing import Any

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS, TempDir, run_cli, write_text  # noqa: E402

import warmup_loader as wl  # noqa: E402
from l10n_common import L10nError  # noqa: E402


def make_pack(td: Path) -> Path:
    pack = td / "tr-TR"
    (pack / "local").mkdir(parents=True)
    bundle: list[dict[str, Any]] = []
    for i in range(30):
        bundle.append({"text": f"Ayar satırı {i}", "register": "ui", "source": "godot", "license_class": "bundle", "key": f"g{i}", "consistency": "single"})
    for i in range(12):
        bundle.append({"text": f"Hadi bakalım, {i}. turu da bitirelim!", "register": "dialogue_casual", "source": "reference",
                       "license_class": "bundle", "key": f"r{i}", "consistency": "single"})
    bundle.append({"text": "<b>İptal</b>", "register": "ui", "source": "godot", "license_class": "bundle", "key": "cancel", "consistency": "trusted"})
    local = [{"text": f"{{YELLOW}}Treni [accent]depoya[] gönder {i}", "register": "dialogue_casual", "source": "openttd",
              "license_class": "local", "key": f"o{i}", "consistency": "single"} for i in range(20)]
    local.append({"text": "x" * 400, "register": "dialogue_casual", "source": "openttd", "license_class": "local", "key": "long", "consistency": "single"})
    write_text(pack / "warmup.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in bundle))
    write_text(pack / "local" / "warmup.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in local))
    return pack


class SamplingTests(unittest.TestCase):
    def test_same_seed_same_output(self):
        with TempDir() as td:
            pack = make_pack(td)
            a = wl.load_warmup(pack, ["dialogue_casual"], 15, seed=7)
            b = wl.load_warmup(pack, ["dialogue_casual"], 15, seed=7)
            c = wl.load_warmup(pack, ["dialogue_casual"], 15, seed=8)
            self.assertEqual(a, b)
            self.assertNotEqual([e["text"] for e in a], [e["text"] for e in c])
            self.assertEqual(len(a), 15)

    def test_register_filter_and_local_toggle(self):
        with TempDir() as td:
            pack = make_pack(td)
            ui = wl.load_warmup(pack, ["ui"], 40)
            self.assertTrue(all(e["register"] == "ui" for e in ui))
            dlg = wl.load_warmup(pack, ["dialogue_casual"], 40, include_local=False)
            self.assertTrue(all(e["license_class"] == "bundle" for e in dlg))
            self.assertEqual(len(dlg), 12)
            both = wl.load_warmup(pack, ["dialogue_casual"], 40)
            self.assertEqual(len(both), 32)  # 12 reference + 20 local, the 400 character line is skipped

    def test_balanced_reference_first_and_cleaned(self):
        with TempDir() as td:
            pack = make_pack(td)
            got = wl.load_warmup(pack, ["dialogue_casual"], 6, seed=1)
            self.assertEqual([e["source"] for e in got], ["reference", "openttd"] * 3)
            local_texts = [e["text"] for e in got if e["source"] == "openttd"]
            for t in local_texts:
                self.assertNotIn("{YELLOW}", t)
                self.assertNotIn("[accent]", t)
                self.assertRegex(t, r"^Treni depoya gönder \d+$")
            ui = wl.load_warmup(pack, ["ui"], 1, seed=99)
            self.assertEqual(ui[0]["text"], "İptal")  # trusted lines first inside a source

    def test_render_block(self):
        block = wl.render_warmup([{"text": "a\nb", "register": "dialogue_casual"}, {"text": "Kaydet", "register": "ui"}])
        self.assertEqual(block, "[ui]\n- Kaydet\n[dialogue_casual]\n- a / b")
        self.assertEqual(wl.render_warmup([]), "")

    def test_missing_pack_and_bad_register(self):
        with TempDir() as td:
            with self.assertRaises(L10nError):
                wl.load_warmup(td, ["ui"])
            with self.assertRaises(L10nError):
                wl.check_registers(["shouting"])


class CliTests(unittest.TestCase):
    def test_exit_codes_and_determinism(self):
        with TempDir() as td:
            pack = make_pack(td)
            args = [str(pack), "--register", "dialogue_casual", "--count", "10", "--seed", "42", "--json"]
            code, out1, err = run_cli("warmup_loader.py", *args)
            self.assertEqual(code, 0, err)
            code, out2, _ = run_cli("warmup_loader.py", *args)
            self.assertEqual(json.loads(out1)["entries"], json.loads(out2)["entries"])
            code, out, _ = run_cli("warmup_loader.py", "--input", str(pack), "--register", "dialogue_formal", "--count", "30",
                                   "--out", str(td / "w.txt"))
            self.assertEqual(code, 1)
            self.assertIn("WARN", out)
            code, _, _ = run_cli("warmup_loader.py", str(pack), "--register", "ui", "--count", "5", "--format", "jsonl", "--out", str(td / "w.jsonl"))
            self.assertEqual(code, 0)
            self.assertEqual(len((td / "w.jsonl").read_text(encoding="utf-8").splitlines()), 5)
            self.assertEqual(run_cli("warmup_loader.py", str(pack), "--register", "yelling")[0], 2)
            self.assertEqual(run_cli("warmup_loader.py", str(td / "nope"))[0], 2)
            self.assertEqual(run_cli("warmup_loader.py")[0], 2)

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertTrue("warmup_loader.py" in doc, "warmup_loader.py missing from CLI_REFERENCE.md")
        code, help_text, _ = run_cli("warmup_loader.py", "--help")
        self.assertEqual(code, 0)
        for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
            self.assertTrue(flag in doc, f"warmup_loader.py: {flag} missing from CLI_REFERENCE.md")


if __name__ == "__main__":
    unittest.main()
