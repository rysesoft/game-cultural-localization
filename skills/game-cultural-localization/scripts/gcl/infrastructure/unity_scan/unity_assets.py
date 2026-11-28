"""Unity project YAML asset scanner resolving SharedData tables, prefab/scene usages and code lines."""

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gcl.domain.errors import L10nError

from .cs_index import _rel
from .cs_lexer import read_text
from .cs_tracer import trace_uses

__layer__ = "infrastructure"
__pattern__ = "Asset Scanner"
__owns__ = "Unity Localization SharedData tables, prefab/scene hierarchy paths, overrides and scan_unity"

CODE_LINES_PER_FIELD = 4
USE_SITES_PER_KEY = 12
ASSET_EXTS = (".prefab", ".unity", ".asset")
_DOC = re.compile(r"^--- !u!(\d+) &(-?\d+)", re.M)
_REF = re.compile(
    r"^( *)(?:- )?m_TableReference:\n *m_TableCollectionName: ?(.*)\n *m_TableEntryReference:\n *m_KeyId: (-?\d+)\n *m_Key: ?(.*)$",
    re.M,
)
_PARENT = re.compile(r"^( *)(?:- )?([A-Za-z_]\w*):\s*$")
_ENTRY = re.compile(r"- m_Id: (-?\d+)\n\s+m_Key: (.*)")
_MOD = re.compile(r"- target: \{fileID: (-?\d+), guid: (\w+), type: \d+\}\n\s+propertyPath: (.+)\n\s+value: ?(.*)")
_MOD_SLOTS = ((".m_TableEntryReference.m_KeyId", "id"), (".m_TableEntryReference.m_Key", "key"), (".m_TableReference.m_TableCollectionName", "table"))
_DECL = re.compile(r"\bLocalized\w*\s+\w+\s*[;=]")
_CONCAT = re.compile(r"\+|\$\"|string\.Format|\.Format\(|Concat\(")


@dataclass(frozen=True, slots=True)
class _TableMap:
    """Resolved SharedData tables and asset GUID maps for one Unity scan."""

    root: Path
    names: dict[str, str]
    by_name: dict[str, str]
    by_id: dict[tuple[str, str], str]
    by_key: dict[tuple[str, str], str]
    guids_of_id: dict[str, list[str]]
    scripts: dict[str, Path]
    prefabs: dict[str, Path]


@dataclass(slots=True)
class _ScanAcc:
    """Mutable accumulator collecting key usages, script fields and dangling counts."""

    keys: dict[str, dict[str, Any]]
    seen_fields: dict[tuple[str, str], Path] = field(default_factory=dict)
    missing_tables: Counter[str] = field(default_factory=Counter)
    unresolved: int = 0


def find_unity_root(project: Path) -> Path:
    """Return the Assets directory of a Unity project or raise L10nError."""
    project = Path(project)
    for cand in (project, project / "Assets"):
        if cand.name == "Assets" and cand.is_dir() and (cand.parent / "ProjectSettings").is_dir():
            return cand
    if (project / "Assets").is_dir() and (project / "ProjectSettings").is_dir():
        return project / "Assets"
    raise L10nError(
        f"{project}: not a Unity project (no Assets and ProjectSettings folders). --scan supports Unity only for now, "
        "the context agents read other engines' code directly"
    )


def load_tables(
    files: Sequence[tuple[Path, str]], shared_paths: dict[str, Path] | None = None,
) -> tuple[dict[str, str], dict[str, str], dict[tuple[str, str], str], dict[str, set[str]]]:
    """Parse Shared Data assets into (guid->name, name->guid, (guid, id)->key, guid->keys)."""
    names: dict[str, str] = {}
    by_name: dict[str, str] = {}
    by_id: dict[tuple[str, str], str] = {}
    keys: dict[str, set[str]] = {}
    for path, txt in files:
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
            shared_paths[name] = path
        keys.setdefault(guid, set())
        for kid, key in _ENTRY.findall(txt):
            by_id[(guid, kid)] = key.strip()
            keys[guid].add(key.strip())
    return names, by_name, by_id, keys


def _guid_map(root: Path, pattern: str) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for meta in root.rglob(pattern):
        m = re.search(r"guid: (\w+)", read_text(meta))
        if m:
            out[m.group(1)] = meta.with_suffix("")
    return out


def script_classes(root: Path) -> dict[str, Path]:
    """Return MonoBehaviour script guid -> .cs file."""
    return _guid_map(root, "*.cs.meta")


