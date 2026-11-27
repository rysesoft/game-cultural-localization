"""Context map facts (build_context_map.py --scan) on a small synthetic Unity project, and the context first rules."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from unittest import mock

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import REFS, ROOT, SCRIPTS, TempDir, run_cli, write_text  # noqa: E402

import build_context_map as bcm  # noqa: E402
import text_style  # noqa: E402
from l10n_common import L10nError  # noqa: E402
from providers import load_providers_config  # noqa: E402

NO_KEYS = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "", "GCL_OFFLINE": "1"}
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


SHARED_ASSET_GUID = "5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a"
PREFAB_GUID = "7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b"


def locale_table(code: str, shared_guid: str, rows: str) -> str:
    return (f"%YAML 1.1\n--- !u!114 &11400000\nMonoBehaviour:\n  m_Name: HudTable_{code}\n  m_LocaleId:\n    m_Code: {code}\n"
            f"  m_SharedData: {{fileID: 11400000, guid: {shared_guid}, type: 2}}\n  m_TableData:\n{rows}")


EN_ROWS = ("  - m_Id: 100\n    m_Localized: Deadline\n    m_Metadata:\n      m_Items: []\n"
           "  - m_Id: 102\n    m_Localized: 'A can of food.\n\n\n      Restores some energy.'\n    m_Metadata:\n      m_Items: []\n")
TR_ROWS = ("  - m_Id: 100\n    m_Localized: Son Tarih\n    m_Metadata:\n      m_Items: []\n"
           "  - m_Id: 102\n    m_Localized: 'Bir kutu yemek.\n\n\n      Biraz enerji verir.'\n    m_Metadata:\n      m_Items: []\n")

# a scene that binds Hud.Unused through a prefab override, as the ending scenes of the first project did
SCENE = f"""%YAML 1.1
--- !u!1001 &500
PrefabInstance:
  m_ObjectHideFlags: 0
  serializedVersion: 2
  m_Modification:
    serializedVersion: 3
    m_TransformParent: {{fileID: 0}}
    m_Modifications:
    - target: {{fileID: 50, guid: {PREFAB_GUID}, type: 3}}
      propertyPath: m_StringReference.m_TableEntryReference.m_KeyId
      value: 103
      objectReference: {{fileID: 0}}
    - target: {{fileID: 50, guid: {PREFAB_GUID}, type: 3}}
      propertyPath: m_StringReference.m_TableReference.m_TableCollectionName
      value: GUID:{TABLE_GUID}
      objectReference: {{fileID: 0}}
    - target: {{fileID: 41, guid: {PREFAB_GUID}, type: 3}}
      propertyPath: m_AnchorMax.x
      value: 1
      objectReference: {{fileID: 0}}
  m_SourcePrefab: {{fileID: 100100000, guid: {PREFAB_GUID}, type: 3}}
"""

STALE_SO = """%YAML 1.1
--- !u!114 &11400000
MonoBehaviour:
  m_GameObject: {fileID: 0}
  m_Name: OldNews
  title:
    m_TableReference:
      m_TableCollectionName: OldEvents
    m_TableEntryReference:
      m_KeyId: 0
      m_Key: Old.News.Title
  body:
    m_TableReference:
      m_TableCollectionName: HudTable
    m_TableEntryReference:
      m_KeyId: 999
      m_Key:
