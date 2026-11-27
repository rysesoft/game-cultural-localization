"""export_translations.py: decisions applied, then the game's own formats (Unity, CSV, JSON, PO), never into a game project."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import TempDir, run_cli, write_json, write_text  # noqa: E402

import export_translations as ex  # noqa: E402
from l10n_common import parse_unity_yaml  # noqa: E402

SHARED_GUID = "aaaabbbbccccddddeeeeffff00001111"
SHARED = """%YAML 1.1
--- !u!114 &11400000
MonoBehaviour:
  m_Name: Hud Shared Data
  m_TableCollectionName: Hud
  m_TableCollectionNameGuidString: 0123456789abcdef0123456789abcdef
  m_Entries:
  - m_Id: 1
    m_Key: Hud.Title
  - m_Id: 2
    m_Key: Hud.Letter
  - m_Id: 3
    m_Key: Hud.Count
  - m_Id: 4
    m_Key: Hud.New
"""


def table(code: str, rows: str) -> str:
    return (f"%YAML 1.1\n--- !u!114 &11400000\nMonoBehaviour:\n  m_Name: Hud_{code}\n  m_LocaleId:\n    m_Code: {code}\n"
            f"  m_SharedData: {{fileID: 11400000, guid: {SHARED_GUID}, type: 2}}\n  m_TableData:\n{rows}  m_Extra: keep me\n")


TR_ROWS = ("  - m_Id: 1\n    m_Localized: Başlık\n    m_Metadata:\n      m_Items: []\n"
           "  - m_Id: 2\n    m_Localized: 'Birinci paragraf.\n\n\n      İkinci paragraf.'\n    m_Metadata:\n      m_Items: []\n"
           "  - m_Id: 3\n    m_Localized: \"{0:plural:bir eşya|{} eşya}\"\n    m_Metadata:\n      m_Items: []\n")


def unity_game(td: Path) -> Path:
    tables = td / "Game" / "Assets" / "Localisation" / "Tables" / "Hud"
    (td / "Game" / "ProjectSettings").mkdir(parents=True)
    tables.mkdir(parents=True)
    write_text(tables / "Hud Shared Data.asset", SHARED)
    write_text(tables / "Hud Shared Data.asset.meta", f"fileFormatVersion: 2\nguid: {SHARED_GUID}\n")
    write_text(tables / "Hud_tr-TR.asset", table("tr-TR", TR_ROWS))
    write_text(tables / "Hud_de-DE.asset", table("de-DE", "  - m_Id: 1\n    m_Localized: Titel\n"))
    return tables.parent


class UnityTests(unittest.TestCase):
    def test_only_the_texts_change_and_read_back(self):
        with TempDir() as td:
            tables = unity_game(td)
            final = write_json(td / "final_batch_01.json", [
                {"key": "Hud.Title", "tr-TR": "Başlık"},                                     # unchanged
                {"key": "Hud.Letter", "tr-TR": 'Birinci "paragraf".\n\nİkinci \\ paragraf.'},  # quotes, backslash, paragraph
                {"key": "Hud.Count", "tr-TR": "{0:plural:tek eşya|{} eşya}"},                 # SmartFormat passes through
                {"key": "Hud.New", "tr-TR": "Yeni satır"},                                   # no entry in the table yet
            ])
            out = td / "export"
            code, stdout, err = run_cli("export_translations.py", str(final), "--locale", "tr-TR", "--template-dir", str(tables), "--out", str(out))
            self.assertEqual(code, 0, err + stdout)
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["Hud_tr-TR.asset"])   # the de-DE table is not touched
            text = (out / "Hud_tr-TR.asset").read_text(encoding="utf-8")
            got = {e["id"]: e["text"] for e in parse_unity_yaml(text)["entries"] if e["text"] is not None}
            self.assertEqual(got, {"1": "Başlık", "2": 'Birinci "paragraf".\n\nİkinci \\ paragraf.', "3": "{0:plural:tek eşya|{} eşya}",
                                   "4": "Yeni satır"})
            self.assertIn("    m_Localized: Başlık\n", text)          # an unchanged text keeps its original line
            self.assertIn("  m_Extra: keep me\n", text)                  # every other line stays
            self.assertIn("  - m_Id: 4\n    m_Localized: \"Yeni satır\"\n    m_Metadata:\n      m_Items: []\n", text)
            self.assertEqual(text.count("m_Metadata"), 4)
            same = write_json(td / "same.json", [{"key": "Hud.Title", "tr-TR": "Başlık"}])
            out2 = td / "export2"
            code, stdout, _ = run_cli("export_translations.py", str(same), "--locale", "tr-TR", "--template-dir", str(tables), "--out", str(out2), "--json")
            self.assertEqual((code, json.loads(stdout)["files"], json.loads(stdout)["unchanged_tables"]), (0, [], 1))   # nothing to copy

    def test_a_key_name_two_tables_share(self):
        tables = {Path("a.asset"): ("Hud", {"Panel": "1"}), Path("b.asset"): ("Machine", {"Panel": "7"})}
        per = ex.assign_unity_keys({"Panel": "x", "Machine:Panel": "y"}, tables)
        self.assertEqual((per[Path("a.asset")], per[Path("b.asset")]), ({"1": "x"}, {"7": "y"}))
        with self.assertRaises(ex.L10nError):
            ex.assign_unity_keys({"Panel": "x"}, tables)           # no label, two tables, the export stops instead of guessing

    def test_never_writes_into_a_game_project(self):
        with TempDir() as td:
            tables = unity_game(td)
            final = write_json(td / "f.json", [{"key": "Hud.Title", "tr-TR": "X"}])
            for out in (tables / "out", tables / "Hud"):
                code, _, err = run_cli("export_translations.py", str(final), "--locale", "tr-TR", "--template-dir", str(tables), "--out", str(out))
                self.assertEqual(code, 2, err)
                self.assertFalse((tables / "out").exists())
            self.assertIn("m_Localized: Başlık", (tables / "Hud" / "Hud_tr-TR.asset").read_text(encoding="utf-8"))


class DecisionTests(unittest.TestCase):
    def report(self, decisions):
        lines = [{"key": "A", "old": "eski A", "new": "yeni A", "decision": decisions[0]},
                 {"key": "B", "old": "eski B", "new": "yeni B", "decision": decisions[1]},
                 {"key": "C", "old": "aynı", "new": "aynı", "decision": ""}]           # unchanged, needs no decision
        return {"locale": "tr-TR", "lines": lines}

    def test_accept_reject_and_open(self):
        with TempDir() as td:
            run = td / "run"
            run.mkdir()
            write_json(run / "final_batch_01.json", [{"key": "A", "tr-TR": "yeni A"}, {"key": "B", "tr-TR": "yeni B"}, {"key": "C", "tr-TR": "aynı"}])
            (td / "game").mkdir()
            tpl = write_text(td / "game" / "strings.csv", "﻿key;en;tr-TR;note\nA;Apple;;keep\nB;Bee;;keep\nC;Cat;;keep\n")
            write_json(run / "changes_tr-TR_01.json", self.report(["accept", "reject"]))
            code, stdout, err = run_cli("export_translations.py", str(run), "--locale", "tr-TR", "--template", str(tpl), "--out", str(td / "out"), "--json")
            self.assertEqual(code, 0, err)
            self.assertEqual((json.loads(stdout)["accepted"], json.loads(stdout)["rejected"]), (1, 1))
            raw = (td / "out" / "strings.csv").read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))                              # the BOM of the game's file stays
            self.assertEqual(raw.decode("utf-8-sig"), "key;en;tr-TR;note\nA;Apple;yeni A;keep\nB;Bee;eski B;keep\nC;Cat;aynı;keep\n")
            write_json(run / "changes_tr-TR_01.json", self.report(["accept", ""]))
            code, stdout, _ = run_cli("export_translations.py", str(run), "--locale", "tr-TR", "--template", str(tpl), "--out", str(td / "out"), "--json")
            self.assertEqual((code, json.loads(stdout)["undecided"]), (1, ["B"]))        # a changed line nobody decided
            write_json(run / "changes_tr-TR_01.json", self.report(["maybe", ""]))
            self.assertEqual(run_cli("export_translations.py", str(run), "--locale", "tr-TR", "--template", str(tpl), "--out", str(td / "out"))[0], 2)


class OtherFormatTests(unittest.TestCase):
    def test_json_and_po(self):
        with TempDir() as td:
            final = write_json(td / "final.json", [{"key": "hello", "tr-TR": "Merhaba \"dünya\""}, {"key": "apple|[0]", "tr-TR": "bir elma"},
                                                    {"key": "apple|[1]", "tr-TR": "{n} elma"}, {"key": "gone", "tr-TR": "yok"}])
            (td / "game").mkdir()
            tj = write_json(td / "game" / "tr.json", {"hello": "", "other": "kalsın"})
            po = write_text(td / "game" / "tr.po", 'msgid ""\nmsgstr ""\n"Language: tr\\n"\n\n#, fuzzy\nmsgid "hello"\nmsgstr "eski"\n\n'
                                                     'msgid "apple"\nmsgid_plural "apples"\nmsgstr[0] ""\nmsgstr[1] ""\n\nmsgid "keep"\nmsgstr "dursun"\n')
            code, stdout, err = run_cli("export_translations.py", str(final), "--locale", "tr-TR", "--template", str(tj), "--template", str(po),
                                        "--out", str(td / "out"), "--json")
            self.assertEqual(code, 1, err)                                                # 'gone' is in no template
            self.assertEqual(json.loads(stdout)["not_placed"], ["gone"])
            self.assertEqual(json.loads((td / "out" / "tr.json").read_text(encoding="utf-8")), {"hello": 'Merhaba "dünya"', "other": "kalsın"})
            from l10n_common import parse_po
            got = {r.key: r.dst for r in parse_po((td / "out" / "tr.po").read_text(encoding="utf-8"))}
            self.assertEqual((got["hello"], got["apple|[0]"], got["apple|[1]"], got["keep"]), ('Merhaba "dünya"', "bir elma", "{n} elma", "dursun"))
            self.assertNotIn("fuzzy", (td / "out" / "tr.po").read_text(encoding="utf-8"))   # a filled entry is no longer fuzzy


if __name__ == "__main__":
    unittest.main()
