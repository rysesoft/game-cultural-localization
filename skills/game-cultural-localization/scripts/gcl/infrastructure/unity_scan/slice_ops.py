"""Unity StringTable slice builder and context-scout coverage checker."""

import fnmatch
import json
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from gcl.domain.errors import L10nError
from gcl.infrastructure.formats.unity_yaml_reader import is_unity_asset_table, parse_unity_yaml

from .cs_lexer import read_text

__layer__ = "infrastructure"
__pattern__ = "Slice Builder"
__owns__ = "locale StringTable discovery, scout slice partitioning and scout report coverage checking"

_SLICE_NAME = re.compile(r"[A-Za-z0-9_.-]+")
UNASSIGNED = "unassigned"


def locale_tables(shared: Path) -> dict[str, Path]:
    """Return locale code -> StringTable asset path adjacent to Shared Data asset."""
    meta = shared.with_name(shared.name + ".meta")
    m = re.search(r"guid: (\w+)", read_text(meta)) if meta.is_file() else None
    shared_guid = m.group(1) if m else ""
    out: dict[str, Path] = {}
    for f in sorted(shared.parent.glob("*.asset")):
        if f == shared:
            continue
        text = read_text(f)
        head = text[:4000]
        code = re.search(r"m_LocaleId:\n\s+m_Code: (\S+)", head)
        sd = re.search(r"m_SharedData: \{fileID: -?\d+, guid: (\w+)", head)
        if not code or (shared_guid and sd and sd.group(1) != shared_guid) or is_unity_asset_table(text):
            continue
        out[code.group(1)] = f
    return out


def table_texts(asset: Path) -> dict[str, str]:
    """Return key id -> text for a Unity StringTable asset preserving breaks."""
    data = parse_unity_yaml(read_text(asset).lstrip("\ufeff"))
    return {e["id"]: e["text"] or "" for e in data["entries"] if e["id"] is not None and e["text"] is not None}


def load_slice_spec(path: Path) -> dict[str, list[str]]:
    """Read {slice name: [table name or glob, ...]} JSON specification."""
    if not path.is_file():
        raise L10nError(f"--slices file not found: {path}")
    try:
        spec = json.loads(read_text(path).lstrip("\ufeff"))
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


def _assign_tables(scan: dict[str, Any], spec: dict[str, list[str]]) -> dict[str, str]:
    assign: dict[str, str] = {}
    for name, globs in spec.items():
        hit = [t for t in scan["tables"] if any(fnmatch.fnmatchcase(t, g) for g in globs)]
        if not hit:
            raise L10nError(f"slice '{name}': no table matches {globs}. Tables are {', '.join(scan['tables'])}")
        for t in hit:
            if t in assign:
                raise L10nError(f"table {t} is claimed by slice '{assign[t]}' and by slice '{name}', every key must land in exactly one slice")
            assign[t] = name
    return assign


def _load_locale_texts(
    table_names: Sequence[str], tables: dict[str, dict[str, Any]], locales: Sequence[str],
) -> tuple[dict[tuple[str, str], dict[str, str]], list[str]]:
    texts: dict[tuple[str, str], dict[str, str]] = {}
    missing_locales: list[str] = []
    for t in table_names:
        found = locale_tables(tables[t]["shared"])
        for loc in locales:
            if loc not in found:
                missing_locales.append(f"{t} {loc}")
                texts[(t, loc)] = {}
                continue
            ids = tables[t]["ids"]
            texts[(t, loc)] = {ids[kid]: txt for kid, txt in table_texts(found[loc]).items() if kid in ids}
    return texts, missing_locales


def build_slices(
    scan: dict[str, Any], tables: dict[str, dict[str, Any]], spec: dict[str, list[str]], source_locale: str,
    target_locale: str | None = None, ref_meta: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Build per-slice scout inputs from the project's string tables."""
    assign = _assign_tables(scan, spec)
    locales = [source_locale] + ([target_locale] if target_locale and target_locale != source_locale else [])
    texts, missing_locales = _load_locale_texts(scan["tables"], tables, locales)
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ref_meta = ref_meta or {}
    for key, info in sorted(scan["keys"].items(), key=lambda kv: (kv[1]["table"], kv[0])):
        t = info["table"]
        row: dict[str, Any] = {"key": key, "table": t, **{loc: texts[(t, loc)].get(key, "") for loc in locales}}
        meta = ref_meta.get(key) or ref_meta.get(info.get("name", ""), {})
        row["category"] = str(meta.get("category") or "")
        row["speaker"] = str(meta.get("speaker") or "")
        for fld, default in (("usages", []), ("code", []), ("loads", []), ("uses", []), ("uses_total", 0), ("loaded_not_shown", False)):
            row[fld] = info.get(fld, default)
        out[assign.get(t, UNASSIGNED)].append(row)
    stats = {
        "slices": {n: len(rows) for n, rows in sorted(out.items())},
        "unassigned_tables": sorted(t for t in scan["tables"] if t not in assign),
        "missing_locale_tables": missing_locales,
    }
    return dict(out), stats


def check_slices(folder: Path) -> dict[str, dict[str, Any]]:
    """Verify every key of <slice>.input.json appears in exactly one entry of <slice>.report.json."""
    inputs = sorted(folder.glob("*.input.json"))
    if not inputs:
        raise L10nError(f"{folder}: no <slice>.input.json files, run --slices first")
    res: dict[str, dict[str, Any]] = {}
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
        seen: Counter[str] = Counter()
        questions = 0
        for e in rep:
            if isinstance(e, dict):
                ks = e.get("keys") if isinstance(e.get("keys"), list) else ([e["key"]] if e.get("key") else [])
                seen.update(str(k) for k in ks)
                questions += len(e.get("questions") or [])
        res[name] = {
            "keys": len(want), "report": True, "missing": sorted(want - set(seen)),
            "duplicated": sorted(k for k, c in seen.items() if c > 1), "unknown": sorted(set(seen) - want),
            "questions": questions,
        }
    return res