"""


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_text(path, text)


def add_locales(proj: Path) -> None:
    """English and Turkish tables of HudTable, and a Turkish table of another collection in the same folder."""
    folder = proj / "Assets" / "Localisation" / "Tables" / "Hud"
    put(folder / "HudTable Shared Data.asset.meta", f"fileFormatVersion: 2\nguid: {SHARED_ASSET_GUID}\n")
    put(folder / "HudTable_en.asset", locale_table("en", SHARED_ASSET_GUID, EN_ROWS))
    put(folder / "HudTable_tr-TR.asset", locale_table("tr-TR", SHARED_ASSET_GUID, TR_ROWS))
    put(folder / "Other_tr-TR.asset", locale_table("tr-TR", "0" * 32, "  - m_Id: 100\n    m_Localized: Yanlış tablo\n"))


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

    def test_prefab_override_and_stale_references(self):
        with TempDir() as td:
            proj = make_project(td)
            put(proj / "Assets" / "Prefabs" / "UI" / "DayStart_HUD.prefab.meta", f"fileFormatVersion: 2\nguid: {PREFAB_GUID}\n")
            put(proj / "Assets" / "Scenes" / "End.unity", SCENE)
            put(proj / "Assets" / "ScriptableObjects" / "News" / "OldNews.asset", STALE_SO)
            scan = bcm.scan_unity(proj)
        self.assertEqual(scan["keys"]["Hud.Unused"]["usages"], [{"file": "Assets/Scenes/End.unity", "object": "DayStart_HUD (override)",
                                                                 "class": "LocalizeStringEvent", "field": "m_StringReference"}])
        self.assertEqual(scan["missing_table_references"], {"OldEvents": 1})   # a table the project no longer has
        self.assertEqual(scan["unresolved_references"], 1)                     # key id 999 is not in HudTable
        s = bcm.summary(scan)
        self.assertEqual(s["used"], 4)
        md = bcm.render_summary(scan, s)
        self.assertIn("OldEvents (1)", md)
        self.assertEqual(text_style.punctuation_problems(md), [])


    def test_a_key_name_two_tables_share_keeps_both(self):
        # the first project had one key name in two tables, keyed by name alone one of them was lost
        second = "9e9e9e9e9e9e9e9e9e9e9e9e9e9e9e9e"
        with TempDir() as td:
            proj = make_project(td)
            put(proj / "Assets" / "Localisation" / "Tables" / "Machine" / "Machine Shared Data.asset",
                SHARED.replace("HudTable", "MachineTable").replace(TABLE_GUID, second).replace("m_Id: 10", "m_Id: 20"))
            put(proj / "Assets" / "ScriptableObjects" / "Machines" / "Arm.asset", ITEM_SO.replace("m_Name: Can", "m_Name: Arm")
                .replace("m_TableCollectionName: HudTable", f"m_TableCollectionName: GUID:{second}").replace("m_KeyId: 0", "m_KeyId: 200")
                .replace("m_Key: Item.Name.Can", "m_Key:"))
            scan = bcm.scan_unity(proj)
        keys = scan["keys"]
        self.assertIn("HudTable:Hud.Deadline", keys)
        self.assertEqual(keys["MachineTable:Hud.Deadline"]["usages"][0]["object"], "Arm")
        self.assertEqual(keys["HudTable:Hud.Deadline"]["usages"][0]["field"], "deadlineTextLoc")
        self.assertEqual(keys["HudTable:Hud.Deadline"]["name"], "Hud.Deadline")
        self.assertNotIn("Hud.Deadline", keys)
        self.assertEqual(len(keys), 8)
        self.assertEqual(bcm.summary(scan, ["Hud.Deadline", "MachineTable:Hud.Deadline"])["wanted_missing"], [])


# --------------------------------------------------------------------------- #
# Use trace. The two cases that misled the jury on 2026-11-27, in miniature
# --------------------------------------------------------------------------- #
TRACE_TABLE = "8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c"
WARN_GUID = "2222aaaa3333bbbb4444cccc5555dddd"
LICENSE_GUID = "3333aaaa4444bbbb5555cccc6666dddd"
TRACE_KEYS = {300: "Warning.NeedBrokenItem", 301: "Warning.ItemSentStorage", 302: "Warning.HotHandle", 310: "License.WorkshopCondition",
              311: "License.ReputationCondition", 312: "License.Upgrade", 313: "License.Max", 314: "License.Locked", 315: "License.Occupied",
              316: "License.Named", 317: "License.Busy"}

WARN_CS = r"""using UnityEngine;
using UnityEngine.Localization;

public class WarningMessageController : MonoBehaviour
{
    [HideInInspector] public static string NEED_BROKEN_ITEM = "Don't have any broken item in the salvage machine!";
    [HideInInspector] public static string ITEM_SENT_STORAGE = "Delivered items has been sent to the storage.";
    [HideInInspector] public static string HOT_HANDLE = "You can't fire the laser this close to a surface.";
    [SerializeField] LocalizedString NEED_BROKEN_ITEM_LOC;
    [SerializeField] LocalizedString ITEM_SENT_STORAGE_LOC;
    [SerializeField] LocalizedString HOT_HANDLE_LOC;

    void Awake() { NEED_BROKEN_ITEM_LOC.StringChanged += LanguageChanged; }

    void LanguageChanged(string _)
    {
        NEED_BROKEN_ITEM = NEED_BROKEN_ITEM_LOC.GetLocalizedString();
        ITEM_SENT_STORAGE = ITEM_SENT_STORAGE_LOC.GetLocalizedString();
        if (HOT_HANDLE_LOC != null && !HOT_HANDLE_LOC.IsEmpty) HOT_HANDLE = HOT_HANDLE_LOC.GetLocalizedString();
    }

    public void ShowWarningMessage(string text) { }
}
"""

SALVAGE_CS = r"""public class SalvageMachine : MonoBehaviour
{
    int count;
    int GetTotalItemCount() => count;

    bool CanSalvage()
    {
        return GetTotalItemCount() > 0;
    }

    public void StartSalvage()
    {
        if (!CanSalvage())
        {
            WarningMessageController.SafeExecute(inst => inst.ShowWarningMessage(WarningMessageController.NEED_BROKEN_ITEM));
            return;
        }
        // inst.ShowWarningMessage(WarningMessageController.HOT_HANDLE);
        /* WarningMessageController.HOT_HANDLE */
        Debug.Log("WarningMessageController.HOT_HANDLE is a string here, not a use");
    }
}
"""

CRAFT_CS = r"""public class CraftController : MonoBehaviour
{
    public void CompleteProduction(CraftableResourceSO craftable, bool sentToStorage)
    {
        if (sentToStorage)
        {
            WarningMessageController.SafeExecute(w =>
            {
                string itemName = craftable.itemName;
                w.ShowWarningMessage($"{WarningMessageController.ITEM_SENT_STORAGE}: {itemName}");
            });
        }
    }

    public string DumpInto(int moved)
    {
        string message = "";
        if (moved > 0)
            message = WarningMessageController.ITEM_SENT_STORAGE;
        return message;
    }
}
"""

LICENSE_CS = r"""using UnityEngine.Localization;

