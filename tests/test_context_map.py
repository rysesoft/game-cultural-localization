"""Context map facts (build_context_map.py --scan) on a small synthetic Unity project, and the context first rules."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import REFS, ROOT, SCRIPTS, TempDir, run_cli, write_text  # noqa: E402

import build_context_map as bcm  # noqa: E402
import text_style  # noqa: E402
from l10n_common import L10nError  # noqa: E402
from providers import load_providers_config  # noqa: E402

TABLE_GUID = "6ca99244aa860c74f86f800bd96c8a57"
SCRIPT_GUID = "1111aaaa2222bbbb3333cccc4444dddd"

SHARED = f"""%YAML 1.1
--- !u!114 &11400000
MonoBehaviour:
  m_Name: HudTable Shared Data
  m_TableCollectionName: HudTable
  m_TableCollectionNameGuidString: {TABLE_GUID}
  m_Entries:
  - m_Id: 100
    m_Key: Hud.Deadline
    m_Metadata:
      m_Items: []
  - m_Id: 101
    m_Key: Hud.Stamina
    m_Metadata:
      m_Items: []
  - m_Id: 102
    m_Key: Item.Name.Can
    m_Metadata:
      m_Items: []
  - m_Id: 103
    m_Key: Hud.Unused
    m_Metadata:
      m_Items: []
"""

PREFAB = f"""%YAML 1.1
--- !u!1 &10
GameObject:
  m_Name: DayStart_HUD
--- !u!224 &11
RectTransform:
  m_GameObject: {{fileID: 10}}
  m_Father: {{fileID: 0}}
--- !u!1 &20
GameObject:
  m_Name: Controllers
--- !u!224 &21
RectTransform:
  m_GameObject: {{fileID: 20}}
  m_Father: {{fileID: 11}}
--- !u!114 &30
MonoBehaviour:
  m_GameObject: {{fileID: 20}}
  m_Script: {{fileID: 11500000, guid: {SCRIPT_GUID}, type: 3}}
  m_Name:
  deadlineTextLoc:
    m_TableReference:
      m_TableCollectionName: GUID:{TABLE_GUID}
    m_TableEntryReference:
      m_KeyId: 100
      m_Key:
    m_FallbackState: 0
--- !u!1 &40
GameObject:
  m_Name: StaminaLabel
--- !u!224 &41
RectTransform:
  m_GameObject: {{fileID: 40}}
  m_Father: {{fileID: 21}}
--- !u!114 &50
MonoBehaviour:
  m_GameObject: {{fileID: 40}}
  m_Script: {{fileID: 11500000, guid: ffffffffffffffffffffffffffffffff, type: 3}}
  m_StringReference:
    m_TableReference:
      m_TableCollectionName: GUID:{TABLE_GUID}
    m_TableEntryReference:
      m_KeyId: 101
      m_Key:
"""

ITEM_SO = """%YAML 1.1
--- !u!114 &11400000
MonoBehaviour:
  m_GameObject: {fileID: 0}
  m_Name: Can
  localizedItemName:
    m_TableReference:
      m_TableCollectionName: HudTable
    m_TableEntryReference:
      m_KeyId: 0
      m_Key: Item.Name.Can
    m_FallbackState: 0