def _docs(txt: str) -> dict[str, tuple[str, str]]:
    starts = [(m.start(), m.group(1), m.group(2)) for m in _DOC.finditer(txt)]
    return {
        fid: (cls, txt[s:starts[i + 1][0] if i + 1 < len(starts) else len(txt)])
        for i, (s, cls, fid) in enumerate(starts)
    }


def _field(m_docs: str, pos: int, indent: int) -> str:
    for line in reversed(m_docs[:pos].splitlines()):
        pm = _PARENT.match(line)
        if pm and len(pm.group(1)) < indent:
            return pm.group(2)
    return ""


def object_paths(docs: dict[str, tuple[str, str]]) -> dict[str, str]:
    """Map GameObject fileID to hierarchy path Parent/Child/Object."""
    go_name: dict[str, str] = {}
    tr_of_go: dict[str, str] = {}
    father: dict[str, str] = {}
    go_of_tr: dict[str, str] = {}
    for fid, (cls, d) in docs.items():
        if cls == "1":
            nm = re.search(r"\n  m_Name: (.*)", d)
            go_name[fid] = nm.group(1).strip() if nm else ""
        elif cls in ("4", "224"):
            g = re.search(r"m_GameObject: \{fileID: (-?\d+)\}", d)
            f = re.search(r"m_Father: \{fileID: (-?\d+)\}", d)
            if g:
                tr_of_go[g.group(1)] = fid
                go_of_tr[fid] = g.group(1)
            if f:
                father[fid] = f.group(1)
    paths: dict[str, str] = {}
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


def _override_usages(d: str, path: Path, tmap: _TableMap, acc: _ScanAcc) -> int:
    groups: dict[tuple[str, str, str], dict[str, str]] = defaultdict(dict)
    for tfid, tguid, ppath, val in _MOD.findall(d):
        for suffix, slot in _MOD_SLOTS:
            if ppath.strip().endswith(suffix):
                groups[(tfid, tguid, ppath.strip()[: -len(suffix)])][slot] = val.strip()
    unresolved = 0
    for (_tfid, tguid, prefix), g in groups.items():
        table_ref = g.get("table", "")
        guid = table_ref[5:] if table_ref.startswith("GUID:") else tmap.by_name.get(table_ref, "")
        kid = g.get("id", "")
        key = ""
        if kid and kid != "0":
            if not guid and len(tmap.guids_of_id.get(kid, [])) == 1:
                guid = tmap.guids_of_id[kid][0]
            key = tmap.by_id.get((guid, kid), "")
        elif g.get("key"):
            key = tmap.by_key.get((guid, g["key"]), g["key"] if g["key"] in acc.keys else "")
        if not key:
            unresolved += 1 if (kid or g.get("key")) else 0
            continue
        field = prefix.split(".")[-1]
        prefab = tmap.prefabs.get(tguid)
        use = {
            "file": _rel(path, tmap.root),
            "object": (prefab.stem if prefab else "prefab instance") + " (override)",
            "class": "LocalizeStringEvent" if field == "m_StringReference" else "",
            "field": field,
        }
        if use not in acc.keys[key]["usages"]:
            acc.keys[key]["usages"].append(use)
    return unresolved


def _prepare_table_map(
    root: Path, files: Sequence[tuple[Path, str]], tables_out: dict[str, dict[str, Any]] | None,
) -> tuple[_TableMap, _ScanAcc]:
    shared_paths: dict[str, Path] = {}
    names, by_name, raw_id, table_keys = load_tables(files, shared_paths)
    if not names:
        raise L10nError(f"{root}: no Unity Localization string table (Shared Data asset) found")
    name_count = Counter(k for ks in table_keys.values() for k in ks)

    def label(guid: str, k: str) -> str:
        return f"{names[guid]}:{k}" if name_count[k] > 1 else k

    by_id = {gk: label(gk[0], k) for gk, k in raw_id.items()}
    by_key = {(g, k): label(g, k) for g, ks in table_keys.items() for k in ks}
    guids_of_id: dict[str, list[str]] = defaultdict(list)
    for g, kid in by_id:
        guids_of_id[kid].append(g)
    if tables_out is not None:
        for guid, name in names.items():
            tables_out[name] = {"shared": shared_paths[name], "ids": {kid: k for (g, kid), k in by_id.items() if g == guid}}
    keys: dict[str, dict[str, Any]] = {}
    for guid, ks in table_keys.items():
        for k in ks:
            lab = label(guid, k)
            keys[lab] = {"table": names[guid], "usages": [], "code": []}
            if name_count[k] > 1:
                keys[lab]["name"] = k
    tmap = _TableMap(root, names, by_name, by_id, by_key, guids_of_id, script_classes(root), _guid_map(root, "*.prefab.meta"))
    return tmap, _ScanAcc(keys=keys)