public class LicensePanelController : MonoBehaviour
{
    [SerializeField] LocalizedString needReputationTextLoc;
    [SerializeField] LocalizedString needWorkshopTextLoc;
    [SerializeField] LocalizedString upgradeTextLoc;
    [SerializeField] LocalizedString maxTextLoc;
    [SerializeField] LocalizedString lockedString;
    [SerializeField] LocalizedString occupiedString;
    [SerializeField] LocalizedString namedLoc;
    [SerializeField] LocalizedString busyLoc;

    string needReputationText = "Need More Reputation:";
    string needWorkshopText = "Upgrade workshop!";
    string maxText = "MAX";

    void Awake()
    {
        needReputationTextLoc.StringChanged += NeedReputationTextLoc_StringChanged;
        maxTextLoc.StringChanged += MaxTextLoc_StringChanged;
    }

    void NeedReputationTextLoc_StringChanged(string value)
    {
        needReputationText = value;
        needWorkshopText = needWorkshopTextLoc.GetLocalizedString();
    }

    void MaxTextLoc_StringChanged(string value) => maxText = value;

    public void DrawPanel(int rep, int have, int amount, bool atMax, bool active, string hangarName, string nameText, State state)
    {
        string hoverDescription = "";
        if (rep > have)
        {
            hoverDescription += $"{needReputationText} {rep - have}\r\n";
        }
        if (have > 0)
        {
            hint.text = "";
        }
        else
        {
            hint.text = needReputationText;
        }
        button.SetText(upgradeTextLoc.GetLocalizedString() + "\n¢" + amount);
        title.text = atMax ? maxText : "";
        string statusLabel = !active
            ? lockedString.GetLocalizedString()
            : occupiedString.GetLocalizedString();
        button.SetText($"{hangarName} ({statusLabel})");
        label.text = string.Format("{0}: {1}", nameText, namedLoc.GetLocalizedString());
        switch (state)
        {
            case State.Busy:
                Show(busyLoc.GetLocalizedString());
                break;
        }
    }
}
"""


def trace_shared() -> str:
    entries = "".join(f"  - m_Id: {kid}\n    m_Key: {key}\n    m_Metadata:\n      m_Items: []\n" for kid, key in TRACE_KEYS.items())
    return (f"%YAML 1.1\n--- !u!114 &11400000\nMonoBehaviour:\n  m_Name: Trace Shared Data\n  m_TableCollectionName: TraceTable\n"
            f"  m_TableCollectionNameGuidString: {TRACE_TABLE}\n  m_Entries:\n{entries}")


def mono_prefab(name: str, script_guid: str, refs: dict) -> str:
    body = "".join(f"  {fld}:\n    m_TableReference:\n      m_TableCollectionName: GUID:{TRACE_TABLE}\n    m_TableEntryReference:\n"
                   f"      m_KeyId: {kid}\n      m_Key:\n" for fld, kid in refs.items())
    return (f"%YAML 1.1\n--- !u!1 &10\nGameObject:\n  m_Name: {name}\n--- !u!224 &11\nRectTransform:\n  m_GameObject: {{fileID: 10}}\n"
            f"  m_Father: {{fileID: 0}}\n--- !u!114 &30\nMonoBehaviour:\n  m_GameObject: {{fileID: 10}}\n"
            f"  m_Script: {{fileID: 11500000, guid: {script_guid}, type: 3}}\n  m_Name:\n{body}")


def make_trace_project(td: Path) -> Path:
    proj = td / "Trace"
    (proj / "ProjectSettings").mkdir(parents=True)
    a = proj / "Assets"
    put(a / "Localisation" / "Trace Shared Data.asset", trace_shared())
    put(a / "Scripts" / "_Controller" / "WarningMessageController.cs", WARN_CS)
    put(a / "Scripts" / "_Controller" / "WarningMessageController.cs.meta", f"fileFormatVersion: 2\nguid: {WARN_GUID}\n")
    put(a / "Scripts" / "CraftSystem" / "SalvageMachine.cs", SALVAGE_CS)
    (a / "Scripts" / "CraftSystem" / "CraftController.cs").parent.mkdir(parents=True, exist_ok=True)
    write_text(a / "Scripts" / "CraftSystem" / "CraftController.cs", CRAFT_CS, newline="\r\n")   # the game's files use CRLF
    put(a / "Scripts" / "Player Menu" / "LicensePanelController.cs", LICENSE_CS)
    put(a / "Scripts" / "Player Menu" / "LicensePanelController.cs.meta", f"fileFormatVersion: 2\nguid: {LICENSE_GUID}\n")
    put(a / "Prefabs" / "WarningMessageCanvas.prefab", mono_prefab("WarningMessageCanvas", WARN_GUID,
        {"NEED_BROKEN_ITEM_LOC": 300, "ITEM_SENT_STORAGE_LOC": 301, "HOT_HANDLE_LOC": 302}))
    put(a / "Prefabs" / "License.prefab", mono_prefab("License", LICENSE_GUID,
        {"needWorkshopTextLoc": 310, "needReputationTextLoc": 311, "upgradeTextLoc": 312, "maxTextLoc": 313, "lockedString": 314,
         "occupiedString": 315, "namedLoc": 316, "busyLoc": 317}))
    return proj


def line_of(text: str, needle: str) -> int:
    return text[: text.index(needle)].count("\n") + 1


class UseTraceTests(unittest.TestCase):
    """Every loaded text is followed to the code that reads it, so a scout writes per key notes from facts."""

    @classmethod
    def setUpClass(cls):
        with TempDir() as td:
            cls.scan = bcm.scan_unity(make_trace_project(td))
            cls.blob = json.dumps(cls.scan)
            cls.td = str(td)

    def key(self, name: str) -> dict:
        return self.scan["keys"][name]

    def test_a_warning_carries_its_own_trigger_not_the_group_note(self):
        # the line note of a whole warning group said "a wrong item or the machine is busy", the code says "the machine is empty"
        info = self.key("Warning.NeedBrokenItem")
        self.assertEqual(info["loads"], [{"file": "Assets/Scripts/_Controller/WarningMessageController.cs",
                                          "line": line_of(WARN_CS, "NEED_BROKEN_ITEM = NEED"), "variable": "WarningMessageController.NEED_BROKEN_ITEM",
                                          "via": "GetLocalizedString", "scope": "static"}])
        self.assertEqual(info["uses_total"], 1)
        use = info["uses"][0]
        self.assertEqual((use["file"], use["line"]), ("Assets/Scripts/CraftSystem/SalvageMachine.cs", line_of(SALVAGE_CS, "inst.ShowWarningMessage(Warn")))
        self.assertEqual((use["method"], use["trigger"], use["concat"]), ("StartSalvage", ["if (!CanSalvage())"], False))
        self.assertEqual(use["helpers"], {"CanSalvage()": "GetTotalItemCount() > 0"})
        self.assertFalse(info["loaded_not_shown"])

    def test_a_text_loaded_and_never_read_is_flagged(self):
        # the group note said the code appends a colon and the missing amount, the variable is never read at all
        info = self.key("License.WorkshopCondition")
        self.assertEqual([(ld["variable"], ld["scope"]) for ld in info["loads"]], [("needWorkshopText", "field")])
        self.assertEqual((info["uses"], info["uses_total"], info["loaded_not_shown"]), ([], 0, True))
        hot = self.key("Warning.HotHandle")           # its only use is commented out, a string literal and a comment do not count
        self.assertEqual((hot["uses"], hot["loaded_not_shown"]), ([], True))
        self.assertEqual(self.scan["use_trace"]["loaded_not_shown"], 2)
        self.assertTrue(self.scan["use_trace"]["heuristic"])
        self.assertIn("Heuristic", self.scan["use_trace"]["note"])

    def test_static_field_uses_across_files_with_their_glue(self):
        info = self.key("Warning.ItemSentStorage")
        uses = {u["method"]: u for u in info["uses"]}
        self.assertEqual(info["uses_total"], 2)
        craft = uses["CompleteProduction"]
        self.assertEqual((craft["file"], craft["line"]), ("Assets/Scripts/CraftSystem/CraftController.cs", line_of(CRAFT_CS, "w.ShowWarningMessage($")))
        self.assertEqual((craft["shape"], craft["concat"], craft["trigger"]), ("{THIS}: {itemName}", True, ["if (sentToStorage)"]))
        dump = uses["DumpInto"]                        # a braceless if, the text handed on to another variable
        self.assertEqual((dump["trigger"], dump["assigned_to"], dump["concat"]), (["if (moved > 0)"], "message", False))
        self.assertNotIn(self.td, self.blob)           # no machine path in the output

    def test_string_changed_handler_concat_else_ternary_format_and_switch(self):
        rep = self.key("License.ReputationCondition")
        self.assertEqual([(ld["variable"], ld["via"]) for ld in rep["loads"]], [("needReputationText", "StringChanged")])
        by_line = {u["line"]: u for u in rep["uses"]}
        glued = by_line[line_of(LICENSE_CS, "hoverDescription += ")]
        self.assertEqual((glued["shape"], glued["trigger"], glued["method"]), ("{hoverDescription}{THIS} {rep - have}\r\n", ["if (rep > have)"], "DrawPanel"))
        self.assertEqual(by_line[line_of(LICENSE_CS, "hint.text = needReputationText")]["trigger"], ["else of if (have > 0)"])
        upgrade = self.key("License.Upgrade")["uses"][0]  # read in place, no variable in between
        self.assertEqual((upgrade["variable"], upgrade["shape"]), ("upgradeTextLoc", "{THIS}\n¢{amount}"))
        mx = self.key("License.Max")                     # an expression bodied handler stores the text
        self.assertEqual([(ld["variable"], ld["via"]) for ld in mx["loads"]], [("maxText", "StringChanged")])
        self.assertEqual(mx["uses"][0]["trigger"], ["when (atMax)"])
        locked, occupied = self.key("License.Locked"), self.key("License.Occupied")
        self.assertEqual((locked["loads"][0]["scope"], locked["loads"][0]["trigger"]), ("local", ["when (!active)"]))
        self.assertEqual(occupied["loads"][0]["trigger"], ["when not (!active)"])
        self.assertEqual(occupied["uses"][0]["shape"], "{hangarName} ({THIS})")
        self.assertEqual(self.key("License.Named")["uses"][0]["shape"], "{nameText}: {THIS}")
        self.assertEqual(self.key("License.Busy")["uses"][0]["trigger"], ["case State.Busy of switch (state)"])

    def test_masking_keeps_offsets_and_interpolation_holes(self):
        src = 'var a = "x // y"; // gone\nchar c = \'{\'; var b = $"{n} \\"q\\" {s.Name}" + @"v""w"; /* z */ d();\n'
        nc, mk, strings = bcm._mask_cs(src)
        self.assertEqual((len(nc), len(mk)), (len(src), len(src)))
        self.assertNotIn("gone", nc)
        self.assertIn('"x // y"', nc)                    # a comment marker inside a literal is text
        self.assertNotIn("x // y", mk)
        self.assertIn("s.Name", mk)                       # the holes stay code
        self.assertNotIn("{", mk.replace(bcm._HOLE, ""))  # neither the char literal nor the holes open a block
        self.assertEqual([(s.interp, s.verbatim) for s in strings], [(False, False), (True, False), (False, True)])
        self.assertEqual(bcm._render(bcm._CsFile("x", src).prepare(), strings[1]), '{n} "q" {s.Name}')

    def test_summary_slices_and_cli(self):
        s = bcm.summary(self.scan)
        self.assertEqual(s["loaded_not_shown"], ["License.WorkshopCondition", "Warning.HotHandle"])
        md = bcm.render_summary(self.scan, s)
        self.assertIn("`License.WorkshopCondition`", md)
        self.assertIn("heuristic", md)
        self.assertEqual(text_style.punctuation_problems(md), [])
        with TempDir() as td:
            proj = make_trace_project(td)
            tables: dict = {}
            scan = bcm.scan_unity(proj, tables_out=tables, use_sites=1)
            slices, _stats = bcm.build_slices(scan, tables, {"all": ["*"]}, "en")
            rows = {r["key"]: r for r in slices["all"]}
            sent = rows["Warning.ItemSentStorage"]
            self.assertEqual((len(sent["uses"]), sent["uses_total"]), (1, 2))      # --use-sites caps the list, the total stays
            self.assertEqual(rows["Warning.NeedBrokenItem"]["uses"][0]["trigger"], ["if (!CanSalvage())"])
            self.assertTrue(rows["License.WorkshopCondition"]["loaded_not_shown"])
            out = td / "context"
            base = ("build_context_map.py", "--scan", "--project", str(proj), "--out", str(out))
            code, stdout, err = run_cli(*base)
            self.assertEqual(code, 0, err)                                         # a text never shown is a game bug, not a failed scan
            self.assertIn("loaded but never shown", stdout)
            self.assertIn("heuristic", stdout)
            self.assertEqual(run_cli(*base, "--use-sites", "0")[0], 0)
            data = json.loads((out / "key_usage.json").read_text(encoding="utf-8"))
            self.assertNotIn("use_trace", data)
            self.assertNotIn("uses", data["keys"]["Warning.NeedBrokenItem"])
            self.assertEqual(run_cli(*base, "--use-sites", "-1")[0], 2)


class SliceTests(unittest.TestCase):
    """Scout inputs come from the project's own string tables, never from an ad hoc export."""

    def _scan(self, td: Path):
        proj = make_project(td)
        add_locales(proj)
        tables: dict = {}
        return bcm.scan_unity(proj, tables_out=tables), tables

    def test_rows_keep_paragraphs_and_every_key_lands_once(self):
        with TempDir() as td:
            scan, tables = self._scan(td)
            meta = {"Item.Name.Can": {"category": "ui", "speaker": ""}}
            slices, stats = bcm.build_slices(scan, tables, {"hud": ["Hud*"]}, "en", "tr-TR", meta)
        self.assertEqual(list(slices), ["hud"])
        rows = {r["key"]: r for r in slices["hud"]}
        self.assertEqual(sorted(rows), ["Hud.Deadline", "Hud.Stamina", "Hud.Unused", "Item.Name.Can"])
        self.assertEqual(rows["Item.Name.Can"]["en"], "A can of food.\n\nRestores some energy.")
        self.assertEqual(rows["Item.Name.Can"]["tr-TR"], "Bir kutu yemek.\n\nBiraz enerji verir.")
        self.assertEqual(rows["Hud.Deadline"]["tr-TR"], "Son Tarih")                 # not the decoy table of another collection
        self.assertEqual(rows["Hud.Stamina"]["tr-TR"], "")
        self.assertEqual(rows["Item.Name.Can"]["category"], "ui")
        self.assertEqual(rows["Hud.Deadline"]["usages"][0]["field"], "deadlineTextLoc")
        self.assertEqual(stats, {"slices": {"hud": 4}, "unassigned_tables": [], "missing_locale_tables": []})

    def test_unclaimed_overlapping_and_unknown_tables(self):
        with TempDir() as td:
            scan, tables = self._scan(td)
            slices, stats = bcm.build_slices(scan, tables, {"menus": ["Menu*", "Hud*"]}, "en", "de-DE")
            self.assertEqual(stats["missing_locale_tables"], ["HudTable de-DE"])
            scan["tables"].append("Codex")                                          # a second table no slice claims
            scan["keys"]["Codex.Intro"] = {"table": "Codex", "usages": [], "code": []}
            tables["Codex"] = {"shared": tables["HudTable"]["shared"], "ids": {}}
            slices, stats = bcm.build_slices(scan, tables, {"hud": ["HudTable"]}, "en")
            self.assertEqual([r["key"] for r in slices[bcm.UNASSIGNED]], ["Codex.Intro"])
            self.assertEqual(stats["unassigned_tables"], ["Codex"])
            with self.assertRaises(L10nError):
                bcm.build_slices(scan, tables, {"a": ["HudTable"], "b": ["Hud*"]}, "en")   # one table in two slices
            with self.assertRaises(L10nError):
                bcm.build_slices(scan, tables, {"a": ["Nope*"]}, "en")                     # a typo claims nothing
            for bad in ('{"unassigned": ["Hud*"]}', '{"a b": ["Hud*"]}', '{"a": []}', '[]'):
                with self.assertRaises(L10nError):
                    bcm.load_slice_spec(write_text(td / "spec.json", bad))


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

    def test_slices_and_check_slices_cli(self):
        with TempDir() as td:
            proj = make_project(td)
            add_locales(proj)
            out = td / "context"
            spec = write_text(td / "spec.json", '{"hud": ["HudTable"]}')
            code, _, err = run_cli("build_context_map.py", "--scan", "--project", str(proj), "--out", str(out), "--slices", str(spec), "--locale", "tr-TR")
            self.assertEqual(code, 0, err)
            rows = json.loads((out / "slices" / "hud.input.json").read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 4)
            self.assertIn("\n\n", next(r["en"] for r in rows if r["key"] == "Item.Name.Can"))
            check = ("build_context_map.py", "--check-slices", "--out", str(out))
            self.assertEqual(run_cli(*check)[0], 1)                                 # no scout report yet
            entry = {"screen": "", "element": "", "player_action": "", "inserted": "", "limit": "", "speaker": "",
                     "listener": "", "register_hint": "", "notes": "", "questions": ["who reads this"]}
            report = out / "slices" / "hud.report.json"
            write_text(report, json.dumps([dict(entry, keys=["Hud.Deadline", "Hud.Stamina"]), dict(entry, keys=["Hud.Unused", "Item.Name.Can"])]))
            code, stdout, err = run_cli(*check, "--json")
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(stdout)["slices"]["hud"]["questions"], 2)
            write_text(report, json.dumps([dict(entry, keys=["Hud.Deadline", "Hud.Stamina", "Hud.Unused"]), dict(entry, keys=["Hud.Unused", "Nope"])]))
            code, stdout, _ = run_cli(*check, "--json")
            res = json.loads(stdout)["slices"]["hud"]
            self.assertEqual((code, res["missing"], res["duplicated"], res["unknown"]), (1, ["Item.Name.Can"], ["Hud.Unused"], ["Nope"]))
            self.assertEqual(run_cli(*check, "--scan", "--project", str(proj))[0], 2)  # one mode at a time
            self.assertEqual(run_cli("build_context_map.py", "--check-slices", "--out", str(td / "empty"))[0], 2)