"""

CODE = """using UnityEngine.Localization;
public class DayStartHUDController {
    [SerializeField] private LocalizedString deadlineTextLoc;
    void Show(int deadline) {
        deadlineText = (deadline > 0) ? $"{deadlineTextLoc.GetLocalizedString()}: " + deadline : " ";
        title.text = deadlineTextLoc.GetLocalizedString();
    }
}
"""


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_text(path, text)


def make_project(td: Path) -> Path:
    proj = td / "Game"
    (proj / "ProjectSettings").mkdir(parents=True)
    put(proj / "Assets" / "Localisation" / "Tables" / "Hud" / "HudTable Shared Data.asset", SHARED)
    put(proj / "Assets" / "Prefabs" / "UI" / "DayStart_HUD.prefab", PREFAB)
    put(proj / "Assets" / "ScriptableObjects" / "Items" / "Can.asset", ITEM_SO)
    put(proj / "Assets" / "Scripts" / "HUD" / "DayStartHUDController.cs", CODE)
    put(proj / "Assets" / "Scripts" / "HUD" / "DayStartHUDController.cs.meta", f"fileFormatVersion: 2\nguid: {SCRIPT_GUID}\n")
    return proj


class ScanTests(unittest.TestCase):
    def test_usages_paths_and_code(self):
        with TempDir() as td:
            scan = bcm.scan_unity(make_project(td))
        self.assertEqual(scan["engine"], "unity")
        self.assertEqual(scan["tables"], ["HudTable"])
        keys = scan["keys"]
        deadline = keys["Hud.Deadline"]
        self.assertEqual(deadline["usages"], [{"file": "Assets/Prefabs/UI/DayStart_HUD.prefab", "object": "DayStart_HUD/Controllers",
                                               "class": "DayStartHUDController", "field": "deadlineTextLoc"}])
        self.assertEqual([c["line"] for c in deadline["code"]], [5, 6])          # the declaration line is left out
        self.assertEqual([c["concat"] for c in deadline["code"]], [True, False])  # text, a colon and a number are glued
        stamina = keys["Hud.Stamina"]["usages"][0]                                 # a LocalizeStringEvent of the Unity package
        self.assertEqual((stamina["object"], stamina["class"], stamina["field"]), ("DayStart_HUD/Controllers/StaminaLabel", "LocalizeStringEvent", "m_StringReference"))
        can = keys["Item.Name.Can"]["usages"][0]                                   # table by name, entry by key name
        self.assertEqual((can["file"], can["object"], can["field"]), ("Assets/ScriptableObjects/Items/Can.asset", "Can", "localizedItemName"))
        self.assertEqual(keys["Hud.Unused"]["usages"], [])
        blob = json.dumps(scan)
        self.assertNotIn(str(td), blob)                                            # no machine path in the output

    def test_summary_and_house_style(self):
        with TempDir() as td:
            scan = bcm.scan_unity(make_project(td))
        s = bcm.summary(scan, ["Hud.Deadline", "Hud.Unused", "Nope"])
        self.assertEqual((s["keys"], s["used"], s["concat_lines"]), (4, 3, 1))
        self.assertEqual(s["wanted_missing"], ["Hud.Unused", "Nope"])
        md = bcm.render_summary(scan, s)
        self.assertEqual(text_style.punctuation_problems(md), [])
        self.assertIn("| HudTable | 4 | 3 |", md)

    def test_not_unity_is_refused(self):
        with TempDir() as td:
            with self.assertRaises(L10nError):
                bcm.find_unity_root(td)


class CliTests(unittest.TestCase):
    def test_scan_cli_and_exit_codes(self):
        with TempDir() as td:
            proj = make_project(td)
            ref = write_text(td / "ref.csv", "key,en,tr-TR\nHud.Deadline,Deadline,Son tarih\nHud.Stamina,Stamina,Enerji\n")
            out = td / "context"
            code, stdout, err = run_cli("build_context_map.py", "--scan", "--project", str(proj), "--out", str(out), "--keys-from", str(ref))
            self.assertEqual(code, 0, err)
            self.assertTrue((out / "key_usage.json").is_file())
            self.assertTrue((out / "scan_summary.md").is_file())
            ref2 = write_text(td / "ref2.csv", "key,en,tr-TR\nHud.Unused,Unused,Kullanılmıyor\n")
            self.assertEqual(run_cli("build_context_map.py", "--scan", "--project", str(proj), "--out", str(out), "--keys-from", str(ref2))[0], 1)
            self.assertEqual(run_cli("build_context_map.py", "--scan", "--project", str(td), "--out", str(out))[0], 2)        # not a Unity project
            self.assertEqual(run_cli("build_context_map.py", "--scan", "--project", str(proj), "--out", str(proj / "ctx"))[0], 2)  # never writes into the game
            self.assertEqual(run_cli("build_context_map.py", "--project", str(proj), "--out", str(out))[0], 2)                # no mode


class ContextFirstRuleTests(unittest.TestCase):
    """The context map is the mandatory first step, set by the studio. A term list never replaces it."""

    def test_rules_agents_and_config(self):
        rules = (ROOT / "rules" / "AGENTS.md").read_text(encoding="utf-8")
        second = re.search(r"(?m)^2\. (.*)$", rules).group(1)
        for word in ("Context map before any word", "context-cartographer", "Opus", "context-scout", "Sonnet", "asks the user", "CONTEXT_MAP.md"):
            self.assertIn(word, second)
        self.assertNotIn("glossary.csv", rules)
        skill = (SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
        law5 = re.search(r"(?m)^5\. \*\*(.*)$", skill).group(1)
        self.assertIn("Context Decides Every Word", law5)
        self.assertNotRegex(law5.lower(), r"\block\b|glossary")
        for name, model in (("context-cartographer", "opus"), ("context-scout", "sonnet")):
            text = (ROOT / "agents" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn(f"name: {name}", text)
            self.assertIn(f"model: {model}", text.lower().replace("`", ""))   # the Claude Code value is spelled out in the body
        cfg = load_providers_config()
        self.assertEqual(cfg.role_model("context_orchestrator").id, "claude-opus-5-5")
        self.assertEqual(cfg.role_model("context_agent").id, "claude-sonnet-5-5")
        methodology = (REFS / "methodology_and_qa.md").read_text(encoding="utf-8")
        self.assertIn("0. **Context map, always first.**", methodology)
        self.assertNotIn("Lock `glossary.csv`", methodology)


if __name__ == "__main__":
    unittest.main()
