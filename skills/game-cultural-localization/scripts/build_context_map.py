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

Output in --out
  key_usage.json   {"engine", "tables", "keys": {key: {"table", "usages": [...], "code": [...]}}}
  scan_summary.md  coverage, tables, classes per table, keys without a usage

Exit codes: 0 scan written, 1 scan written but keys of --keys-from have no usage, 2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, emit_report, load_table, run_main, __version__,
)

TOOL = "build_context_map"
CODE_LINES_PER_FIELD = 4
ASSET_EXTS = (".prefab", ".unity", ".asset")
_DOC = re.compile(r"^--- !u!(\d+) &(-?\d+)", re.M)
_REF = re.compile(r"^( *)(?:- )?m_TableReference:\n *m_TableCollectionName: ?(.*)\n *m_TableEntryReference:\n *m_KeyId: (-?\d+)\n *m_Key: ?(.*)$", re.M)
_PARENT = re.compile(r"^( *)(?:- )?([A-Za-z_]\w*):\s*$")
_ENTRY = re.compile(r"- m_Id: (-?\d+)\n\s+m_Key: (.*)")
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


def load_tables(files: Sequence[Tuple[Path, str]]) -> Tuple[Dict[str, str], Dict[str, str], Dict[Tuple[str, str], str], Dict[str, set]]:
    """Shared Data assets -> (guid -> table name, table name -> guid, (guid, key id) -> key, guid -> key names)."""
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
        keys.setdefault(guid, set())
        for kid, key in _ENTRY.findall(txt):
            by_id[(guid, kid)] = key.strip()
            keys[guid].add(key.strip())
    return names, by_name, by_id, keys


def script_classes(root: Path) -> Dict[str, Path]:
    """MonoBehaviour script guid -> .cs file."""
    out: Dict[str, Path] = {}
    for meta in root.rglob("*.cs.meta"):
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


def scan_unity(project: Path, code_lines: int = CODE_LINES_PER_FIELD) -> Dict[str, Any]:
    """Every key usage of a Unity project. Read only."""
    root = find_unity_root(project)
    files: List[Tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        if path.suffix in ASSET_EXTS and path.is_file():
            txt = read_text(path)
            if "m_TableReference" in txt or "m_TableCollectionNameGuidString" in txt:
                files.append((path, txt))
    names, by_name, by_id, table_keys = load_tables(files)
    if not names:
        raise L10nError(f"{root}: no Unity Localization string table (Shared Data asset) found")
    scripts = script_classes(root)
    keys: Dict[str, Dict[str, Any]] = {}
    for guid, ks in table_keys.items():
        for k in ks:
            keys[k] = {"table": names[guid], "usages": [], "code": []}
    unresolved = 0
    seen_fields: Dict[Tuple[str, str], Path] = {}
    for path, txt in files:
        if "m_TableReference" not in txt:
            continue
        docs = _docs(txt)
        paths = object_paths(docs)
        for _fid, (_cls, d) in docs.items():
            if "m_TableReference" not in d:
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
                key = by_id.get((guid, kid)) if kid not in ("0", "") else (kname if kname in keys else "")
                if not key:
                    if table_ref:
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
            "keys": {k: keys[k] for k in sorted(keys)}, "unresolved_references": unresolved}


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
           "concat_lines": len({(c["file"], c["line"]) for i in keys.values() for c in i["code"] if c["concat"]})}
    if wanted is not None:
        missing = [k for k in wanted if not keys.get(k, {}).get("usages")]
        out["wanted"] = len(wanted)
        out["wanted_missing"] = missing
    return out


def render_summary(scan: Dict[str, Any], s: Dict[str, Any]) -> str:
    """scan_summary.md in the house style (no semicolons, dashes or colons inside sentences)."""
    lines = [f"# Context scan of {scan['project']}", "",
             f"Engine {scan['engine']}. {s['keys']} keys in {len(scan['tables'])} string tables, {s['used']} of them have at least one usage in a prefab, scene or data asset.",
             f"{s['concat_lines']} code lines glue a localized text to something else (a name, a number or another text). They belong in the transcreation ledger as concatenation seams.", ""]
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


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Context map facts. Where every localization key of a game project is used (Unity for now)")
    ap.add_argument("--scan", action="store_true", help="Scan the project and write key_usage.json and scan_summary.md")
    ap.add_argument("--project", default=None, help="Game project folder (a Unity project or its Assets folder)")
    ap.add_argument("--out", default=None, help="Output folder, for example loc_work/context (never inside the game project)")
    ap.add_argument("--keys-from", default=None, help="String table whose keys must be covered (for example the studio reference), reports keys without a usage")
    ap.add_argument("--code-lines", type=int, default=CODE_LINES_PER_FIELD, help=f"Code lines kept per localized field (default {CODE_LINES_PER_FIELD})")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    if not args.scan:
        ap.error("choose a mode, for now --scan")
    if not args.project or not args.out:
        ap.error("--scan needs --project and --out")
    project = Path(args.project)
    out = Path(args.out)
    if out.resolve().is_relative_to(project.resolve()):
        raise L10nError("--out must not be inside the game project, the scan never writes into it")
    if args.code_lines < 0:
        raise L10nError("--code-lines must be 0 or more")
    scan = scan_unity(project, args.code_lines)
    wanted = None
    if args.keys_from:
        ref = Path(args.keys_from)
        if not ref.is_file():
            raise L10nError(f"--keys-from file not found: {ref}")
        wanted = [r.key for r in load_table(ref, "en", "en", "key", target_only=True)]
    s = summary(scan, wanted)
    out.mkdir(parents=True, exist_ok=True)
    (out / "key_usage.json").write_text(json.dumps(scan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "scan_summary.md").write_text(render_summary(scan, s), encoding="utf-8")
    exit_code = EXIT_FINDINGS if s.get("wanted_missing") else EXIT_OK
    lines = [f"Context scan {scan['project']} ({scan['engine']}): {s['keys']} keys in {len(scan['tables'])} tables, {s['used']} with a usage",
             f"  code lines that glue texts together: {s['concat_lines']}"]
    if wanted is not None:
        lines.append(f"  keys of {Path(args.keys_from).name}: {s['wanted']}, without a usage: {len(s['wanted_missing'])}")
    lines += [f"  wrote {out / 'key_usage.json'} and {out / 'scan_summary.md'}", f"  Exit code: {exit_code}"]
    payload = {"tool": TOOL, "version": __version__, "project": scan["project"], "summary": s, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