class ContextInPromptTests(unittest.TestCase):
    """Jurors read the map and the neutral line fields. Writers also read the scout notes and the locale appendix,
    which holds the studio's own choices and would hand a calibrated juror its answer key."""

    def _map(self, td: Path) -> Path:
        folder = td / "context"
        m = put(folder / "CONTEXT_MAP.md", "MAP-TEXT the game on one page\n")
        put(folder / "CONTEXT_MAP.tr-TR.md", "APPENDIX-TR studio choices\n")
        notes = {"HudTable:Hud.Deadline": {"screen": "day start HUD", "element": "label", "notes": "SCOUT-NOTE", "questions": ["q"]},
                 "DLG_1": {"screen": "workshop", "speaker": "Mentor", "notes": "SCOUT-NOTE"},
                 "K00": {"screen": "contract letter", "notes": "SCOUT-NOTE"}}
        put(folder / "line_notes.json", json.dumps(notes))
        return m

    def test_pack(self):
        with TempDir() as td:
            m = self._map(td)
            pack = bcm.load_context(m, "tr-TR")
            self.assertEqual(pack.line("Hud.Deadline"), {"screen": "day start HUD", "element": "label"})   # plain name of a Table:Key label
            self.assertEqual(pack.line("Hud.Deadline", writer=True)["notes"], "SCOUT-NOTE")
            self.assertEqual(pack.line("Nope"), {})
            juror, writer = pack.system("BASE"), pack.system("BASE", writer=True)
            self.assertTrue(juror.startswith("BASE") and "MAP-TEXT" in juror and "APPENDIX-TR" not in juror)
            self.assertIn("APPENDIX-TR", writer)
            items = [{"key": "DLG_1"}, {"key": "K00", "context": {"screen": "given"}}, {"key": "none"}]
            self.assertEqual(pack.enrich(items), 1)
            self.assertEqual((items[0]["context"], items[1]["context"]), ({"screen": "workshop", "speaker": "Mentor"}, {"screen": "given"}))
            self.assertEqual(bcm.load_context(m, "de-DE").appendix, "")
            self.assertEqual(bcm.load_context(None).system("BASE"), "BASE")
            self.assertEqual(text_style.punctuation_problems(bcm.MAP_HEADER + "\n" + bcm.APPENDIX_HEADER), [])
            # the header travels with the line notes, so every locale's juror and writer learns to read inserted and limit
            for field in ("`inserted`", "`limit`", "`screen`", "`player_action`"):
                self.assertIn(field, bcm.MAP_HEADER)
            self.assertIn("form of address", bcm.APPENDIX_HEADER)
            prompts = SCRIPTS.parent / "prompts"
            critic = (prompts / "critic.tr-TR.md").read_text(encoding="utf-8")
            self.assertIn("`context`", critic)
            self.assertIn("`inserted`", critic)
            self.assertIn("son satıra kadar siz der", (prompts / "pass2.tr-TR.md").read_text(encoding="utf-8"))
            with self.assertRaises(L10nError):
                bcm.load_context(td / "missing.md")
            with self.assertRaises(L10nError):
                bcm.load_context(put(td / "empty" / "CONTEXT_MAP.md", "  \n"))
            put(td / "bad" / "line_notes.json", "{oops")
            with self.assertRaises(L10nError):
                bcm.load_context(put(td / "bad" / "CONTEXT_MAP.md", "map"))

    def test_jurors_read_the_english_view_and_the_leak_check_finds_the_answer_key(self):
        # the first map was written in Turkish by scouts who had read the studio's Turkish, so the jurors saw the studio's words
        with TempDir() as td:
            folder = td / "context"
            m = put(folder / "CONTEXT_MAP.md", "Oyuncu kontrat mektubunu okur.\n")
            put(folder / "line_notes.json", json.dumps({"K00": {"screen": "kontrat mektubu", "notes": "stüdyo kontrat dedi"}}))
            ref = write_text(td / "ref.csv", "key,en,tr-TR\nK00,Read the contract letter from the Federation office,Federasyon ofisinden gelen kontrat mektubunu oku\n")
            leak = ("build_context_map.py", "--check-leak", "--context-map", str(m), "--reference", str(ref), "--locale", "tr-TR", "--json")
            code, out, err = run_cli(*leak)
            self.assertEqual(code, 1, err)
            self.assertIn("kontrat", [w for w, _n, _first in json.loads(out)["words"]])
            put(folder / "CONTEXT_MAP.jury.md", "The task line says Read the contract letter from the Federation office.\n")
            put(folder / "line_notes.jury.json", json.dumps({"K00": {"screen": "contract letter", "notes": "jury notes carry no scout notes"}}))
            pack = bcm.load_context(m, "tr-TR")
            self.assertEqual(pack.line("K00"), {"screen": "contract letter"})                 # jurors read the English view
            self.assertEqual(pack.line("K00", writer=True)["screen"], "kontrat mektubu")     # writers keep the user's map
            self.assertIn("the contract letter from", pack.system("BASE"))
            self.assertIn("kontrat mektubunu", pack.system("BASE", writer=True))
            code, out, err = run_cli(*leak)
            data = json.loads(out)
            self.assertEqual((data["view"], data["words"]), ("jury", []))
            self.assertEqual(data["quoted_source_lines"], ["read the contract letter from the federation office"])   # a quoted source line
            self.assertEqual(code, 1, err)
            put(folder / "CONTEXT_MAP.jury.md", "The player reads a letter about a contract.\n")
            self.assertEqual(run_cli(*leak)[0], 0)

    def test_calibration_jurors_get_the_map_but_no_answer_key(self):
        import eval_critic as ec
        from providers import Router, load_providers_config
        seen = []

        def spy(real):
            def call(provider, items, locale, **kw):
                seen.append((kw["system"], items))
                return real(provider, items, locale, **kw)
            return call
        pairs = [{"key": f"K0{i}", "native": f"Acele etme evlat {i}.", "robot": f"Zamanını al çocuk {i}.", "register": "dialogue_casual"} for i in range(3)]
        with TempDir() as td, mock.patch.object(ec, "pairwise_choices", spy(ec.pairwise_choices)), mock.patch.object(ec, "score_entries", spy(ec.score_entries)):
            rep = ec.evaluate(Router(load_providers_config(), dry_run=True), "tr-TR", ["J1"], pairs, [], warmup=False, pack_dir=None, seed=1,
                              warmup_count=5, pairwise_min=0.85, langpack_version=None, context=bcm.load_context(self._map(td), "tr-TR"))
        self.assertEqual((rep["context_map"], rep["context_lines"]), ("CONTEXT_MAP.md", 1))
        self.assertTrue(seen)
        for system, items in seen:
            self.assertIn("MAP-TEXT", system)
            self.assertNotIn("APPENDIX-TR", system)
            blob = json.dumps(items)
            self.assertIn("contract letter", blob)
            self.assertNotIn("SCOUT-NOTE", blob)

    def test_jury_cli_records_the_map(self):
        with TempDir() as td:
            m = self._map(td)
            blind = write_text(td / "blind_tr-TR_01.json", json.dumps({"entries": [{"key": "Hud.Deadline", "target": "Son tarih"}, {"key": "X", "target": "Kaydet"}]}))
            out = td / "v.json"
            common = ("jury.py", str(blind), "--locale", "tr-TR", "--dry-run", "--langpack-dir", str(td / "np"), "--out", str(out))
            code, _, err = run_cli(*common, "--context-map", str(m), env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            prompt = json.loads(out.read_text(encoding="utf-8"))["prompt"]
            self.assertEqual((prompt["context_map"], prompt["context_lines"]), ("CONTEXT_MAP.md", 1))
            self.assertEqual(run_cli(*common, "--context-map", str(td / "nope.md"), env_extra=NO_KEYS)[0], 2)
            # --config was accepted and never read, the map in l10n.config.json is used now, an explicit flag still wins
            cfg = write_text(td / "l10n.config.json", json.dumps({"context_map": "context/CONTEXT_MAP.md"}))
            self.assertEqual(run_cli(*common, "--config", str(cfg), env_extra=NO_KEYS)[0], 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["prompt"]["context_map"], "CONTEXT_MAP.md")
            bad = write_text(td / "bad.config.json", json.dumps({"context_map": "nowhere/CONTEXT_MAP.md"}))
            self.assertEqual(run_cli(*common, "--config", str(bad), env_extra=NO_KEYS)[0], 2)
            self.assertEqual(run_cli(*common, "--config", str(bad), "--context-map", str(m), env_extra=NO_KEYS)[0], 0)

    def test_orchestrator_writers_and_jurors(self):
        import jury
        import llm_tasks
        import orchestrator_stub as orch
        import pass2_rewrite
        import test_orchestrator_jury as toj
        from providers import FakeScenario, Router, load_providers_config
        seen: dict = {"pass1": [], "jury": [], "pass2": [], "pick": []}

        def spy(name, real):
            def call(provider, items, locale, **kw):
                seen[name].append((kw["system"], json.dumps(items, ensure_ascii=False)))
                return real(provider, items, locale, **kw)
            return call
        with TempDir() as td, \
                mock.patch.object(llm_tasks, "translate_rows", spy("pass1", llm_tasks.translate_rows)), \
                mock.patch.object(jury, "score_entries", spy("jury", jury.score_entries)), \
                mock.patch.object(pass2_rewrite, "pass2_candidates", spy("pass2", pass2_rewrite.pass2_candidates)), \
                mock.patch.object(pass2_rewrite, "pick_candidates", spy("pick", pass2_rewrite.pick_candidates)):
            src = write_text(td / "src.json", json.dumps(toj.SOURCE))
            router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(toj.SCENARIO))
            res = orch.run_jury_pipeline(src, "tr-TR", td / "w", router, budget_caps=False, langpack_dir=td / "np", context_map=self._map(td))
            verdicts = json.loads((td / "w" / "verdicts_tr-TR_01.json").read_text(encoding="utf-8"))
        self.assertTrue(any("Phase 0: context map CONTEXT_MAP.md" in line for line in res["log"]))
        self.assertEqual(verdicts["prompt"]["context_lines"], 1)
        for name in seen:
            self.assertTrue(seen[name], name)
            for system, items in seen[name]:
                self.assertIn("MAP-TEXT", system)
                writer = name in ("pass1", "pass2")
                self.assertEqual("APPENDIX-TR" in system, writer, name)   # the appendix reaches writers only
                if "DLG_1" in items:
                    self.assertIn("workshop", items)
                    self.assertEqual("SCOUT-NOTE" in items, writer, name)


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


