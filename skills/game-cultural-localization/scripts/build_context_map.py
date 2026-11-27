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
  key_usage.json            {"engine", "tables", "use_trace", "keys": {key: {"table", "usages": [...], "code": [...],
                            "loads": [...], "uses": [...], "uses_total", "loaded_not_shown"}}}
  scan_summary.md           coverage, tables, classes per table, keys without a usage, keys loaded but never shown
  slices/<slice>.input.json with --slices, the input of one context-scout. Rows carry the key, the table,
                            the source text and the --locale text read from the project's own string tables
                            (paragraph breaks intact), category and speaker from --keys-from, usages, code and the
                            use trace (loads, uses, uses_total, loaded_not_shown).
                            Every table lands in exactly one slice, unclaimed tables go to unassigned.input.json.

--check-slices reads slices/<slice>.input.json and the scout's slices/<slice>.report.json and reports keys
that are missing, sit in two report entries or are not in the input.

Use trace (heuristic, regex over the project's C# code, no compiler). Every code line that loads a key into a variable
(`x = fooLoc.GetLocalizedString();`, a StringChanged handler that stores its value) is followed to the places that read
the variable, across the whole code base for static and public members. Each key gets `loads`, `uses` (file, line,
method, the enclosing conditions as `trigger`, `shape` of the text the code glues on, `{THIS}` marking the key's own
text) and `loaded_not_shown` when the loaded variable is never read anywhere. --use-sites 0 turns the trace off.

Exit codes: 0 written or covered, 1 findings (keys of --keys-from without a usage, unclaimed tables, missing
locale tables, gaps in the scout reports), 2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import bisect
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
USE_SITES_PER_KEY = 12
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


def scan_unity(project: Path, code_lines: int = CODE_LINES_PER_FIELD, tables_out: Optional[Dict[str, Dict[str, Any]]] = None,
               use_sites: int = USE_SITES_PER_KEY) -> Dict[str, Any]:
    """Every key usage of a Unity project. Read only.

    tables_out, when given, receives table name -> {"shared": Shared Data file, "ids": key id -> key}.
    use_sites above 0 also traces every loaded text to the code that reads it (see trace_uses) and keeps that many
    use sites per key.
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
    out = {"engine": "unity", "project": root.parent.name, "tables": sorted(names.values())}
    if use_sites > 0:
        out["use_trace"] = trace_uses(root, keys, seen_fields, use_sites)
    out.update({"keys": {k: keys[k] for k in sorted(keys)}, "unresolved_references": unresolved,
                "missing_table_references": dict(sorted(missing_tables.items()))})
    return out


# --------------------------------------------------------------------------- #
# Use trace. Where the code reads the text a key was loaded into (heuristic, regex only)
# --------------------------------------------------------------------------- #
TRACE_NOTE = ("Heuristic. Loads, use sites, triggers and loaded_not_shown come from a regex search of the C# code, not from a "
              "compiler. Reflection, UnityEvents, aliases and texts passed on as LocalizedString objects stay invisible, so read "
              "the code before you call a text unused.")
THIS = "{THIS}"
_HOLE = "\x01"       # the braces of an interpolation hole in the masked text, neither code nor space
_IDENT = re.compile(r"[A-Za-z_]\w*")
_CODE_TOKEN = re.compile(r'//|/\*|\$@"|@\$"|\$"|@"|"|\'|[{}]')
_STR_STOP = {(False, False): re.compile(r'[\\"\n]'), (True, False): re.compile(r'[\\"\n{}]'),
             (False, True): re.compile(r'"'), (True, True): re.compile(r'["{}]')}
_KEYWORDS = frozenset(("return else new case throw await yield out ref in is as goto using if for foreach while switch catch lock "
                       "fixed do try finally nameof typeof sizeof default checked unchecked delegate operator params this base "
                       "null true false select where").split())
_MODS = r"(?:(?:public|private|protected|internal|static|virtual|override|abstract|sealed|async|extern|unsafe|new|partial|readonly)\s+)"
_TYPE = r"[A-Za-z_][\w.]*(?:\s*<[^(){};=]*>)?(?:\s*\[\s*\])*\??"
_METHOD_HDR = re.compile(r"(?P<mods>" + _MODS + r"*)(?P<type>" + _TYPE + r"\s+)?(?:[\w.]+\.)?(?P<name>[A-Za-z_]\w*)\s*(?:<[^()]*>)?\s*\(")
_PROP_HDR = re.compile(_MODS + r"*(?P<type>" + _TYPE + r")\s+(?P<name>[A-Za-z_]\w*)$")
_EXPR_BODY = re.compile(r"\s*(?:\[[^\]]*\]\s*)*" + _MODS + r"*(" + _TYPE + r")\s+([A-Za-z_]\w*)\s*(\([^()]*\))?\s*=>")
_ASSIGN = re.compile(r"\s*((?:var|string)\s+)?(?:this\s*\.\s*)?([A-Za-z_]\w*)\s*(\+?=)(?![=>])")
_TYPE_BEFORE = re.compile(r"(" + _TYPE + r")\s+$")
_PREFIX = re.compile(r"(if|while|foreach|for|using|lock|fixed)\s*\(")
_LABEL = re.compile(r"(?:case\b[^:;{}]*?|default\s*):(?!:)")
_DEBUG = re.compile(r"\b(?:Debug\s*\.\s*(?:Log|Assert)\w*|Console\s*\.\s*Write\w*|print)\s*\(")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"', "'": "'", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def _collapse(s: str) -> str:
    return " ".join(s.split())


def _clip(s: str, n: int = 120) -> str:
    s = _collapse(s)
    return s if len(s) <= n else s[: n - 3] + "..."


@dataclass
class _Str:
    """A C# string literal. parts are ["lit", start, end] and ["hole", start, end] spans of the file text."""
    start: int
    interp: bool
    verbatim: bool
    parts: List[List[Any]] = field(default_factory=list)
    end: int = -1


def _mask_cs(text: str) -> Tuple[str, str, List[_Str]]:
    """(text without comments, text without comments and literal text, string literals). Offsets stay the same.

    The holes of interpolated strings stay code in both copies, so `$"{X}: {y}"` still shows X and y. Their braces
    become _HOLE in the masked copy, so two holes never read as a declaration `X y` and never count as blocks.
    """
    n = len(text)
    nc, mk = list(text), list(text)
    strings: List[_Str] = []

    def blank(arr: List[str], a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if arr[k] != "\n":
                arr[k] = " "
    stack: List[Any] = [[None, 0]]          # code frames [string of the hole or None, brace depth], or _Str frames
    i = 0
    while i < n:
        top = stack[-1]
        if isinstance(top, _Str):
            rx = _STR_STOP[(top.interp, top.verbatim)]
            k = i
            while True:
                m = rx.search(text, k)
                if not m:
                    k = n
                    break
                k = m.start()
                c = text[k]
                if c == "\\":
                    k += 2
                    continue
                if (c == '"' and top.verbatim and text[k + 1:k + 2] == '"') or (c in "{}" and text[k + 1:k + 2] == c):
                    k += 2
                    continue
                if c == "}":
                    k += 1
                    continue
                break
            blank(mk, i, k)
            top.parts.append(["lit", i, min(k, n)])
            if k < n and text[k] == "{":
                top.parts.append(["hole", k + 1, -1])
                mk[k] = _HOLE
                stack.append([top, 0])
                i = k + 1
            else:
                top.end = min(k + 1, n)
                strings.append(top)
                stack.pop()
                i = top.end
            continue
        m = _CODE_TOKEN.search(text, i)
        if not m:
            break
        j, tok = m.start(), m.group()
        if tok == "//":
            e = text.find("\n", j)
            e = n if e < 0 else e
            blank(nc, j, e)
            blank(mk, j, e)
            i = e
        elif tok == "/*":
            e = text.find("*/", j + 2)
            e = n if e < 0 else e + 2
            blank(nc, j, e)
            blank(mk, j, e)
            i = e
        elif tok == "'":
            e = text.find("'", j + (3 if text[j + 1:j + 2] == "\\" else 2), j + 12)
            if e < 0:
                i = j + 1
            else:
                blank(mk, j + 1, e)
                i = e + 1
        elif tok == "{":
            top[1] += 1
            i = j + 1
        elif tok == "}":
            if top[0] is not None and top[1] == 0:
                top[0].parts[-1][2] = j
                mk[j] = _HOLE
                stack.pop()
                i = j + 1
            else:
                top[1] -= 1
                i = j + 1
        else:
            stack.append(_Str(j, "$" in tok, "@" in tok))
            i = j + len(tok)
    strings = [s for s in strings if all(p[2] >= 0 for p in s.parts)]
    return "".join(nc), "".join(mk), sorted(strings, key=lambda s: s.start)


def _blocks(masked: str) -> List[Tuple[int, int]]:
    out, stack = [], []
    for m in re.finditer(r"[{}]", masked):
        if m.group() == "{":
            stack.append(m.start())
        elif stack:
            out.append((stack.pop(), m.start()))
    out.sort()
    return out


def _unescape(s: str, verbatim: bool, interp: bool) -> str:
    if interp:
        s = s.replace("{{", "{").replace("}}", "}")
    if verbatim:
        return s.replace('""', '"')

    def esc(m: "re.Match[str]") -> str:
        body = m.group(1)
        if body[0] in "ux" and len(body) > 1:
            try:
                return chr(int(body[1:], 16))
            except ValueError:
                return m.group()
        return _ESCAPES.get(body, m.group())
    return re.sub(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{1,4}|.)", esc, s)


class _CsFile:
    """One C# file. The masked copies are made on first use."""

    def __init__(self, rel: str, text: str) -> None:
        self.rel, self.text = rel, text
        self.ready = False

    def prepare(self) -> "_CsFile":
        if not self.ready:
            self.nocomment, self.masked, self.strings = _mask_cs(self.text)
            self.starts = [0] + [m.end() for m in re.finditer(r"\n", self.text)]
            self.blocks = _blocks(self.masked)
            self.opens = [o for o, _c in self.blocks]
            self.open_of = {c: o for o, c in self.blocks}
            self.close_of = {o: c for o, c in self.blocks}
            self.str_start = {s.start: s for s in self.strings}
            self.str_starts = [s.start for s in self.strings]
            self.str_end = {s.end - 1: s for s in self.strings}
            self.ready = True
        return self

    def line(self, pos: int) -> int:
        return bisect.bisect_right(self.starts, pos)

    def line_text(self, pos: int) -> str:
        s = self.starts[self.line(pos) - 1]
        e = self.text.find("\n", s)
        return self.text[s: e if e >= 0 else len(self.text)].strip()[:240]


def _match_fwd(m: str, k: int, limit: int = 4000) -> Optional[int]:
    depth = 0
    for j in range(k, min(len(m), k + limit)):
        c = m[j]
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
            if depth == 0:
                return j
    return None


def _match_back(m: str, k: int, limit: int = 4000) -> Optional[int]:
    depth = 0
    for j in range(k, max(-1, k - limit), -1):
        c = m[j]
        if c in ")]":
            depth += 1
        elif c in "([":
            depth -= 1
            if depth == 0:
                return j
    return None


def _stmt_start(f: _CsFile, pos: int, floor: int = 0) -> int:
    m = f.masked
    return max(floor, max(m.rfind(";", floor, pos), m.rfind("{", floor, pos), m.rfind("}", floor, pos)) + 1)


def _header(f: _CsFile, o: int) -> Tuple[int, str]:
    """Start and text of the header of the block opened at o (the code between the previous statement and the brace)."""
    hs = _stmt_start(f, o)
    return hs, _collapse(re.sub(r"(?m)^[ \t]*#.*$", "", f.nocomment[hs:o]))


def _enclosing(f: _CsFile, pos: int) -> Any:
    """Blocks around pos, innermost first."""
    for i in range(bisect.bisect_left(f.opens, pos) - 1, -1, -1):
        o, c = f.blocks[i]
        if c > pos:
            yield o, c


def _word_char(c: str) -> bool:
    return c.isalnum() or c == "_"


def _operand(f: _CsFile, a: int, b: int) -> Tuple[int, int]:
    """Grow a name at [a, b) to its member chain (Class.NAME, this.NAME, NAME.Method(), NAME[i])."""
    m, n = f.masked, len(f.masked)
    while True:
        k = a - 1
        while k >= 0 and m[k].isspace():
            k -= 1
        if k < 0 or m[k] != ".":
            break
        j = k - 1
        if j >= 0 and m[j] == "?":
            j -= 1
        while j >= 0 and m[j].isspace():
            j -= 1
        if j >= 0 and m[j] in ")]":
            o = _match_back(m, j)
            if o is None:
                break
            j = o - 1
        e = j
        while j >= 0 and _word_char(m[j]):
            j -= 1
        if j == e:
            break
        a = j + 1
    while True:
        k = b
        while k < n and m[k].isspace():
            k += 1
        if k + 1 < n and m[k] == "?" and m[k + 1] == ".":
            k += 1
        if k < n and m[k] == ".":
            j = k + 1
            while j < n and m[j].isspace():
                j += 1
            e = j
            while e < n and _word_char(m[e]):
                e += 1
            if e == j:
                break
            b = e
            continue
        if k < n and m[k] in "([" and k == b:
            e = _match_fwd(m, k)
            if e is None:
                break
            b = e + 1
            continue
        break
    return a, b


def _bounds(f: _CsFile, a: int, b: int) -> Tuple[int, int]:
    """The expression around [a, b) at the same bracket depth, up to an argument comma, an assignment or a statement end."""
    m, n = f.masked, len(f.masked)
    depth, k = 0, a - 1
    while k >= 0:
        if k in f.str_end:
            k = f.str_end[k].start - 1
            continue
        c = m[k]
        if c in ")]":
            depth += 1
        elif c in "([":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and (c in ",;{}:&|=" or (c == "?" and m[k + 1:k + 2] != ".") or (c == ">" and k and m[k - 1] == "=")):
            break
        k -= 1
    lo = k + 1
    depth, k = 0, b
    while k < n:
        if k in f.str_start:
            k = f.str_start[k].end
            continue
        c = m[k]
        if c in "([":
            depth += 1
        elif c in ")]":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and (c in ",;{}:&|=" or (c == "?" and m[k + 1:k + 2] != ".") or (c in "!<>" and m[k + 1:k + 2] == "=")):
            break
        k += 1
    return lo, k


def _split_top(f: _CsFile, lo: int, hi: int, sep: str) -> List[Tuple[int, int]]:
    """Spans of [lo, hi) split at sep on bracket depth 0, trimmed. A '+' next to another '+' or before '=' does not split."""
    m = f.masked
    parts, depth, start, k = [], 0, lo, lo
    while k < hi:
        if k in f.str_start:
            k = f.str_start[k].end
            continue
        c = m[k]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == sep and depth == 0 and not (sep == "+" and (m[k - 1:k] == "+" or m[k + 1:k + 2] in ("+", "="))):
            parts.append((start, k))
            start = k + 1
        k += 1
    parts.append((start, hi))
    out = []
    for p, q in parts:
        while p < q and m[p].isspace():
            p += 1
        while q > p and m[q - 1].isspace():
            q -= 1
        if q > p:
            out.append((p, q))
    return out


def _render(f: _CsFile, s: _Str, this: Optional[Tuple[int, int]] = None) -> str:
    """The text of a literal, holes as {expression}, the hole holding [a, b) as {THIS}."""
    out = []
    for kind, p, q in s.parts:
        if kind == "lit":
            out.append(_unescape(f.text[p:q], s.verbatim, s.interp))
        elif this is not None and p <= this[0] and this[1] <= q:
            out.append(THIS)
        else:
            out.append("{" + _clip(f.nocomment[p:q], 40) + "}")
    return "".join(out)


def _expr(f: _CsFile, a: int, b: int) -> Tuple[int, int, str]:
    """(start, end, shape) of the expression that carries the operand [a, b). Shape is '' when nothing is glued on."""
    m = f.masked
    inner = THIS
    i = bisect.bisect_left(f.str_starts, a) - 1
    while i >= 0:                       # the innermost literal around the operand, an interpolated string when it holds it in a hole
        s = f.strings[i]
        if s.end >= b:
            if s.interp and any(k == "hole" and p <= a and b <= q for k, p, q in s.parts):
                inner = _render(f, s, (a, b))
                a, b = _operand(f, s.start, s.end)
            break
        i -= 1
    lo, hi = _bounds(f, a, b)
    km = re.match(r"\s*(?:return|await|throw|yield\s+return)\b", m[lo:hi])
    if km:
        lo += km.end()
    parts = _split_top(f, lo, hi, "+")
    if len(parts) > 1:
        out = []
        for p, q in parts:
            lit = f.str_start.get(p)
            if p <= a and b <= q:
                out.append(inner)
            elif lit is not None and lit.end == q:
                out.append(_render(f, lit))
            else:
                out.append("{" + _clip(f.nocomment[p:q], 40) + "}")
        shape = "".join(out)
    else:
        shape = inner
    j = lo - 1
    while j >= 0 and m[j].isspace():
        j -= 1
    if j >= 1 and m[j] == "=" and m[j - 1] == "+":
        target = _collapse(f.nocomment[_stmt_start(f, j - 1):j - 1])
        tm = re.search(r"[\w.\[\]]+$", target)
        shape = "{" + (tm.group() if tm else target)[-40:] + "}" + shape
    elif j >= 0 and m[j] in "(,":
        shape = _format_shape(f, j, a, b, inner) or shape
    return lo, hi, ("" if shape == THIS else shape)


def _format_shape(f: _CsFile, j: int, a: int, b: int, inner: str) -> str:
    """Shape of a string.Format call that takes the operand as its pattern or as one of its arguments."""
    m = f.masked
    op = j
    if m[j] == ",":
        depth, k = 0, j - 1
        while k >= 0:
            c = m[k]
            if c in ")]":
                depth += 1
            elif c in "([":
                if depth == 0:
                    break
                depth -= 1
            elif c in ";{}" and depth == 0:
                return ""
            k -= 1
        if k < 0 or m[k] != "(":
            return ""
        op = k
    nm = re.search(r"([\w.]+)\s*$", m[max(0, op - 80):op])
    close = _match_fwd(m, op)
    if not nm or not nm.group(1).endswith("Format") or close is None:
        return ""
    args = _split_top(f, op + 1, close, ",")
    idx = next((i for i, (p, q) in enumerate(args) if p <= a and b <= q), None)
    if idx is None:
        return ""
    texts = [_clip(f.nocomment[p:q], 40) for p, q in args]
    if idx == 0:
        return nm.group(1) + "(" + inner + "".join(", {" + t + "}" for t in texts[1:]) + ")"
    lit = f.str_start.get(args[0][0])
    if lit is None or lit.end != args[0][1]:
        return ""

    def sub(mm: "re.Match[str]") -> str:
        i = int(mm.group(1)) + 1
        return inner if i == idx else ("{" + texts[i] + "}" if i < len(texts) else mm.group())
    return re.sub(r"\{(\d+)(?:[:,][^}]*)?\}", sub, _render(f, lit))


def _prefixes(f: _CsFile, s: int, pos: int) -> Tuple[List[str], int]:
    """Braceless if, else, loop and case prefixes of the statement starting at s (outermost first), and where they end."""
    m = f.masked
    conds: List[str] = []
    k = s
    while True:
        while k < pos and m[k].isspace():
            k += 1
        if m.startswith("else", k) and not _word_char(m[k + 4:k + 5] or " "):
            conds.append("else" + _else_of(f, s))
            k += 4
            continue
        pm = _PREFIX.match(m, k, pos)
        if pm:
            close = _match_fwd(m, pm.end() - 1)
            if close is None or close >= pos:
                break
            if pm.group(1) in ("if", "while"):
                conds.append(_clip(pm.group(1) + " (" + f.nocomment[pm.end():close] + ")"))
            k = close + 1
            continue
        lm = _LABEL.match(m, k, pos)
        if lm:
            k = lm.end()
            continue
        break
    return conds, k


def _else_of(f: _CsFile, s: int) -> str:
    """' of if (...)' for an else that starts at s, when the if before it is found."""
    m = f.masked
    k = s - 1
    while k >= 0 and m[k].isspace():
        k -= 1
    if k >= 0 and m[k] == "}" and k in f.open_of:
        o = f.open_of[k]
        hm = re.search(r"(?:else\s+)?(?:if|while)\s*\(.*$", _header(f, o)[1])
        return " of " + _clip(hm.group()) if hm else ""
    if k >= 0 and m[k] == ";":
        conds, _ = _prefixes(f, _stmt_start(f, k), k)
        if conds and conds[-1].startswith("if"):
            return " of " + conds[-1]
    return ""


def _ternary(f: _CsFile, lo: int) -> str:
    """'when (cond)' or 'when not (cond)' when the expression starting at lo is a branch of a conditional operator."""
    m = f.masked

    def back(k: int, stop: str) -> int:
        """Index of the first unbracketed stop character left of k, -1 when an open bracket comes first."""
        depth = 0
        while k >= 0:
            if k in f.str_end:
                k = f.str_end[k].start - 1
                continue
            c = m[k]
            if c in ")]":
                depth += 1
            elif c in "([":
                if depth == 0:
                    return -1 if stop != "cond" else k
                depth -= 1
            elif depth == 0:
                if stop == "?" and c in ",;{}":
                    return -1
                if stop == "?" and c == "?" and m[k + 1:k + 2] not in (".", "?") and m[k - 1:k] != "?":
                    return k
                if stop == "cond" and (c in ",;{}?:" or (c == "=" and m[k + 1:k + 2] != "=" and m[k - 1:k] not in ("=", "!", "<", ">"))):
                    return k
            k -= 1
        return -1 if stop != "cond" else k
    j = lo - 1
    while j >= 0 and m[j].isspace():
        j -= 1
    if j < 1 or m[j] not in "?:" or (m[j] == "?" and (m[j + 1:j + 2] in (".", "?") or m[j - 1] == "?")):
        return ""
    neg = m[j] == ":"
    if neg:
        j = back(j - 1, "?")
        if j < 0:
            return ""
    k = back(j - 1, "cond")
    cond = re.sub(r"^(?:return|await)\s+", "", _collapse(f.nocomment[k + 1:j]))
    return _clip(("when not (" if neg else "when (") + cond + ")") if cond else ""


def _classify_header(hdr: str) -> Tuple[str, str]:
    h = re.sub(r"^(?:\[[^\]]*\]\s*)+", "", hdr).strip()
    h = re.sub(r"^(?:(?:case\b[^:]*?|default\s*):(?!:)\s*)+", "", h).strip()
    if not h:
        return "", ""
    if re.match(r"(?:else\s+)?(?:if|while)\s*\(", h):
        return "if", h
    if h == "else":
        return "else", h
    if re.match(r"switch\s*\(", h):
        return "switch", h
    if re.match(r"catch\b", h):
        return "catch", h
    eb = _EXPR_BODY.match(h)
    if eb and eb.group(1).split("<")[0] not in _KEYWORDS:
        return "method", eb.group(2)
    if h.endswith("=>") or re.match(r"(?:for|foreach|do|try|finally|using|lock|fixed|unsafe|checked|unchecked|delegate)\b", h):
        return "other", h
    tm = re.search(r"\b(?:class|struct|interface|enum|record|namespace)\s+([\w.]+)", h)
    if tm and "(" not in h[:tm.start()]:
        return "type", tm.group(1)
    if h in ("get", "set", "init", "add", "remove"):
        return "accessor", h
    tt = re.match(r"(" + _MODS + r"*)\([^()]*\)\??\s+(?=[A-Za-z_])", h)      # a tuple return type
    mm = _METHOD_HDR.match(tt.group(1) + "T " + h[tt.end():] if tt else h)
    if mm and (mm.group("type") or mm.group("mods").strip() not in ("", "new")) and mm.group("name") not in _KEYWORDS:
        tp = (mm.group("type") or "").split()
        hh = mm.string
        close = _match_fwd(hh, mm.end() - 1)
        tail = hh[close + 1:].strip() if close is not None else "?"
        if (not tp or tp[0] not in _KEYWORDS) and (not tail or tail.startswith((":", "where"))):
            return "method", mm.group("name")
    pm = _PROP_HDR.match(h)
    if pm and pm.group("type").split("<")[0] not in _KEYWORDS and pm.group("name") not in _KEYWORDS:
        return "property", pm.group("name")
    return "other", h


def _context(f: _CsFile, pos: int, s: int) -> Tuple[str, List[str]]:
    """(method, enclosing conditions innermost first) of a code position, s being the start of its statement."""
    conds, _ = _prefixes(f, s, pos)
    conds.reverse()
    method = ""
    for o, _c in _enclosing(f, pos):
        hs, hdr = _header(f, o)
        kind, text = _classify_header(hdr)
        if kind == "if":
            conds.append(_clip(text))
        elif kind == "else":
            conds.append("else" + _else_of(f, hs))
        elif kind == "switch":
            labels = list(_LABEL.finditer(f.masked, o + 1, pos))
            lab = _collapse(f.nocomment[labels[-1].start():labels[-1].end() - 1]) + " of " if labels else ""
            conds.append(_clip(lab + text))
        elif kind == "catch":
            conds.append(_clip(text))
        elif kind in ("method", "property"):
            method = text
            break
        elif kind == "type":
            break
    if not method:
        em = _EXPR_BODY.match(f.masked, s, pos)
        if em and em.group(1).split("<")[0] not in _KEYWORDS:
            method = em.group(2)
    return method, conds[:3]


def _helpers(f: _CsFile, conds: Sequence[str]) -> Dict[str, str]:
    """Bodies of the one line bool methods and properties a condition calls, from the same file."""
    out: Dict[str, str] = {}
    for cond in conds:
        for nm in re.finditer(r"\b([A-Za-z_]\w*)\b(\s*\(\s*\))?", cond):
            name = nm.group(1)
            label = name + ("()" if nm.group(2) else "")
            if name in _KEYWORDS or label in out or len(out) >= 3:
                continue
            rxs = ([r"\bbool\s+%s\s*\(\s*\)\s*=>\s*([^;{}]+);", r"\bbool\s+%s\s*\(\s*\)\s*\{\s*return\s+([^;{}]+);\s*\}"] if nm.group(2)
                   else [r"\bbool\s+%s\s*=>\s*([^;{}]+);", r"\bbool\s+%s\s*\{\s*get\s*(?:=>\s*([^;{}]+);|\{\s*return\s+([^;{}]+);\s*\})"])
            for rx in rxs:
                dm = re.search(rx % re.escape(name), f.nocomment)
                if dm:
                    out[label] = _clip(next(g for g in dm.groups() if g), 120)
                    break
    return out


def _flow(f: _CsFile, lo: int, hi: int, floor: int = 0) -> Tuple[str, str, bool]:
    """Where the value of the expression [lo, hi) goes.

    ('load', name, declares a local) for an assignment to a plain name, ('return', member, False) for a returned text,
    ('init', 'Type.Member', False) for a member of an object initializer and ('direct', '', False) for anything else.
    """
    s = _stmt_start(f, lo, floor)
    init = _initializer(f, s, lo)
    if init is not None:
        return "init", init, False
    _conds, k = _prefixes(f, s, lo)
    head = f.masked[k:lo]
    eb = _EXPR_BODY.match(head)
    if eb and eb.group(1).split("<")[0] not in _KEYWORDS:
        rest = head[eb.end():]
        am = _ASSIGN.match(rest)
        if am:
            return "load", am.group(2), bool(am.group(1))
        if eb.group(1) == "string":
            return "return", eb.group(2), False
        return "direct", "", False
    am = _ASSIGN.match(head)
    if am:
        return "load", am.group(2), bool(am.group(1))
    if re.match(r"\s*return\b", head):
        return "return", "", False
    return "direct", "", False


def _initializer(f: _CsFile, s: int, lo: int) -> Optional[str]:
    """'Type.Member' when [s, lo) sits right inside an object initializer (new HoverData { HoverName = ... }), else None."""
    if s == 0 or f.masked[s - 1] != "{":
        return None
    hdr = _header(f, s - 1)[1]
    nm = re.search(r"\bnew\b\s*([\w.]*)(?:\s*<[^()]*>)?\s*(?:\([^()]*\)|\[\s*\])?\s*$", hdr)
    if not nm and not hdr.endswith("="):
        return None
    parts = _split_top(f, s, lo, ",")
    am = _ASSIGN.match(f.masked, parts[-1][0], lo) if parts else None
    member = am.group(2) if am else ""
    typ = nm.group(1) if nm else ""
    return ".".join(x for x in (typ, member) if x) or "initializer"


def _is_debug(f: _CsFile, a: int) -> bool:
    """True for a line that only a developer sees, a Debug.Log call or a file of an Editor folder."""
    return "/Editor/" in "/" + f.rel or bool(_DEBUG.search(f.masked, _stmt_start(f, a), a))


def _is_read(f: _CsFile, a: int, b: int) -> bool:
    """False for a declaration, a write, out, nameof."""
    m = f.masked
    if re.match(r"\s*(?:=(?![=>])|\+=|-=|\?\?=)", m[b:b + 6]):
        return False
    before = m[max(0, a - 160):a]
    if re.search(r"(?:\bnameof\s*\(|\bout\s)\s*$", before):
        return False
    tm = _TYPE_BEFORE.search(before)
    if tm and not before[:tm.start()].rstrip().endswith("."):
        first = re.split(r"[\s.<\[?]", tm.group(1))[0]
        if first not in _KEYWORDS:
            return False
    return True


class _Tracer:
    """Follows every localized field the scan found to the code that reads its text."""

    def __init__(self, root: Path, limit: int) -> None:
        self.limit = limit
        self.files: List[_CsFile] = []
        self.by_rel: Dict[str, _CsFile] = {}
        for p in sorted(root.rglob("*.cs")):
            if p.is_file():
                cf = _CsFile(_rel(p, root), read_text(p))
                self.files.append(cf)
                self.by_rel[cf.rel] = cf
        self._index: Optional[Dict[str, set]] = None
        self._class_cache: Dict[str, List[_CsFile]] = {}
        self._field_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._var_cache: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        self._site_cache: Dict[Tuple[str, int, str], Dict[str, Any]] = {}

    # -- the code base ------------------------------------------------------
    def with_token(self, tok: str) -> set:
        """Indices of the files whose text holds the identifier."""
        if self._index is None:
            idx: Dict[str, set] = defaultdict(set)
            for i, cf in enumerate(self.files):
                for t in set(_IDENT.findall(cf.text)):
                    idx[t].add(i)
            self._index = idx
        return self._index.get(tok, set())

    def class_files(self, cls: str) -> List[_CsFile]:
        """Files that declare the class (partial parts included)."""
        if cls not in self._class_cache:
            rx = re.compile(r"\b(?:class|struct)\s+" + re.escape(cls) + r"\b")
            self._class_cache[cls] = [self.files[i] for i in sorted(self.with_token(cls)) if rx.search(self.files[i].text)]
        return self._class_cache[cls]

    def family(self, cls: str, first: Optional[_CsFile] = None) -> List[_CsFile]:
        """The class, its partial parts and its base classes (four levels), the script file first."""
        out: List[_CsFile] = [first] if first is not None else []
        name = cls
        for _ in range(5):
            files = self.class_files(name)
            out += [cf for cf in files if cf not in out]
            base = None
            for cf in files:
                bm = re.search(r"\b(?:class|struct)\s+" + re.escape(name) + r"\s*(?:<[^>{]*>)?\s*:\s*([\w.]+)", cf.text)
                if bm:
                    base = bm.group(1).split(".")[-1]
                    break
            if not base or base in ("MonoBehaviour", "ScriptableObject", "Object"):
                break
            name = base
        return out

    def derived(self, cls: str) -> List[_CsFile]:
        rx = re.compile(r"\bclass\s+\w+\s*(?:<[^>{]*>)?\s*:\s*(?:[\w.]+\.)?" + re.escape(cls) + r"\b")
        return [self.files[i] for i in sorted(self.with_token(cls)) if rx.search(self.files[i].text)]

    def member_decl(self, files: Sequence[_CsFile], name: str) -> Optional[Tuple[_CsFile, bool, bool, str]]:
        """(file, static, shared, declaring class) of a class level field or property, shared being anything not private."""
        rx = re.compile(r"(?m)^[ \t]*(?:\[[^\]\n]*\][ \t]*)*((?:(?:public|private|protected|internal|static|readonly|const|new|"
                        r"volatile|override|virtual|abstract)[ \t]+)*)(" + _TYPE + r")[ \t]+" + re.escape(name) + r"[ \t]*(?:=|;|\{|=>|,)")
        for cf in files:
            cf.prepare()
            for dm in rx.finditer(cf.nocomment):
                if dm.group(2).split("<")[0] in _KEYWORDS:
                    continue
                kind, cls = self._type_at(cf, dm.start(2))
                if kind != "type":
                    continue
                mods = dm.group(1).split()
                return cf, "static" in mods or "const" in mods, any(x in mods for x in ("public", "internal", "protected")), cls
        return None

    @staticmethod
    def _type_at(cf: _CsFile, pos: int) -> Tuple[str, str]:
        """Kind and name of the innermost block around pos ('type' when pos sits at class level)."""
        for o, _c in _enclosing(cf, pos):
            return _classify_header(_header(cf, o)[1])
        return "", ""

    def _method_block(self, cf: _CsFile, pos: int) -> Optional[Tuple[int, int]]:
        for o, c in _enclosing(cf, pos):
            if _classify_header(_header(cf, o)[1])[0] in ("method", "property", "accessor"):
                return o, c
        return None

    def class_at(self, cf: _CsFile, pos: int) -> str:
        """Name of the class around pos."""
        for o, _c in _enclosing(cf.prepare(), pos):
            kind, name = _classify_header(_header(cf, o)[1])
            if kind == "type":
                return name.split(".")[-1]
        return ""

    # -- fields ------------------------------------------------------------
    def field_trace(self, cls: str, fld: str, script: Optional[_CsFile]) -> Dict[str, Any]:
        """Loads, direct uses and opaque uses of one localized field."""
        ck = (cls, fld)
        if ck in self._field_cache:
            return self._field_cache[ck]
        res: Dict[str, Any] = {"loads": [], "direct": [], "opaque": False}
        self._field_cache[ck] = res
        own = self.family(cls, script)
        refs: List[Tuple[_CsFile, int, int]] = []
        rx = re.compile(r"\b" + re.escape(fld) + r"\b")
        for cf in own:
            cf.prepare()
            refs += [(cf, m.start(), m.end()) for m in rx.finditer(cf.masked)]
        decl = self.member_decl(own, fld)
        if decl is not None and decl[2]:
            near = self.with_token(fld) & self.with_token(cls)
            orx = re.compile(r"\.\s*(" + re.escape(fld) + r")\b")
            for i in sorted(near):
                cf = self.files[i]
                if cf in own:
                    continue
                cf.prepare()
                refs += [(cf, m.start(1), m.end(1)) for m in orx.finditer(cf.masked)]
        for cf, a0, b0 in refs:
            m = cf.masked
            if not _is_read(cf, a0, b0) and not re.match(r"\s*\.", m[b0:b0 + 4]):
                continue
            a, b = _operand(cf, a0, b0)
            tail = re.sub(r"\s+", "", m[b0:b])
            tail = re.sub(r"^\[.*?\]", "", tail)
            if re.match(r"\??\.GetLocalizedString\(", tail):
                lo, hi, shape = _expr(cf, a, b)
                self._record(res, cf, a0, b0, lo, shape, _flow(cf, lo, hi), "GetLocalizedString", fld)
            elif re.match(r"\??\.StringChanged$", tail):
                op = re.match(r"\s*([+-]=)", m[b:b + 6])
                if op and op.group(1) == "+=":
                    self._subscription(res, cf, b + op.end(), [cf] + [g for g in own if g is not cf])
            elif tail == "":
                if not re.match(r"\s*(?:[!=]=|=(?![=>]))", m[b:b + 6]) and not re.search(r"[!=]=\s*$", m[max(0, a - 6):a]):
                    res["opaque"] = True
            elif "GetLocalizedStringAsync" in tail:
                res["opaque"] = True
        return res

    def _record(self, res: Dict[str, Any], cf: _CsFile, a0: int, b0: int, lo: int, shape: str,
                flow: Tuple[str, str, bool], via: str, display: str) -> None:
        """File one text value, a load into a variable or member, or a direct use of the text in place."""
        kind, name, local = flow
        if kind == "init":
            kind = "direct"
        if kind == "load":
            res["loads"].append({"cf": cf, "pos": a0, "var": name, "local": local, "via": via, "shape": shape, "when": _ternary(cf, lo)})
        elif kind == "return":
            member = name or _context(cf, lo, _stmt_start(cf, lo))[0]
            if member:
                res["loads"].append({"cf": cf, "pos": a0, "var": member, "local": False, "via": "return", "shape": shape,
                                     "when": _ternary(cf, lo)})
            else:
                res["opaque"] = True
        else:
            res["direct"].append((cf, a0, b0, display))

    def _subscription(self, res: Dict[str, Any], cf: _CsFile, k: int, own: Sequence[_CsFile]) -> None:
        """StringChanged += handler. The handler's parameter carries the text."""
        m = cf.masked
        lm = re.match(r"\s*(?:\(\s*(?:string\s+)?([A-Za-z_]\w*)\s*\)|([A-Za-z_]\w*))\s*=>\s*", m[k:k + 200])
        if lm:
            body = k + lm.end()
            end = cf.close_of.get(body) if m[body:body + 1] == "{" else None
            if end is None:
                end = m.find(";", body)
                end = len(m) if end < 0 else end
                self._param_flows(res, cf, lm.group(1) or lm.group(2), body, end, body)
            else:
                self._param_flows(res, cf, lm.group(1) or lm.group(2), body, end, 0)
            return
        hm = re.match(r"\s*(?:this\s*\.\s*)?([A-Za-z_]\w*)\s*;", m[k:k + 200])
        if not hm:
            res["opaque"] = True
            return
        rx = re.compile(r"\bvoid\s+" + re.escape(hm.group(1)) + r"\s*\(\s*string\s+([A-Za-z_]\w*)\s*\)\s*(=>|\{)")
        for g in own:
            g.prepare()
            dm = rx.search(g.masked)
            if dm:
                if dm.group(2) == "=>":
                    end = g.masked.find(";", dm.end())
                    self._param_flows(res, g, dm.group(1), dm.end(), len(g.masked) if end < 0 else end, dm.end())
                else:
                    self._param_flows(res, g, dm.group(1), dm.end(), g.close_of.get(dm.end() - 1, len(g.masked)), 0)
                return
        res["opaque"] = True

    def _param_flows(self, res: Dict[str, Any], cf: _CsFile, param: str, start: int, end: int, floor: int) -> None:
        if param == "_":
            return
        for pm in re.finditer(r"\b" + re.escape(param) + r"\b", cf.masked[start:end]):
            a0, b0 = start + pm.start(), start + pm.end()
            if cf.masked[a0 - 1:a0] == "." or not _is_read(cf, a0, b0):
                continue
            a, b = _operand(cf, a0, b0)
            lo, hi, shape = _expr(cf, a, b)
            self._record(res, cf, a0, b0, lo, shape, _flow(cf, lo, hi, floor), "StringChanged", param)

    # -- variables ---------------------------------------------------------
    def var_trace(self, load: Dict[str, Any], cls: str, own: Sequence[_CsFile]) -> Dict[str, Any]:
        """Reads of the variable a text was loaded into. sites are listed, maybe counts reads that may be other members."""
        cf, name = load["cf"], load["var"]
        mb = self._method_block(cf, load["pos"])
        local = load["local"]
        if not local and mb is not None and load["via"] != "return":
            local = bool(re.search(r"(?:\bvar|\bstring)\s+" + re.escape(name) + r"\s*[=;]", cf.masked[mb[0]:load["pos"]]))
        if local and mb is not None:
            ck: Tuple[Any, ...] = ("local", cf.rel, mb[0], name)
            if ck not in self._var_cache:
                rx = re.compile(r"\b" + re.escape(name) + r"\b")
                sites = [(cf, m.start(), m.end(), name) for m in rx.finditer(cf.masked, load["pos"], mb[1])
                         if cf.masked[m.start() - 1:m.start()] != "." and _is_read(cf, m.start(), m.end())]
                self._var_cache[ck] = {"scope": "local", "sites": sites, "maybe": 0, "display": name}
            return self._var_cache[ck]
        decl = self.member_decl(own, name)
        if load["via"] == "return":
            dcls = decl[3] if decl else cls
            ck = ("member", dcls, name)
            if ck not in self._var_cache:
                self._var_cache[ck] = self._member_reads(own, dcls, name, decl[1] if decl else False, True, "member")
            return self._var_cache[ck]
        if decl is None:
            ck = ("unknown", cls, name)
            if ck not in self._var_cache:
                self._var_cache[ck] = self._member_reads(own, cls, name, False, True, "unknown")
            return self._var_cache[ck]
        dfile, static, shared, dcls = decl
        ck = ("member", dcls, name)
        if ck not in self._var_cache:
            files = list(own) + [g for g in self.class_files(dcls) if g not in own]
            self._var_cache[ck] = self._member_reads(files, dcls, name, static, shared, "static" if static else "field")
        return self._var_cache[ck]

    def _member_reads(self, own: Sequence[_CsFile], cls: str, name: str, static: bool, shared: bool, scope: str) -> Dict[str, Any]:
        files = list(own)
        if shared:
            files += [g for g in self.derived(cls) if g not in files]
        sites: List[Tuple[_CsFile, int, int, str]] = []
        maybe = 0
        display = f"{cls}.{name}" if static else name
        rx = re.compile(r"\b" + re.escape(name) + r"\b")
        for cf in files:
            cf.prepare()
            for m in rx.finditer(cf.masked):
                a0, b0 = m.start(), m.end()
                k = a0 - 1
                while k >= 0 and cf.masked[k].isspace():
                    k -= 1
                if k >= 0 and cf.masked[k] == ".":
                    owner = re.search(r"([A-Za-z_]\w*)\s*\??\s*$", cf.masked[max(0, k - 80):k])
                    if not _is_read(cf, a0, b0):
                        continue
                    if owner and owner.group(1) in ("this", "base", cls):
                        sites.append((cf, a0, b0, display))
                    else:
                        maybe += 1
                elif _is_read(cf, a0, b0):
                    sites.append((cf, a0, b0, display))
        if shared:
            near = self.with_token(name)
            cls_files = self.with_token(cls)
            orx = re.compile(r"(?:\b([A-Za-z_]\w*)\s*\??\s*\.\s*)?\b" + re.escape(name) + r"\b")
            for i in sorted(near):
                cf = self.files[i]
                if cf in files:
                    continue
                cf.prepare()
                for m in orx.finditer(cf.masked):
                    a0 = m.start() + (len(m.group()) - len(name))
                    b0 = m.end()
                    if not _is_read(cf, a0, b0):
                        continue
                    dotted = "." in m.group()
                    if static and m.group(1) == cls:
                        sites.append((cf, a0, b0, display))
                    elif not static and dotted and i in cls_files:
                        sites.append((cf, a0, b0, display))
                    elif dotted or static:
                        maybe += 1
        return {"scope": scope, "sites": sites, "maybe": maybe, "display": display}

    # -- sites -------------------------------------------------------------
    def site(self, cf: _CsFile, a0: int, b0: int, display: str) -> Dict[str, Any]:
        ck = (cf.rel, a0, display)
        if ck in self._site_cache:
            return self._site_cache[ck]
        a, b = _operand(cf, a0, b0)
        lo, hi, shape = _expr(cf, a, b)
        method, trigger = _context(cf, lo, _stmt_start(cf, lo))
        when = _ternary(cf, lo)
        trigger = ([when] if when else []) + trigger[:2] if when else trigger
        out: Dict[str, Any] = {"file": cf.rel, "line": cf.line(a0), "text": cf.line_text(a0), "variable": display,
                               "method": method, "trigger": trigger, "concat": bool(shape)}
        if shape:
            out["shape"] = shape
        if _is_debug(cf, a0):
            out["debug"] = True
        kind, target, _local = _flow(cf, lo, hi)
        if kind in ("load", "init") and target != display.split(".")[-1]:
            out["assigned_to"] = target
        helpers = _helpers(cf, trigger)
        if helpers:
            out["helpers"] = helpers
        self._site_cache[ck] = out
        return out

    # -- keys --------------------------------------------------------------
    def key_trace(self, usages: Sequence[Dict[str, Any]], scripts: Dict[Tuple[str, str], Path], root: Path) -> Dict[str, Any]:
        loads: List[Dict[str, Any]] = []
        raw: List[Tuple[_CsFile, int, int, str]] = []
        dead = bool(usages)
        for u in usages:
            script = scripts.get((u["class"], u["field"]))
            if not u["class"] or u["class"] == "LocalizeStringEvent" or script is None:
                dead = False
                continue
            first = self.by_rel.get(_rel(script, root))
            ft = self.field_trace(u["class"], u["field"], first)
            if ft["opaque"] or ft["direct"] or not ft["loads"]:
                dead = False
            raw += ft["direct"]
            own = self.family(u["class"], first)
            for ld in ft["loads"]:
                if ld["cf"] in own:
                    vt = self.var_trace(ld, u["class"], own)
                else:
                    lcls = self.class_at(ld["cf"], ld["pos"])
                    vt = self.var_trace(ld, lcls, self.family(lcls, ld["cf"]))
                rec = {"file": ld["cf"].rel, "line": ld["cf"].line(ld["pos"]), "variable": vt["display"], "via": ld["via"], "scope": vt["scope"]}
                if ld["shape"]:
                    rec["shape"] = ld["shape"]
                if ld["when"]:
                    rec["trigger"] = [ld["when"]]
                if rec not in loads:
                    loads.append(rec)
                raw += vt["sites"]
                if vt["sites"] or vt["maybe"] or vt["scope"] in ("unknown", "member"):
                    dead = False
        seen: Dict[Tuple[str, int, str], Tuple[_CsFile, int, int, str]] = {}
        for cf, a0, b0, disp in raw:
            seen.setdefault((cf.rel, cf.line(a0), disp), (cf, a0, b0, disp))
        order = sorted(seen, key=lambda k: (_is_debug(seen[k][0], seen[k][1]), k))    # player facing sites first
        uses = [self.site(*seen[k]) for k in order[: self.limit]]
        return {"loads": loads, "uses": uses, "uses_total": len(order), "loaded_not_shown": dead and bool(loads)}


def trace_uses(root: Path, keys: Dict[str, Dict[str, Any]], scripts: Dict[Tuple[str, str], Path], limit: int) -> Dict[str, Any]:
    """Add loads, uses, uses_total and loaded_not_shown to every key. Returns the use_trace header of key_usage.json."""
    tracer = _Tracer(root, limit)
    for info in keys.values():
        info.update(tracer.key_trace(info["usages"], scripts, root))
    return {"heuristic": True, "note": TRACE_NOTE, "code_files": len(tracer.files), "use_sites_per_key": limit,
            "keys_with_uses": sum(1 for i in keys.values() if i["uses"]),
            "loaded_not_shown": sum(1 for i in keys.values() if i["loaded_not_shown"])}


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
    if "use_trace" in scan:
        out["with_uses"] = sum(1 for i in keys.values() if i.get("uses"))
        out["loaded_not_shown"] = sorted(k for k, i in keys.items() if i.get("loaded_not_shown"))
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
    if "with_uses" in s:
        lines.append(f"The use trace found the code that reads the text of {s['with_uses']} keys, with the method, the conditions around "
                     f"the line and the text glued on. {len(s['loaded_not_shown'])} keys are loaded into a variable the code never reads, "
                     "so the game never shows them. The trace is a heuristic search of the C# code, read the code before you list such a key as a game bug.")
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
    if s.get("loaded_not_shown"):
        lines += ["", "Keys loaded but never shown (first 40). Each one is a game bug or a leftover, ask the user before anyone translates it.", ""]
        lines += [f"- `{k}`" for k in s["loaded_not_shown"][:40]]
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
        row["loads"] = info.get("loads", [])
        row["uses"] = info.get("uses", [])
        row["uses_total"] = info.get("uses_total", 0)
        row["loaded_not_shown"] = info.get("loaded_not_shown", False)
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
    ap.add_argument("--use-sites", type=int, default=USE_SITES_PER_KEY,
                    help=f"Use sites kept per key by the heuristic use trace (default {USE_SITES_PER_KEY}, 0 turns the trace off)")
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
    if args.use_sites < 0:
        raise L10nError("--use-sites must be 0 or more")
    spec = load_slice_spec(Path(args.slices)) if args.slices else None
    tables: Dict[str, Dict[str, Any]] = {}
    scan = scan_unity(project, args.code_lines, tables, args.use_sites)
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
    if "with_uses" in s:
        lines.append(f"  use trace (heuristic, regex over {scan['use_trace']['code_files']} C# files): {s['with_uses']} keys with use sites, "
                     f"{len(s['loaded_not_shown'])} loaded but never shown")
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