def _scan_mono_doc(d: str, path: Path, paths: dict[str, str], tmap: _TableMap, acc: _ScanAcc) -> None:
    sm = re.search(r"m_Script: \{fileID: \d+, guid: (\w+)", d)
    script = tmap.scripts.get(sm.group(1)) if sm else None
    gm = re.search(r"m_GameObject: \{fileID: (-?\d+)\}", d)
    obj = paths.get(gm.group(1), "") if gm and gm.group(1) != "0" else ""
    if not obj:
        nm = re.search(r"\n  m_Name: (.+)", d)
        obj = nm.group(1).strip() if nm else ""
    for m in _REF.finditer(d):
        table_ref, kid, kname = m.group(2).strip(), m.group(3), m.group(4).strip()
        guid = table_ref[5:] if table_ref.startswith("GUID:") else tmap.by_name.get(table_ref, "")
        key = tmap.by_id.get((guid, kid)) if kid not in ("0", "") else tmap.by_key.get((guid, kname), "")
        if not key and not table_ref and kname in acc.keys:
            key = kname
        if not key:
            if table_ref and guid not in tmap.names:
                acc.missing_tables[table_ref] += 1
            elif table_ref:
                acc.unresolved += 1
            continue
        field = _field(d, m.start(), len(m.group(1)))
        cls = script.stem if script else ("LocalizeStringEvent" if field == "m_StringReference" else "")
        use = {"file": _rel(path, tmap.root), "object": obj, "class": cls, "field": field}
        if use not in acc.keys[key]["usages"]:
            acc.keys[key]["usages"].append(use)
        if script is not None and field:
            acc.seen_fields[(cls, field)] = script


def _collect_field_code(root: Path, acc: _ScanAcc, code_lines: int) -> None:
    code_cache: dict[Path, list[str]] = {}
    field_code: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for (cls, fld), script in acc.seen_fields.items():
        lines = code_cache.setdefault(script, read_text(script).splitlines())
        rx = re.compile(r"\b" + re.escape(fld) + r"\b")
        hits: list[dict[str, Any]] = []
        for n, line in enumerate(lines, start=1):
            s = line.strip()
            if rx.search(s) and not _DECL.search(s) and not s.startswith(("//", "[", "///")):
                hits.append({"file": _rel(script, root), "line": n, "text": s[:240], "concat": bool(_CONCAT.search(s))})
                if len(hits) >= code_lines:
                    break
        field_code[(cls, fld)] = hits
    for info in acc.keys.values():
        for u in info["usages"]:
            for h in field_code.get((u["class"], u["field"]), []):
                if h not in info["code"]:
                    info["code"].append(h)


def scan_unity(
    project: Path, code_lines: int = CODE_LINES_PER_FIELD,
    tables_out: dict[str, dict[str, Any]] | None = None, use_sites: int = USE_SITES_PER_KEY,
) -> dict[str, Any]:
    """Read-only scan collecting every localized key usage across Unity assets and scripts."""
    root = find_unity_root(project)
    files: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        if path.suffix in ASSET_EXTS and path.is_file():
            txt = read_text(path)
            if "m_TableReference" in txt or "m_TableEntryReference" in txt or "m_TableCollectionNameGuidString" in txt:
                files.append((path, txt))
    tmap, acc = _prepare_table_map(root, files, tables_out)
    for path, txt in files:
        if "m_TableReference" not in txt and "m_TableEntryReference" not in txt:
            continue
        docs = _docs(txt)
        paths = object_paths(docs)
        for _fid, (cls, d) in docs.items():
            if cls == "1001" and "m_TableEntryReference" in d:
                acc.unresolved += _override_usages(d, path, tmap, acc)
            if "m_TableReference" in d and cls != "1001":
                _scan_mono_doc(d, path, paths, tmap, acc)
    _collect_field_code(root, acc, code_lines)
    out: dict[str, Any] = {"engine": "unity", "project": root.parent.name, "tables": sorted(tmap.names.values())}
    if use_sites > 0:
        out["use_trace"] = trace_uses(root, acc.keys, acc.seen_fields, use_sites)
    out.update({
        "keys": {k: acc.keys[k] for k in sorted(acc.keys)},
        "unresolved_references": acc.unresolved,
        "missing_table_references": dict(sorted(acc.missing_tables.items())),
    })
    return out