class AssetTableScoutTests(unittest.TestCase):
    """An AssetTable holds asset GUIDs, a scout never gets its entries as text (DecalTextures of the first game)."""

    @staticmethod
    def _table(script: str, code: str, value: str) -> str:
        return ("%YAML 1.1\n--- !u!114 &11400000\nMonoBehaviour:\n"
                f"  m_Script: {{fileID: 11500000, guid: {script}, type: 3}}\n  m_LocaleId:\n    m_Code: {code}\n"
                "  m_SharedData: {fileID: 11400000, guid: 0123456789abcdef0123456789abcdef, type: 2}\n"
                f"  m_TableData:\n  - m_Id: 1\n    m_Localized: {value}\n    m_Metadata:\n      m_Items: []\n")

    def test_locale_tables_skips_an_asset_table(self):
        from l10n_common import UNITY_ASSET_TABLE_SCRIPT
        with TempDir() as td:
            (td / "Decals").mkdir()
            (td / "General").mkdir()
            write_text(td / "Decals" / "Decals Shared Data.asset", "%YAML 1.1\n")
            write_text(td / "Decals" / "Decals_fr.asset", self._table(UNITY_ASSET_TABLE_SCRIPT, "fr", "99f909044abd13e43b187a1e55a4e2c5"))
            write_text(td / "General" / "General Shared Data.asset", "%YAML 1.1\n")
            write_text(td / "General" / "General_fr.asset", self._table("e9620f8c34305754d8cc9a7e49e852d9", "fr", "Bonjour"))
            self.assertEqual(bcm.locale_tables(td / "Decals" / "Decals Shared Data.asset"), {})
            self.assertEqual(list(bcm.locale_tables(td / "General" / "General Shared Data.asset")), ["fr"])


if __name__ == "__main__":
    unittest.main()
