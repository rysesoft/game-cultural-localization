#!/usr/bin/env python3
"""Context map facts. Where every localization key of a game project is used.

Phase 0 step 0 of the methodology. `context-cartographer` (Claude Opus) and its `context-scout`
agents (Claude Sonnet) write CONTEXT_MAP.md, the document every translator and juror reads first.
This tool collects the facts they would otherwise gather by hand. For every key the files, the
objects (with their hierarchy path), the classes and the fields that use it, and the code lines
that show it, with a flag where the code glues the text to something else.

Engines
  Unity  Unity Localization string tables (Shared Data assets), LocalizedString fields and
         LocalizeStringEvent components in prefabs, scenes and ScriptableObjects. References by
         table GUID or table name and by key id or key name are all resolved.
  other  exit 2 for now, the agents read that engine's code directly.

The tool only reads the project. Paths longer than the Windows limit are read with the long path
prefix. Output paths are relative to the project, so the files never carry a machine path.

Usage
  python build_context_map.py --scan --project "<unity project>" --out loc_work/context
  python build_context_map.py --scan --project "<unity project>" --out loc_work/context --keys-from loc_work/reference/tr.csv
  python build_context_map.py --scan --project "<unity project>" --out loc_work/context --slices slices.json --locale tr-TR
  python build_context_map.py --check-slices --out loc_work/context

Output in --out
  key_usage.json            {"engine", "tables", "keys": {key: {"table", "usages": [...], "code": [...]}}}
  scan_summary.md           coverage, tables, classes per table, keys without a usage
  slices/<slice>.input.json with --slices, the input of one context-scout. Rows carry the key, the table,
                            the source text and the --locale text read from the project's own string tables
                            (paragraph breaks intact), category and speaker from --keys-from, usages and code.
                            Every table lands in exactly one slice, unclaimed tables go to unassigned.input.json.

--check-slices reads slices/<slice>.input.json and the scout's slices/<slice>.report.json and reports keys
that are missing, sit in two report entries or are not in the input.

Exit codes: 0 written or covered, 1 findings (keys of --keys-from without a usage, unclaimed tables, missing
locale tables, gaps in the scout reports), 2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, emit_report, load_table, parse_unity_yaml, run_main, __version__,
)

TOOL = "build_context_map"
CODE_LINES_PER_FIELD = 4
ASSET_EXTS = (".prefab", ".unity", ".asset")
_DOC = re.compile(r"^--- !u!(\d+) &(-?\d+)", re.M)
_REF = re.compile(r"^( *)(?:- )?m_TableReference:\n *m_TableCollectionName: ?(.*)\n *m_TableEntryReference:\n *m_KeyId: (-?\d+)\n *m_Key: ?(.*)$", re.M)
_PARENT = re.compile(r"^( *)(?:- )?([A-Za-z_]\w*):\s*$")
_ENTRY = re.compile(r"- m_Id: (-?\d+)\n\s+m_Key: (.*)")
# a scene or prefab can bind a key through a prefab override, the reference then lives in m_Modifications
_MOD = re.compile(r"- target: \{fileID: (-?\d+), guid: (\w+), type: \d+\}\n\s+propertyPath: (.+)\n\s+value: ?(.*)")
_MOD_SLOTS = ((".m_TableEntryReference.m_KeyId", "id"), (".m_TableEntryReference.m_Key", "key"),
              (".m_TableReference.m_TableCollectionName", "table"))
_DECL = re.compile(r"\bLocalized\w*\s+\w+\s*[;=]")
_CONCAT = re.compile(r"\+|\$\"|string\.Format|\.Format\(|Concat\(")


def read_text(path: Path) -> str:
    """UTF-8 text of a project file, also when its absolute path is longer than the Windows limit."""
    p = str(path.resolve())
    if os.name == "nt" and not p.startswith("\\\\?\\"):
        p = "\\\\?\\" + p
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def find_unity_root(project: Path) -> Path:
    """The Assets folder of a Unity project (the project folder or its Assets folder may be given)."""
    project = Path(project)
    for cand in (project, project / "Assets"):
        if cand.name == "Assets" and cand.is_dir() and (cand.parent / "ProjectSettings").is_dir():
            return cand
    if (project / "Assets").is_dir() and (project / "ProjectSettings").is_dir():
        return project / "Assets"
    raise L10nError(f"{project}: not a Unity project (no Assets and ProjectSettings folders). --scan supports Unity only for now, "
                    "the context agents read other engines' code directly")


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root.parent).as_posix()
    except ValueError:
        return path.name


def load_tables(files: Sequence[Tuple[Path, str]], shared_paths: Optional[Dict[str, Path]] = None
                ) -> Tuple[Dict[str, str], Dict[str, str], Dict[Tuple[str, str], str], Dict[str, set]]:
    """Shared Data assets -> (guid -> table name, table name -> guid, (guid, key id) -> key, guid -> key names).

    shared_paths, when given, receives table name -> Shared Data file (the locale tables sit next to it).
    """
    names: Dict[str, str] = {}
    by_name: Dict[str, str] = {}
    by_id: Dict[Tuple[str, str], str] = {}
    keys: Dict[str, set] = {}
    for _path, txt in files:
        if "m_TableCollectionNameGuidString" not in txt:
            continue
        nm = re.search(r"\n  m_TableCollectionName: (.+)", txt)
        gd = re.search(r"m_TableCollectionNameGuidString: (\w+)", txt)
        if not nm or not gd:
            continue
        guid, name = gd.group(1), nm.group(1).strip()
        names[guid] = name
        by_name[name] = guid
        if shared_paths is not None:
            shared_paths[name] = _path
        keys.setdefault(guid, set())
        for kid, key in _ENTRY.findall(txt):
            by_id[(guid, kid)] = key.strip()
            keys[guid].add(key.strip())
    return names, by_name, by_id, keys


def script_classes(root: Path) -> Dict[str, Path]:
    """MonoBehaviour script guid -> .cs file."""
    return _guid_map(root, "*.cs.meta")


def _guid_map(root: Path, pattern: str) -> Dict[str, Path]:
    """Asset guid -> asset file, from the .meta files matching pattern."""
    out: Dict[str, Path] = {}
    for meta in root.rglob(pattern):
        m = re.search(r"guid: (\w+)", read_text(meta))
        if m:
            out[m.group(1)] = meta.with_suffix("")
    return out


def _docs(txt: str) -> Dict[str, Tuple[str, str]]:
    """YAML documents of a Unity file, fileID -> (class id, text)."""
    starts = [(m.start(), m.group(1), m.group(2)) for m in _DOC.finditer(txt)]
    out: Dict[str, Tuple[str, str]] = {}
    for i, (s, cls, fid) in enumerate(starts):
        out[fid] = (cls, txt[s:starts[i + 1][0] if i + 1 < len(starts) else len(txt)])
    return out


def _field(m_docs: str, pos: int, indent: int) -> str:
    """The serialized field that holds the reference (the nearest parent key with a smaller indent)."""
    for line in reversed(m_docs[:pos].splitlines()):
        pm = _PARENT.match(line)
        if pm and len(pm.group(1)) < indent:
            return pm.group(2)
    return ""


def object_paths(docs: Dict[str, Tuple[str, str]]) -> Dict[str, str]:
    """GameObject fileID -> hierarchy path (Parent/Child/Object) from the Transform and RectTransform documents."""
    go_name: Dict[str, str] = {}
    tr_of_go: Dict[str, str] = {}
    father: Dict[str, str] = {}
    go_of_tr: Dict[str, str] = {}
    for fid, (cls, d) in docs.items():
        if cls == "1":  # GameObject
            nm = re.search(r"\n  m_Name: (.*)", d)
            go_name[fid] = nm.group(1).strip() if nm else ""
        elif cls in ("4", "224"):  # Transform, RectTransform
            g = re.search(r"m_GameObject: \{fileID: (-?\d+)\}", d)
            f = re.search(r"m_Father: \{fileID: (-?\d+)\}", d)
            if g:
                tr_of_go[g.group(1)] = fid
                go_of_tr[fid] = g.group(1)
            if f:
                father[fid] = f.group(1)
    paths: Dict[str, str] = {}
    for go, name in go_name.items():
        parts = [name]
        tr = tr_of_go.get(go)
        for _ in range(12):
            tr = father.get(tr or "", "0")
            if tr == "0" or tr not in go_of_tr:
                break
            parts.append(go_name.get(go_of_tr[tr], ""))
        paths[go] = "/".join(p for p in reversed(parts) if p)
    return paths


def _override_usages(d: str, path: Path, root: Path, keys: Dict[str, Dict[str, Any]], by_name: Dict[str, str],
                     by_id: Dict[Tuple[str, str], str], by_key: Dict[Tuple[str, str], str], guids_of_id: Dict[str, List[str]],
                     prefabs: Dict[str, Path]) -> int:
    """Usages a prefab instance sets through m_Modifications. Returns the number of overrides that resolve to no key."""
    groups: Dict[Tuple[str, str, str], Dict[str, str]] = defaultdict(dict)
    for tfid, tguid, ppath, val in _MOD.findall(d):
        for suffix, slot in _MOD_SLOTS:
            if ppath.strip().endswith(suffix):
                groups[(tfid, tguid, ppath.strip()[: -len(suffix)])][slot] = val.strip()
    unresolved = 0
    for (_tfid, tguid, prefix), g in groups.items():
        table_ref = g.get("table", "")
        guid = table_ref[5:] if table_ref.startswith("GUID:") else by_name.get(table_ref, "")
        kid = g.get("id", "")
        key = ""
        if kid and kid != "0":
            if not guid and len(guids_of_id.get(kid, [])) == 1:  # the table stays in the base prefab, the id is unique
                guid = guids_of_id[kid][0]
            key = by_id.get((guid, kid), "")
        elif g.get("key"):
            key = by_key.get((guid, g["key"]), g["key"] if g["key"] in keys else "")
        if not key:
            unresolved += 1 if (kid or g.get("key")) else 0
            continue
        field = prefix.split(".")[-1]
        prefab = prefabs.get(tguid)
        use = {"file": _rel(path, root), "object": (prefab.stem if prefab else "prefab instance") + " (override)",
               "class": "LocalizeStringEvent" if field == "m_StringReference" else "", "field": field}
        if use not in keys[key]["usages"]:
            keys[key]["usages"].append(use)
    return unresolved


def scan_unity(project: Path, code_lines: int = CODE_LINES_PER_FIELD, tables_out: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Every key usage of a Unity project. Read only.

    tables_out, when given, receives table name -> {"shared": Shared Data file, "ids": key id -> key}.
    """
    root = find_unity_root(project)
    files: List[Tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        if path.suffix in ASSET_EXTS and path.is_file():
            txt = read_text(path)
            if "m_TableReference" in txt or "m_TableEntryReference" in txt or "m_TableCollectionNameGuidString" in txt:
                files.append((path, txt))
    shared_paths: Dict[str, Path] = {}
    names, by_name, by_id, table_keys = load_tables(files, shared_paths)
    if not names:
        raise L10nError(f"{root}: no Unity Localization string table (Shared Data asset) found")
    # a key name two tables share is labelled Table:Key, as the reference exports of studios do, so neither is lost
    name_count = Counter(k for ks in table_keys.values() for k in ks)

    def label(guid: str, k: str) -> str:
        return f"{names[guid]}:{k}" if name_count[k] > 1 else k

    by_id = {gk: label(gk[0], k) for gk, k in by_id.items()}
    by_key = {(g, k): label(g, k) for g, ks in table_keys.items() for k in ks}
    scripts = script_classes(root)
    prefabs = _guid_map(root, "*.prefab.meta")
    guids_of_id: Dict[str, List[str]] = defaultdict(list)
    for (g, kid) in by_id:
        guids_of_id[kid].append(g)
    if tables_out is not None:
        for guid, name in names.items():
            tables_out[name] = {"shared": shared_paths[name], "ids": {kid: k for (g, kid), k in by_id.items() if g == guid}}
    keys: Dict[str, Dict[str, Any]] = {}
    for guid, ks in table_keys.items():
        for k in ks:
            keys[label(guid, k)] = {"table": names[guid], "usages": [], "code": []}
            if name_count[k] > 1:
                keys[label(guid, k)]["name"] = k
    unresolved = 0
    missing_tables: Counter = Counter()
    seen_fields: Dict[Tuple[str, str], Path] = {}
    for path, txt in files:
        if "m_TableReference" not in txt and "m_TableEntryReference" not in txt:
            continue
        docs = _docs(txt)
        paths = object_paths(docs)
        for _fid, (_cls, d) in docs.items():
            if _cls == "1001" and "m_TableEntryReference" in d:  # prefab instance with overridden localized strings
                unresolved += _override_usages(d, path, root, keys, by_name, by_id, by_key, guids_of_id, prefabs)
            if "m_TableReference" not in d or _cls == "1001":
                continue
            sm = re.search(r"m_Script: \{fileID: \d+, guid: (\w+)", d)
            script = scripts.get(sm.group(1)) if sm else None
            gm = re.search(r"m_GameObject: \{fileID: (-?\d+)\}", d)
            obj = paths.get(gm.group(1), "") if gm and gm.group(1) != "0" else ""
            if not obj:
                nm = re.search(r"\n  m_Name: (.+)", d)
                obj = nm.group(1).strip() if nm else ""
            for m in _REF.finditer(d):
                table_ref, kid, kname = m.group(2).strip(), m.group(3), m.group(4).strip()
                guid = table_ref[5:] if table_ref.startswith("GUID:") else by_name.get(table_ref, "")
                key = by_id.get((guid, kid)) if kid not in ("0", "") else by_key.get((guid, kname), "")
                if not key and not table_ref and kname in keys:  # no table set, the name is unique
                    key = kname
                if not key:
                    if table_ref and guid not in names:  # a table the project no longer has, usually an old system
                        missing_tables[table_ref] += 1
                    elif table_ref:
                        unresolved += 1
                    continue
                field = _field(d, m.start(), len(m.group(1)))
                cls = script.stem if script else ("LocalizeStringEvent" if field == "m_StringReference" else "")
                use = {"file": _rel(path, root), "object": obj, "class": cls, "field": field}
                if use not in keys[key]["usages"]:
                    keys[key]["usages"].append(use)
                if script is not None and field:
                    seen_fields[(cls, field)] = script
    # code lines that show each localized field
    code_cache: Dict[Path, List[str]] = {}
    field_code: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for (cls, field), script in seen_fields.items():
        lines = code_cache.setdefault(script, read_text(script).splitlines())
        rx = re.compile(r"\b" + re.escape(field) + r"\b")
        hits: List[Dict[str, Any]] = []
        for n, line in enumerate(lines, start=1):
            s = line.strip()
            if rx.search(s) and not _DECL.search(s) and not s.startswith(("//", "[", "///")):
                hits.append({"file": _rel(script, root), "line": n, "text": s[:240], "concat": bool(_CONCAT.search(s))})
                if len(hits) >= code_lines:
                    break
        field_code[(cls, field)] = hits
    for info in keys.values():
        for u in info["usages"]:
            for h in field_code.get((u["class"], u["field"]), []):
                if h not in info["code"]:
                    info["code"].append(h)
    return {"engine": "unity", "project": root.parent.name, "tables": sorted(names.values()),
            "keys": {k: keys[k] for k in sorted(keys)}, "unresolved_references": unresolved,
            "missing_table_references": dict(sorted(missing_tables.items()))}


def summary(scan: Dict[str, Any], wanted: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Coverage numbers, per table counts and the main classes per table."""
    keys = scan["keys"]
    per_table: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"keys": 0, "used": 0, "classes": Counter()})
    for k, info in keys.items():
        t = per_table[info["table"]]
        t["keys"] += 1
        t["used"] += 1 if info["usages"] else 0
        for u in info["usages"]:
            t["classes"][u["class"] or "unknown"] += 1
    out = {"tables": {name: {"keys": t["keys"], "used": t["used"], "classes": [c for c, _ in t["classes"].most_common(4)]}
                      for name, t in sorted(per_table.items())},
           "keys": len(keys), "used": sum(1 for i in keys.values() if i["usages"]),
           "concat_lines": len({(c["file"], c["line"]) for i in keys.values() for c in i["code"] if c["concat"]}),
           "dangling_references": scan.get("unresolved_references", 0),
           "missing_table_references": scan.get("missing_table_references", {})}
    if wanted is not None:
        shared_names: Dict[str, List[str]] = defaultdict(list)  # a plain name two tables share stands for each of its labels
        for k, info in keys.items():
            if info.get("name"):
                shared_names[info["name"]].append(k)
        missing = [k for k in wanted if not keys.get(k, {}).get("usages") and not any(keys[x]["usages"] for x in shared_names.get(k, []))]
        out["wanted"] = len(wanted)
        out["wanted_missing"] = missing
    return out


def render_summary(scan: Dict[str, Any], s: Dict[str, Any]) -> str:
    """scan_summary.md in the house style (no semicolons, dashes or colons inside sentences)."""
    lines = [f"# Context scan of {scan['project']}", "",
             f"Engine {scan['engine']}. {s['keys']} keys in {len(scan['tables'])} string tables, {s['used']} of them have at least one usage in a prefab, scene or data asset.",
             f"{s['concat_lines']} code lines glue a localized text to something else (a name, a number or another text). They belong in the transcreation ledger as concatenation seams."]
    if s.get("dangling_references"):
        lines.append(f"{s['dangling_references']} references point to a key (by id or by name) that its table no longer has. The game shows nothing or a fallback there, list them as game bugs.")
    if s.get("missing_table_references"):
        gone = ", ".join(f"{t} ({n})" for t, n in s["missing_table_references"].items())
        lines.append(f"References to tables the project no longer has, usually an old system that was replaced. {gone}.")
    lines.append("")
    if "wanted" in s:
        lines.append(f"Of the {s['wanted']} keys of the reference table, {s['wanted'] - len(s['wanted_missing'])} have a usage and {len(s['wanted_missing'])} have none.")
        lines.append("")
    lines += ["| Table | Keys | With usage | Main classes |", "|---|---|---|---|"]
    for name, t in s["tables"].items():
        lines.append(f"| {name} | {t['keys']} | {t['used']} | {', '.join(t['classes']) or 'none found'} |")
    if s.get("wanted_missing"):
        lines += ["", "Keys without a usage (first 40). The agents look for them in the code by name.", ""]
        lines += [f"- `{k}`" for k in s["wanted_missing"][:40]]
    return "\n".join(lines) + "\n"


_SLICE_NAME = re.compile(r"[A-Za-z0-9_.-]+")
UNASSIGNED = "unassigned"

# --------------------------------------------------------------------------- #
# The map in model prompts (used by eval_critic, jury, pass2_rewrite, orchestrator_stub)
# --------------------------------------------------------------------------- #
JUROR_FIELDS = ("screen", "element", "player_action", "inserted", "limit", "speaker", "listener", "register_hint")
JURY_MAP = "CONTEXT_MAP.jury.md"        # the jurors' view of the map, in English
JURY_NOTES = "line_notes.jury.json"     # the jurors' view of the line notes, in English
WRITER_FIELDS = JUROR_FIELDS + ("notes",)
MAP_HEADER = ("# Context map of this game\n\n"
              "Read this map before the first line. It describes the game, its world, its systems and its screens, as a professional "
              "translator learns them from the code before translating. It never decides a word for you. The same source word takes "
              "different words in your language depending on where the game shows it, so judge and write every line for its place. "
              "An item may carry a `context` object with the screen and the element that show the line, what the player is doing, "
              "what the code inserts next to it, the room it has, the speaker and the listener. Read it before you judge or write the "
              "line. `screen` and `element` tell a button from a title, a toast or a letter, `player_action` tells what the player "
              "wants in that moment. `inserted` names what the code puts next to the text when the game runs, a name, a number, a "
              "unit or another text. The line must still read right together with it, a label the code follows with a colon and a "
              "number takes no punctuation of its own, and a sentence the code ends with a name must take that name in the grammar "
              "of your language. `limit` is the room the line has. `speaker` and `listener` set the voice and the form of address.")
APPENDIX_HEADER = ("# Decisions of the existing {locale} version\n\n"
                   "The published {locale} version of the game made these choices. Stay consistent with them unless the context of a line "
                   "says otherwise. Keep the form of address it sets for every character, a character who speaks formally to the player "
                   "does so to the last line.")


@dataclass
class ContextPack:
    """CONTEXT_MAP.md, its per key line notes and the locale appendix, ready for model prompts.

    Jurors and critics get the map and the neutral line fields only. Writers (Pass 1, Pass 2) also get the
    scout notes and the locale appendix, which holds the existing translation's choices and would hand a
    calibrated juror its answer key.
    """
    text: str = ""
    notes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    appendix: str = ""
    locale: str = ""
    source: str = ""
    jury_text: str = ""                                                     # CONTEXT_MAP.jury.md, English
    jury_notes: Dict[str, Dict[str, Any]] = field(default_factory=dict)     # line_notes.jury.json, English

    def __post_init__(self) -> None:
        self._plain = _plain_labels(self.notes)
        self._jury_plain = _plain_labels(self.jury_notes)

    def line(self, key: str, writer: bool = False) -> Dict[str, str]:
        """Context fields of one key (exact label, or a plain name that labels exactly one Table:Key).

        Jurors read the jury notes when they exist. The notes of the user's map are written in the user's language
        by scouts who may have seen an existing translation, so they can carry that translation's words.
        """
        notes, plain = (self.jury_notes, self._jury_plain) if not writer and self.jury_notes else (self.notes, self._plain)
        n = notes.get(key) or notes.get(plain.get(key, ""), {})
        return {f: str(n[f]) for f in (WRITER_FIELDS if writer else JUROR_FIELDS) if n.get(f)}

    def system(self, base: str, writer: bool = False) -> str:
        """The system prompt with the map appended (and the locale appendix for writers). Unchanged without a map.

        Jurors read the English jury map when it exists, writers the user's map."""
        text = self.jury_text if not writer and self.jury_text else self.text
        if not text:
            return base
        out = base.rstrip() + "\n\n" + MAP_HEADER + "\n\n" + text.strip() + "\n"
        if writer and self.appendix:
            out += "\n" + APPENDIX_HEADER.format(locale=self.locale) + "\n\n" + self.appendix.strip() + "\n"
        return out

    def enrich(self, items: Sequence[Dict[str, Any]], key_field: str = "key", writer: bool = False) -> int:
        """Add a `context` object to every item that has none. Returns how many items got one."""
        n = 0
        for it in items:
            if it.get("context"):
                continue
            ctx = self.line(str(it.get(key_field, "")), writer)
            if ctx:
                it["context"] = ctx
                n += 1
        return n


def _plain_labels(notes: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    plain: Dict[str, List[str]] = defaultdict(list)
    for label in notes:
        if ":" in label:
            plain[label.split(":", 1)[1]].append(label)
    return {k: v[0] for k, v in plain.items() if len(v) == 1}


def _load_notes(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(read_text(path).lstrip("﻿"))
    except json.JSONDecodeError as exc:
        raise L10nError(f"{path}: invalid JSON at line {exc.lineno}: {exc.msg}")
    if not isinstance(data, dict):
        raise L10nError(f"{path}: expected an object {{key: line note}}")
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def load_context(map_path: Optional[Path], locale: str = "") -> ContextPack:
    """ContextPack from CONTEXT_MAP.md and the files next to it.

    line_notes.json (scout notes), CONTEXT_MAP.<locale>.md (choices of an existing translation, writers only),
    CONTEXT_MAP.jury.md and line_notes.jury.json (the jurors' English view, used instead of the map and the
    notes when present).
    """
    if map_path is None:
        return ContextPack()
    map_path = Path(map_path)
    if not map_path.is_file():
        raise L10nError(f"--context-map file not found: {map_path}")
    text = read_text(map_path).lstrip("﻿")
    if not text.strip():
        raise L10nError(f"{map_path}: the context map is empty")
    notes = _load_notes(map_path.with_name("line_notes.json"))
    appendix_path = map_path.with_name(f"{map_path.stem}.{locale}.md") if locale else None
    appendix = read_text(appendix_path).lstrip("﻿") if appendix_path is not None and appendix_path.is_file() else ""
    jury_path = map_path.with_name(JURY_MAP)
    jury_text = read_text(jury_path).lstrip("﻿") if jury_path.is_file() else ""
    return ContextPack(text, notes, appendix, locale, map_path.name, jury_text, _load_notes(map_path.with_name(JURY_NOTES)))


# --------------------------------------------------------------------------- #
# Leak check of the jurors' view
# --------------------------------------------------------------------------- #
_WORD = re.compile(r"[^\W\d_]{4,}")


def _words(text: str) -> set:
    return {w.casefold() for w in _WORD.findall(text or "")}


def target_only_words(rows: Sequence[Any]) -> set:
    """Words (4 letters or more) of an existing translation that its source never uses. Juror text must not hold them."""
    src: set = set()
    tgt: set = set()
    for r in rows:
        src |= _words(r.src)
        tgt |= _words(r.dst)
    return tgt - src


def check_leak(pack: ContextPack, rows: Sequence[Any], quote_min: int = 25) -> Dict[str, Any]:
    """What the jurors read against an existing translation. Words only that translation uses, and quoted source lines.

    The first calibration with a map passed partly on such words. Its scouts wrote the map in Turkish after reading the
    studio's Turkish, so the jurors saw the studio's names (on 400 pairs the juror fields shared words with the studio
    line only 115 times and with the literal line only 18 times).
    """
    vocab = target_only_words(rows)
    texts: List[Tuple[str, str]] = [("map", pack.jury_text or pack.text)]
    for key in (pack.jury_notes or pack.notes):
        texts.append((key, " ".join(pack.line(key).values())))
    hits: Counter = Counter()
    first: Dict[str, str] = {}
    leaky_notes = 0
    for name, text in texts:
        found = _words(text) & vocab
        if found and name != "map":
            leaky_notes += 1
        for w in found:
            hits[w] += 1
            first.setdefault(w, name)
    sources = {r.src.strip().casefold() for r in rows if len(r.src.strip()) >= quote_min}
    juror_text = "\n".join(t for _, t in texts).casefold()
    quoted = sorted(s for s in sources if s in juror_text)
    return {"view": "jury" if pack.jury_text or pack.jury_notes else "user map", "words": [[w, n, first[w]] for w, n in hits.most_common()],
            "notes_with_leaks": leaky_notes, "notes": len(texts) - 1, "quoted_source_lines": quoted}


def locale_tables(shared: Path) -> Dict[str, Path]:
    """Locale code -> StringTable asset of the collection whose Shared Data asset is shared (they sit in one folder)."""
    meta = shared.with_name(shared.name + ".meta")
    m = re.search(r"guid: (\w+)", read_text(meta)) if meta.is_file() else None
    shared_guid = m.group(1) if m else ""
    out: Dict[str, Path] = {}
    for f in sorted(shared.parent.glob("*.asset")):
        if f == shared:
            continue
        head = read_text(f)[:4000]
        code = re.search(r"m_LocaleId:\n\s+m_Code: (\S+)", head)
        sd = re.search(r"m_SharedData: \{fileID: -?\d+, guid: (\w+)", head)
        if not code or (shared_guid and sd and sd.group(1) != shared_guid):
            continue
        out[code.group(1)] = f
    return out


def table_texts(asset: Path) -> Dict[str, str]:
    """Key id -> text of a Unity StringTable asset, line and paragraph breaks intact."""
    data = parse_unity_yaml(read_text(asset).lstrip("﻿"))
    return {e["id"]: e["text"] or "" for e in data["entries"] if e["id"] is not None and e["text"] is not None}


def load_slice_spec(path: Path) -> Dict[str, List[str]]:
    """{slice name: [table name or glob, ...]} from a JSON file."""
    if not path.is_file():
        raise L10nError(f"--slices file not found: {path}")
    try:
        spec = json.loads(read_text(path).lstrip("﻿"))
    except json.JSONDecodeError as exc:
        raise L10nError(f"{path}: invalid JSON at line {exc.lineno}: {exc.msg}")
    if not isinstance(spec, dict) or not spec:
        raise L10nError(f"{path}: expected an object {{\"slice name\": [\"TableName\", \"Table*\"]}}")
    for name, globs in spec.items():
        if not _SLICE_NAME.fullmatch(name) or name == UNASSIGNED:
            raise L10nError(f"{path}: slice name '{name}' must be letters, digits, '_', '-' or '.', and not '{UNASSIGNED}'")
        if not isinstance(globs, list) or not globs or not all(isinstance(g, str) and g for g in globs):
            raise L10nError(f"{path}: slice '{name}' needs a non-empty list of table names or globs")
    return spec


def build_slices(scan: Dict[str, Any], tables: Dict[str, Dict[str, Any]], spec: Dict[str, List[str]], source_locale: str,
                 target_locale: Optional[str] = None, ref_meta: Optional[Dict[str, Dict[str, Any]]] = None
                 ) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """Scout inputs, one list of rows per slice, read from the project's own string tables.

    Every table lands in exactly one slice (a table claimed twice is an input error), tables no slice
    claims go to the slice 'unassigned', so no key is ever lost on the way to the scouts.
    """
    assign: Dict[str, str] = {}
    for name, globs in spec.items():
        hit = [t for t in scan["tables"] if any(fnmatch.fnmatchcase(t, g) for g in globs)]
        if not hit:
            raise L10nError(f"slice '{name}': no table matches {globs}. Tables are {', '.join(scan['tables'])}")
        for t in hit:
            if t in assign:
                raise L10nError(f"table {t} is claimed by slice '{assign[t]}' and by slice '{name}', every key must land in exactly one slice")
            assign[t] = name
    locales = [source_locale] + ([target_locale] if target_locale and target_locale != source_locale else [])
    texts: Dict[Tuple[str, str], Dict[str, str]] = {}
    missing_locales: List[str] = []
    for t in scan["tables"]:
        found = locale_tables(tables[t]["shared"])
        for loc in locales:
            if loc not in found:
                missing_locales.append(f"{t} {loc}")
                texts[(t, loc)] = {}
                continue
            ids = tables[t]["ids"]
            texts[(t, loc)] = {ids[kid]: txt for kid, txt in table_texts(found[loc]).items() if kid in ids}
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    ref_meta = ref_meta or {}
    for key, info in sorted(scan["keys"].items(), key=lambda kv: (kv[1]["table"], kv[0])):
        t = info["table"]
        row: Dict[str, Any] = {"key": key, "table": t}
        for loc in locales:
            row[loc] = texts[(t, loc)].get(key, "")
        meta = ref_meta.get(key) or ref_meta.get(info.get("name", ""), {})
        row["category"] = str(meta.get("category") or "")
        row["speaker"] = str(meta.get("speaker") or "")
        row["usages"] = info["usages"]
        row["code"] = info["code"]
        out[assign.get(t, UNASSIGNED)].append(row)
    stats = {"slices": {n: len(rows) for n, rows in sorted(out.items())},
             "unassigned_tables": sorted(t for t in scan["tables"] if t not in assign),
             "missing_locale_tables": missing_locales}
    return dict(out), stats


def check_slices(folder: Path) -> Dict[str, Dict[str, Any]]:
    """Coverage of the scout reports. Every key of <slice>.input.json must sit in exactly one entry of <slice>.report.json."""
    inputs = sorted(folder.glob("*.input.json"))
    if not inputs:
        raise L10nError(f"{folder}: no <slice>.input.json files, run --slices first")
    res: Dict[str, Dict[str, Any]] = {}
    for inp in inputs:
        name = inp.name[: -len(".input.json")]
        try:
            want = {str(r["key"]) for r in json.loads(read_text(inp))}
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise L10nError(f"{inp}: not a slice input ({exc})")
        rep_path = folder / f"{name}.report.json"
        if not rep_path.is_file():
            res[name] = {"keys": len(want), "report": False, "missing": sorted(want), "duplicated": [], "unknown": [], "questions": 0}
            continue
        try:
            rep = json.loads(read_text(rep_path))
        except json.JSONDecodeError as exc:
            raise L10nError(f"{rep_path}: invalid JSON at line {exc.lineno}: {exc.msg}")
        if not isinstance(rep, list):
            raise L10nError(f"{rep_path}: expected a list of report entries")
        seen: Counter = Counter()
        questions = 0
        for e in rep:
            if not isinstance(e, dict):
                continue
            ks = e.get("keys") if isinstance(e.get("keys"), list) else ([e["key"]] if e.get("key") else [])
            seen.update(str(k) for k in ks)
            questions += len(e.get("questions") or [])
        res[name] = {"keys": len(want), "report": True, "missing": sorted(want - set(seen)),
                     "duplicated": sorted(k for k, c in seen.items() if c > 1), "unknown": sorted(set(seen) - want),
                     "questions": questions}
    return res


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Context map facts. Where every localization key of a game project is used (Unity for now)")
    ap.add_argument("--scan", action="store_true", help="Scan the project and write key_usage.json and scan_summary.md")
    ap.add_argument("--slices", default=None, metavar="SPEC", help="Also write one scout input per slice to <out>/slices, SPEC is JSON {\"slice\": [\"TableName\", \"Table*\"]}")
    ap.add_argument("--source-locale", default="en", help="Locale of the source texts in the slice inputs (default en)")
    ap.add_argument("--locale", default=None, help="Target locale whose existing texts go into the slice inputs, for example tr-TR")
    ap.add_argument("--check-slices", action="store_true", help="Check that every key of <out>/slices/<slice>.input.json sits in exactly one entry of <slice>.report.json")
    ap.add_argument("--check-leak", action="store_true", help="Check the jurors' view of --context-map against an existing translation (--reference) for its words and quoted source lines")
    ap.add_argument("--context-map", default=None, help="CONTEXT_MAP.md for --check-leak (the jury files next to it are checked when present)")
    ap.add_argument("--reference", default=None, help="Existing translation with key, en and the --locale column, for --check-leak")
    ap.add_argument("--project", default=None, help="Game project folder (a Unity project or its Assets folder)")
    ap.add_argument("--out", default=None, help="Output folder, for example loc_work/context (never inside the game project)")
    ap.add_argument("--keys-from", default=None, help="String table whose keys must be covered (for example the studio reference), reports keys without a usage")
    ap.add_argument("--code-lines", type=int, default=CODE_LINES_PER_FIELD, help=f"Code lines kept per localized field (default {CODE_LINES_PER_FIELD})")
    add_common_args(ap, TOOL)
    return ap


def _check_main(args: argparse.Namespace, out: Path) -> int:
    res = check_slices(out / "slices")
    bad = {n: r for n, r in res.items() if not r["report"] or r["missing"] or r["duplicated"] or r["unknown"]}
    exit_code = EXIT_FINDINGS if bad else EXIT_OK
    lines = [f"Scout report coverage in {out / 'slices'}: {len(res)} slices, {sum(r['keys'] for r in res.values())} keys, "
             f"{sum(r['questions'] for r in res.values())} questions"]
    for n, r in res.items():
        if not r["report"]:
            lines.append(f"  {n}: no report yet ({r['keys']} keys)")
        elif n in bad:
            lines.append(f"  {n}: {len(r['missing'])} keys missing, {len(r['duplicated'])} in two entries, {len(r['unknown'])} not in the input"
                         + (f" (first {', '.join((r['missing'] + r['duplicated'] + r['unknown'])[:5])})"))
        else:
            lines.append(f"  {n}: {r['keys']} keys, each in exactly one entry")
    lines.append(f"  Exit code: {exit_code}")
    emit_report("\n".join(lines), {"tool": TOOL, "version": __version__, "slices": res, "exit_code": exit_code}, args.json, args.output)
    return exit_code


def _leak_main(args: argparse.Namespace) -> int:
    ref = Path(args.reference)
    if not ref.is_file():
        raise L10nError(f"--reference file not found: {ref}")
    rows = None
    for col in (args.locale, "dst", "target"):
        try:
            rows = load_table(ref, "en", col, "key")
            break
        except L10nError:
            continue
    if rows is None:
        raise L10nError(f"{ref}: no '{args.locale}' column")
    res = check_leak(load_context(Path(args.context_map), args.locale), rows)
    exit_code = EXIT_FINDINGS if res["words"] or res["quoted_source_lines"] else EXIT_OK
    lines = [f"Leak check of the jurors' view ({res['view']}) against {ref.name}: {res['notes']} line notes, "
             f"{res['notes_with_leaks']} with words of the existing translation, {len(res['words'])} distinct words, "
             f"{len(res['quoted_source_lines'])} quoted source lines"]
    for w, n, first in res["words"][:15]:
        lines.append(f"  {w} {n}x, first in {first}")
    lines.append(f"  Exit code: {exit_code}")
    emit_report("\n".join(lines), {"tool": TOOL, "version": __version__, **res, "exit_code": exit_code}, args.json, args.output)
    return exit_code


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    modes = sum(1 for m in (args.scan or bool(args.slices), args.check_slices, args.check_leak) if m)
    if modes != 1:
        ap.error("choose one mode, --scan (optionally with --slices), --check-slices or --check-leak")
    if args.check_leak:
        if not (args.context_map and args.reference and args.locale):
            ap.error("--check-leak needs --context-map, --reference and --locale")
        return _leak_main(args)
    if not args.out:
        ap.error("--out is required")
    out = Path(args.out)
    if args.check_slices:
        return _check_main(args, out)
    if not args.project:
        ap.error("--scan and --slices need --project")
    project = Path(args.project)
    if out.resolve().is_relative_to(project.resolve()):
        raise L10nError("--out must not be inside the game project, the scan never writes into it")
    if args.code_lines < 0:
        raise L10nError("--code-lines must be 0 or more")
    spec = load_slice_spec(Path(args.slices)) if args.slices else None
    tables: Dict[str, Dict[str, Any]] = {}
    scan = scan_unity(project, args.code_lines, tables)
    wanted = None
    ref_meta: Dict[str, Dict[str, Any]] = {}
    if args.keys_from:
        ref = Path(args.keys_from)
        if not ref.is_file():
            raise L10nError(f"--keys-from file not found: {ref}")
        ref_rows = load_table(ref, "en", "en", "key", target_only=True)
        wanted = [r.key for r in ref_rows]
        ref_meta = {r.key: r.meta for r in ref_rows}
    s = summary(scan, wanted)
    out.mkdir(parents=True, exist_ok=True)
    (out / "key_usage.json").write_text(json.dumps(scan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "scan_summary.md").write_text(render_summary(scan, s), encoding="utf-8")
    findings = bool(s.get("wanted_missing"))
    lines = [f"Context scan {scan['project']} ({scan['engine']}): {s['keys']} keys in {len(scan['tables'])} tables, {s['used']} with a usage",
             f"  code lines that glue texts together: {s['concat_lines']}",
             f"  references to a missing key: {s['dangling_references']}, to a missing table: {sum(s['missing_table_references'].values())}"]
    if wanted is not None:
        lines.append(f"  keys of {Path(args.keys_from).name}: {s['wanted']}, without a usage: {len(s['wanted_missing'])}")
    lines.append(f"  wrote {out / 'key_usage.json'} and {out / 'scan_summary.md'}")
    payload: Dict[str, Any] = {"tool": TOOL, "version": __version__, "project": scan["project"], "summary": s}
    if spec is not None:
        slices, stats = build_slices(scan, tables, spec, args.source_locale, args.locale, ref_meta)
        sdir = out / "slices"
        sdir.mkdir(parents=True, exist_ok=True)
        for name, rows in slices.items():
            (sdir / f"{name}.input.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        findings = findings or bool(stats["unassigned_tables"] or stats["missing_locale_tables"])
        lines.append(f"  slices: {', '.join(f'{n} {c}' for n, c in stats['slices'].items())}, written to {sdir}")
        if stats["unassigned_tables"]:
            lines.append(f"  tables no slice claims, written to {UNASSIGNED}.input.json: {', '.join(stats['unassigned_tables'])}")
        if stats["missing_locale_tables"]:
            lines.append(f"  string tables not found for: {', '.join(stats['missing_locale_tables'][:10])}")
        payload["slices"] = stats
    exit_code = EXIT_FINDINGS if findings else EXIT_OK
    lines.append(f"  Exit code: {exit_code}")
    payload["exit_code"] = exit_code
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
