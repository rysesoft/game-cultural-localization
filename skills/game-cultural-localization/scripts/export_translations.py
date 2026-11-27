#!/usr/bin/env python3
"""Final translations into the game's own table format, with the developer's decisions applied.

The last step of the jury flow. orchestrator_stub.py writes final_batch_NN.json and report_changes.py writes
changes_<locale>_<batch>.json with an empty 'decision' per flagged line. This tool
  1. merges the final batches (key -> target text),
  2. applies the decisions of the change reports. accept keeps the new line, reject puts the old line back.
     A changed line without a decision keeps its final text and is reported, nothing ships undecided unseen,
  3. holds back every text whose placeholders or rich text tags differ from its source line (the en column of
     the final files). It is not written, the game keeps the text it has, and the key is reported,
  4. writes the texts in the format of the game's own tables, never into the game project.

Formats, chosen by the template, the table the game already has for the target locale
  .asset     Unity Localization StringTable. Only m_Localized of the known keys changes, every other line stays
             as it was. Key names come from the collection's Shared Data asset (found next to the table by its
             m_SharedData guid, or --shared-table). A key the table has no entry for gets a new entry.
             SmartFormat and rich text markers are plain text to this tool and pass through unchanged. Texts are
             written as YAML double quoted scalars with line breaks as \\n, and the written file is read back and
             compared before it is kept, every written line also by a strict YAML reader (the plugin's own reader
             is lenient and would take a broken line).
  .csv .tsv  the target column (--dst-field, default the locale code) of the matching keys, other columns kept
  .json      a list of objects or {key: text or object}, the target field of the matching keys
  .po        msgstr (msgstr[n] for plural keys 'msgid|[n]') of the matching keys, the fuzzy flag of a filled entry dropped

A plain key that two Unity tables share needs the label Table:Key in the final files (build_context_map.py
labels such keys the same way), otherwise the export stops instead of guessing.

INPUT is one final file or a folder. A folder means every final_batch_*.json in it and, unless --changes is
given, every changes_<locale>_*.json in it.

Usage
  python export_translations.py loc_work/run_tr --locale tr-TR --template-dir "<game>/Assets/Localisation/Tables" --out loc_work/export
  python export_translations.py final_batch_01.json --locale tr-TR --changes changes_tr-TR_01.json --template strings_tr.csv --out loc_work/export

Never writes into a game project. --out is refused inside a Unity, Godot or Unreal project, and the written
files keep the template's file name, so the developer copies them over the originals by hand.

Exit codes: 0 exported, every changed line decided and every key placed, 1 exported but changed lines without
a decision, texts held back for their placeholders or tags, or keys no template holds, 2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import codecs
import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, PLACEHOLDER_STYLES, TAG_STYLES, L10nError, _yaml_scalar, add_common_args, add_input_argument, apply_config,
    emit_report, is_unity_asset_table, load_json_data, load_table, normalize_locale, parity_problems, parse_po, parse_unity_yaml,
    read_text_bom, resolve_input,
    run_main, sniff_delimiter, __version__,
)

TOOL = "export_translations"
DECISIONS = ("accept", "reject", "")
TEMPLATE_SUFFIXES = (".asset", ".csv", ".tsv", ".json", ".po")


# --------------------------------------------------------------------------- #
# Inputs and decisions
# --------------------------------------------------------------------------- #
def game_root(path: Path) -> Optional[Path]:
    """The Unity, Godot or Unreal project a path lies in, None outside any project."""
    p = Path(path).resolve()
    for d in [p] + list(p.parents):
        if (d / "ProjectSettings").is_dir() and (d / "Assets").is_dir():
            return d
        if (d / "project.godot").is_file():
            return d
        try:
            if d.is_dir() and any(d.glob("*.uproject")):
                return d
        except OSError:
            continue
    return None


def collect_inputs(inp: Path, locale: str, changes: Sequence[str]) -> Tuple[List[Path], List[Path]]:
    """(final files, change reports). A folder gives its final_batch_*.json and, without --changes, its change reports."""
    if inp.is_dir():
        finals = sorted(inp.glob("final_batch_*.json"))
        if not finals:
            raise L10nError(f"{inp}: no final_batch_*.json in this folder")
        reports = [Path(c) for c in changes] if changes else sorted(inp.glob(f"changes_{locale}_*.json"))
    elif inp.is_file():
        finals, reports = [inp], [Path(c) for c in changes]
    else:
        raise L10nError(f"input not found: {inp}")
    for r in reports:
        if not r.is_file():
            raise L10nError(f"--changes file not found: {r}")
    return finals, reports


def load_finals(paths: Sequence[Path], locale: str, dst_field: Optional[str], key_field: str,
                sources: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """key -> final text from every final file. One key with two different texts is an input error.

    `sources` collects the English source line of every key whose final file carries one (the en column).
    """
    out: Dict[str, str] = {}
    for p in paths:
        rows = None
        for col in ([dst_field] if dst_field else [locale, "dst", "target"]):
            try:
                rows = load_table(p, "en", col, key_field, target_only=True)
                break
            except L10nError:
                continue
        if rows is None:
            raise L10nError(f"{p}: no target column (tried {dst_field or ', '.join((locale, 'dst', 'target'))}), pass --dst-field")
        for r in rows:
            if r.key in out and out[r.key] != r.dst:
                raise L10nError(f"{p}: key '{r.key}' has two different final texts")
            out[r.key] = r.dst
            src = r.src or str((r.meta or {}).get("en") or "")  # target_only leaves src empty, the row keeps its columns
            if sources is not None and src.strip():
                sources[r.key] = src
    return out


def hold_back_broken(final: Dict[str, str], sources: Dict[str, str], ph_style: str, tag_style: str) -> Dict[str, List[str]]:
    """Take every text whose placeholders or rich text tags differ from its source line out of `final` (in place).

    Such a text crashes or garbles the game where the code fills the placeholder. It is not written, the game's
    table keeps the text it has, and the key is reported. A text without a source line is not checked.
    """
    held: Dict[str, List[str]] = {}
    for key in list(final):
        problems = parity_problems(sources.get(key, ""), final[key], ph_style, tag_style)
        if problems:
            held[key] = problems
            del final[key]
    return held


def apply_decisions(final: Dict[str, str], reports: Sequence[Path]) -> Dict[str, Any]:
    """Apply accept and reject of every change report to final (in place). Returns the counts and open lines."""
    stats: Dict[str, Any] = {"accepted": 0, "rejected": 0, "undecided": [], "unknown": []}
    for path in reports:
        rep = load_json_data(path)
        lines = rep.get("lines") if isinstance(rep, dict) else None
        if not isinstance(lines, list):
            raise L10nError(f"{path}: not a change report of report_changes.py (no 'lines' list)")
        for line in lines:
            key = str(line.get("key", ""))
            decision = str(line.get("decision") or "").strip().lower()
            if decision not in DECISIONS:
                raise L10nError(f"{path}: line '{key}' has the decision '{decision}', use accept, reject or leave it empty")
            if key not in final:
                stats["unknown"].append(key)
                continue
            old, new = str(line.get("old", "")), str(line.get("new", ""))
            if decision == "accept":
                final[key] = new
                stats["accepted"] += 1
            elif decision == "reject":
                final[key] = old
                stats["rejected"] += 1
            elif new != old:
                stats["undecided"].append(key)
    return stats


# --------------------------------------------------------------------------- #
# Unity StringTable
# --------------------------------------------------------------------------- #
_ENTRY_ID = re.compile(r"^(\s*)- m_Id: (-?\d+)\s*$")
_LOCALIZED = re.compile(r"^(\s*)m_Localized:(.*)$")
_TABLE_DATA = re.compile(r"^(\s*)m_TableData:\s*(\[\])?\s*$")


def yaml_dq(text: str) -> str:
    """A YAML double quoted scalar on one line. Unity reads it, line breaks travel as \\n."""
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


_DQ_ESCAPES = {"\\": "\\", '"': '"', "/": "/", " ": " ", "0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n",
               "v": "\v", "f": "\f", "r": "\r", "e": "\x1b", "N": "\x85", "_": "\xa0", "L": " ", "P": " "}
_DQ_HEX = {"x": 2, "u": 4, "U": 8}


def strict_dq(value: str) -> str:
    """Decode one YAML double quoted scalar on one line the way the YAML spec reads it, ValueError when it is not one.

    The plugin's own Unity reader is lenient and reads a broken line too, so it cannot check what the export wrote.
    """
    v = value.strip()
    if len(v) < 2 or v[0] != '"' or v[-1] != '"':
        raise ValueError("not a double quoted scalar on one line")
    out: List[str] = []
    i, end = 1, len(v) - 1
    while i < end:
        ch = v[i]
        if ch == '"':
            raise ValueError(f"unescaped quote at column {i}")
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= end:
            raise ValueError("escape at the end of the scalar")
        esc = v[i + 1]
        if esc in _DQ_HEX:
            digits = v[i + 2:i + 2 + _DQ_HEX[esc]]
            if len(digits) != _DQ_HEX[esc] or i + 2 + len(digits) > end or any(c not in "0123456789abcdefABCDEF" for c in digits):
                raise ValueError(f"bad \\{esc} escape at column {i}")
            out.append(chr(int(digits, 16)))
            i += 2 + len(digits)
            continue
        if esc not in _DQ_ESCAPES:
            raise ValueError(f"unknown escape \\{esc} at column {i}")
        out.append(_DQ_ESCAPES[esc])
        i += 2
    return "".join(out)


def check_written(text: str, written: Dict[str, str]) -> List[str]:
    """Key ids whose written m_Localized line does not decode strictly to its text, or is missing."""
    seen: Dict[str, bool] = {}
    cur: Optional[str] = None
    for ln in text.splitlines():
        m = _ENTRY_ID.match(ln)
        if m:
            cur = m.group(2)
            continue
        lm = _LOCALIZED.match(ln)
        if lm and cur in written and cur not in seen:
            try:
                seen[cur] = strict_dq(lm.group(2)) == written[cur]
            except ValueError:
                seen[cur] = False
    return [i for i in written if not seen.get(i)]


def unity_rewrite(text: str, id_texts: Dict[str, str], written: Optional[Dict[str, str]] = None) -> str:
    """Replace m_Localized of the given key ids, append entries for ids the table lacks. Other lines stay as they were.

    `written` collects the ids whose line this call wrote anew (with the text), for the strict read back.
    """
    written = {} if written is None else written
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    out: List[str] = []
    done: set = set()
    cur: Optional[str] = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = _ENTRY_ID.match(ln)
        if m:
            cur = m.group(2)
        lm = _LOCALIZED.match(ln)
        if lm and cur in id_texts and cur not in done:
            indent = len(lm.group(1))
            value, used = _yaml_scalar(lm.group(2), lines[i + 1:], indent, indent)
            if value == id_texts[cur]:  # same text, keep the original lines so the diff shows real changes only
                out.extend(lines[i:i + 1 + used])
            else:
                out.append(f"{lm.group(1)}m_Localized: {yaml_dq(id_texts[cur])}")
                written[cur] = id_texts[cur]
            done.add(cur)
            i += 1 + used
            continue
        out.append(ln)
        i += 1
    missing = [k for k in id_texts if k not in done]
    if missing:
        idx = next((n for n, ln in enumerate(out) if _TABLE_DATA.match(ln)), None)
        if idx is None:
            raise L10nError("the template has no m_TableData list, it is not a Unity StringTable")
        tm = _TABLE_DATA.match(out[idx])
        base = tm.group(1)
        if tm.group(2):  # an empty table, 'm_TableData: []'
            out[idx] = f"{base}m_TableData:"
        # the list ends at the first line that is neither an item nor indented deeper. An empty line inside it is a
        # paragraph break of a text written over several lines, not the end of the list
        last, j = idx, idx + 1
        while j < len(out):
            if out[j].strip():
                if not (out[j].startswith(base + "- ") or len(out[j]) - len(out[j].lstrip(" ")) > len(base)):
                    break
                last = j
            j += 1
        end = last + 1
        block: List[str] = []
        for kid in missing:
            block += [f"{base}- m_Id: {kid}", f"{base}  m_Localized: {yaml_dq(id_texts[kid])}", f"{base}  m_Metadata:", f"{base}    m_Items: []"]
            written[kid] = id_texts[kid]
        out[end:end] = block
    return nl.join(out)


def unity_tables(template_dir: Path, locale: str) -> List[Path]:
    """Every StringTable asset of the locale under template_dir (by m_LocaleId, not by file name).

    An AssetTable of the locale (textures and other assets by GUID) is left out, it holds no text to write."""
    found = []
    for p in sorted(template_dir.rglob("*.asset")):
        text = read_text_bom(p)
        m = re.search(r"m_LocaleId:\s*\n\s+m_Code: (\S+)", text[:4000])
        if m and normalize_locale(m.group(1))[0] == locale and not is_unity_asset_table(text):
            found.append(p)
    return found


def shared_of(table: Path, text: str, override: Optional[Path]) -> Path:
    """The Shared Data asset of a StringTable, by its m_SharedData guid among the .meta files of its folder."""
    if override is not None:
        return override
    m = re.search(r"m_SharedData: \{fileID: -?\d+, guid: (\w+)", text)
    if m:
        for meta in table.parent.glob("*.asset.meta"):
            if f"guid: {m.group(1)}" in read_text_bom(meta):
                return meta.with_name(meta.name[: -len(".meta")])
    raise L10nError(f"{table}: its Shared Data asset was not found next to it, pass --shared-table")


def assign_unity_keys(final: Dict[str, str], tables: Dict[Path, Tuple[str, Dict[str, str]]]) -> Dict[Path, Dict[str, str]]:
    """key -> (table, id). Table:Key labels pick their table, a plain key must fit exactly one table."""
    per_table: Dict[Path, Dict[str, str]] = {t: {} for t in tables}
    labelled = {k.split(":", 1)[1]: k.split(":", 1)[0] for k in final if ":" in k}
    for key, text in final.items():
        hits = []
        for t, (collection, name_to_id) in tables.items():
            if key in name_to_id:
                hits.append((t, name_to_id[key]))
            elif ":" in key and key.split(":", 1)[0] == collection and key.split(":", 1)[1] in name_to_id:
                hits.append((t, name_to_id[key.split(":", 1)[1]]))
        if len(hits) > 1 and ":" not in key:  # the plain name of a key two tables share
            hits = [(t, i) for t, i in hits if tables[t][0] != labelled.get(key)]
        if len(hits) > 1:
            names = ", ".join(sorted(tables[t][0] for t, _ in hits))
            raise L10nError(f"key '{key}' is in the tables {names}, label it Table:Key in the final file")
        if hits:
            per_table[hits[0][0]][hits[0][1]] = text
    return per_table


def export_unity(final: Dict[str, str], templates: Sequence[Path], shared_override: Optional[Path], out_dir: Path) -> Dict[str, Any]:
    tables: Dict[Path, Tuple[str, Dict[str, str]]] = {}
    texts: Dict[Path, str] = {}
    for t in templates:
        text = read_text_bom(t)
        shared = shared_of(t, text, shared_override)
        sdata = parse_unity_yaml(read_text_bom(shared))
        collection = re.search(r"\n\s*m_TableCollectionName: (.+)", read_text_bom(shared))
        name_to_id = {e["key"]: e["id"] for e in sdata["entries"] if e.get("key") is not None and e.get("id") is not None}
        tables[t] = ((collection.group(1).strip() if collection else shared.stem), name_to_id)
        texts[t] = text
    per_table = assign_unity_keys(final, tables)
    placed = 0
    files = []
    unchanged = 0
    for t, id_texts in per_table.items():
        if not id_texts:
            continue
        written: Dict[str, str] = {}
        new = unity_rewrite(texts[t], id_texts, written)
        placed += len(id_texts)
        if new == texts[t]:  # every text is already in the game, the developer has nothing to copy
            unchanged += 1
            continue
        got = {e["id"]: e["text"] for e in parse_unity_yaml(new)["entries"] if e.get("text") is not None}
        wrong = [i for i, s in id_texts.items() if got.get(i) != s]
        wrong += [i for i in check_written(new, written) if i not in wrong]  # strict, the lenient reader takes broken YAML too
        if wrong:
            raise L10nError(f"{t.name}: read back differs for key ids {', '.join(wrong[:5])}, nothing written")
        dest = out_dir / t.name
        dest.write_bytes(new.encode("utf-8"))
        files.append(dest.name)
    keys_placed = {k for k in final if any(_unity_key_in(k, tables[t]) for t in tables)}
    return {"files": files, "placed": placed, "unchanged": unchanged, "not_placed": sorted(set(final) - keys_placed)}


def _unity_key_in(key: str, table: Tuple[str, Dict[str, str]]) -> bool:
    collection, name_to_id = table
    return key in name_to_id or (":" in key and key.split(":", 1)[0] == collection and key.split(":", 1)[1] in name_to_id)


# --------------------------------------------------------------------------- #
# CSV, TSV, JSON and PO
# --------------------------------------------------------------------------- #
def export_csv(final: Dict[str, str], template: Path, dst_field: str, key_field: str, out_dir: Path) -> Dict[str, Any]:
    raw_bytes = template.read_bytes()
    bom = raw_bytes.startswith(codecs.BOM_UTF8)
    raw = read_text_bom(template)
    delim = sniff_delimiter(raw, template.suffix.lower())
    rows = list(csv.reader(io.StringIO(raw, newline=""), delimiter=delim))
    if not rows:
        raise L10nError(f"{template}: the table is empty")
    header = [h.strip() for h in rows[0]]
    if key_field not in header:
        raise L10nError(f"{template}: no key column '{key_field}', pass --key-field")
    ki = header.index(key_field)
    if dst_field not in header:
        header.append(dst_field)
        rows[0].append(dst_field)
    di = header.index(dst_field)
    placed = set()
    for row in rows[1:]:
        if len(row) <= ki:
            continue
        while len(row) < len(header):
            row.append("")
        if row[ki] in final:
            row[di] = final[row[ki]]
            placed.add(row[ki])
    buf = io.StringIO()
    csv.writer(buf, delimiter=delim, lineterminator="\r\n" if "\r\n" in raw else "\n").writerows(rows)
    (out_dir / template.name).write_bytes((codecs.BOM_UTF8 if bom else b"") + buf.getvalue().encode("utf-8"))
    return {"files": [template.name], "placed": len(placed), "keys": placed}


def export_json(final: Dict[str, str], template: Path, dst_field: str, key_field: str, out_dir: Path) -> Dict[str, Any]:
    data = load_json_data(template)
    placed = set()
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and str(item.get(key_field)) in final:
                item[dst_field] = final[str(item[key_field])]
                placed.add(str(item[key_field]))
    elif isinstance(data, dict):
        for k, v in data.items():
            if k in final:
                if isinstance(v, dict):
                    v[dst_field] = final[k]
                else:
                    data[k] = final[k]
                placed.add(k)
    else:
        raise L10nError(f"{template}: top-level JSON must be a list or an object")
    (out_dir / template.name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"files": [template.name], "placed": len(placed), "keys": placed}


def po_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def export_po(final: Dict[str, str], template: Path, out_dir: Path) -> Dict[str, Any]:
    raw = read_text_bom(template)
    nl = "\r\n" if "\r\n" in raw else "\n"
    blocks = re.split(r"(?:\r?\n){2,}", raw.strip("\r\n"))
    placed = set()
    out_blocks = []
    for block in blocks:
        rows = parse_po(block + nl)
        keys = [r.key for r in rows]
        if not rows or not any(k in final for k in keys):
            out_blocks.append(block)
            continue
        lines = block.split(nl)
        first = next(i for i, ln in enumerate(lines) if ln.startswith("msgstr"))
        head = [re.sub(r",\s*fuzzy\b", "", ln) if ln.startswith("#,") else ln for ln in lines[:first]]
        head = [ln for ln in head if ln.strip() != "#,"]
        if len(rows) > 1 or "|[" in rows[0].key:
            body = []
            for idx, r in enumerate(rows):
                text = final.get(r.key, r.dst)
                body.append(f"msgstr[{idx}] {po_quote(text)}")
                placed.update([r.key] if r.key in final else [])
        else:
            body = [f"msgstr {po_quote(final.get(rows[0].key, rows[0].dst))}"]
            placed.add(rows[0].key)
        out_blocks.append(nl.join(head + body))
    (out_dir / template.name).write_bytes((nl + nl).join(out_blocks).encode("utf-8") + nl.encode("utf-8"))
    return {"files": [template.name], "placed": len(placed), "keys": placed}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Final translations into the game's table format with the developer's decisions applied")
    add_input_argument(ap, "A final_batch_NN.json or the orchestrator's workdir with final_batch_*.json and changes_<locale>_*.json")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--changes", action="append", default=[], help="Change report of report_changes.py with filled decisions (repeatable, default: those in the INPUT folder)")
    ap.add_argument("--template", action="append", default=[], help="The game's table of the target locale (.asset, .csv, .tsv, .json, .po), repeatable")
    ap.add_argument("--template-dir", default=None, help="Folder of Unity StringTable assets, every table of --locale in it is a template")
    ap.add_argument("--shared-table", default=None, help="Shared Data asset of a single Unity template (default: found next to the table)")
    ap.add_argument("--out", required=True, help="Output folder, for example loc_work/export (never inside the game project)")
    ap.add_argument("--dst-field", default=None, help="Target column of the final files and of a CSV or JSON template (default: the locale code)")
    ap.add_argument("--key-field", default="key", help="Key column (default key)")
    ap.add_argument("--placeholder-style", choices=PLACEHOLDER_STYLES, default=None,
                    help="Placeholder syntax for the parity check against the source line (default auto, or placeholder_style of --config)")
    ap.add_argument("--tag-style", choices=TAG_STYLES, default=None, help="Rich text tag syntax for the same check (default auto, or tag_style of --config)")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    apply_config(args, {"placeholder_style": "auto", "tag_style": "auto"})
    locale, _v = normalize_locale(args.locale)
    templates = [Path(t) for t in args.template]
    if args.template_dir:
        tdir = Path(args.template_dir)
        if not tdir.is_dir():
            raise L10nError(f"--template-dir not found: {tdir}")
        found = unity_tables(tdir, locale)
        if not found:
            raise L10nError(f"{tdir}: no Unity StringTable of {locale} found")
        templates += found
    if not templates:
        ap.error("give the game's table with --template or --template-dir")
    for t in templates:
        if not t.is_file():
            raise L10nError(f"--template file not found: {t}")
        if t.suffix.lower() not in TEMPLATE_SUFFIXES:
            raise L10nError(f"{t}: unsupported template format, supported: {', '.join(TEMPLATE_SUFFIXES)}")
    if len({t.name for t in templates}) != len(templates):
        raise L10nError("two templates share a file name, export them in separate runs")
    out_dir = Path(args.out)
    root = game_root(out_dir if out_dir.exists() else out_dir.parent)
    if root is not None:
        raise L10nError(f"--out {out_dir} lies inside the game project {root.name}, the export never writes into a game project")
    if any(out_dir.resolve() == t.resolve().parent for t in templates):
        raise L10nError("--out must not be the folder of a template, the export never overwrites the game's own files")
    finals, reports = collect_inputs(Path(args.input), locale, args.changes)
    sources: Dict[str, str] = {}
    final = load_finals(finals, locale, args.dst_field, args.key_field, sources)
    decided = apply_decisions(final, reports)
    held = hold_back_broken(final, sources, args.placeholder_style, args.tag_style)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst_field = args.dst_field or locale
    files: List[str] = []
    placed_keys: set = set()
    unity = [t for t in templates if t.suffix.lower() == ".asset"]
    placed = 0
    unchanged = 0
    if unity:
        res = export_unity(final, unity, Path(args.shared_table) if args.shared_table else None, out_dir)
        files += res["files"]
        placed += res["placed"]
        unchanged = res["unchanged"]
        placed_keys |= set(final) - set(res["not_placed"])
    for t in templates:
        suffix = t.suffix.lower()
        if suffix in (".csv", ".tsv"):
            res = export_csv(final, t, dst_field, args.key_field, out_dir)
        elif suffix == ".json":
            res = export_json(final, t, dst_field, args.key_field, out_dir)
        elif suffix == ".po":
            res = export_po(final, t, out_dir)
        else:
            continue
        files += res["files"]
        placed += res["placed"]
        placed_keys |= set(res["keys"])
    not_placed = sorted(set(final) - placed_keys)
    findings = bool(decided["undecided"] or not_placed or held)
    exit_code = EXIT_FINDINGS if findings else EXIT_OK
    lines = [f"Export {locale}: {len(final) + len(held)} final lines from {len(finals)} file(s), {len(reports)} change report(s)",
             f"  decisions accepted {decided['accepted']}, rejected {decided['rejected']}, changed lines without a decision {len(decided['undecided'])}",
             f"  placed {placed} texts, wrote {len(files)} file(s) with changes to {out_dir}: {', '.join(files) or 'none'}"
             + (f", {unchanged} Unity table(s) already hold every text and were not written" if unchanged else "")]
    if decided["undecided"]:
        lines.append(f"  without a decision (final text kept): {', '.join(decided['undecided'][:10])}")
    if held:
        lines.append(f"  held back, placeholders or tags differ from the source line (the game keeps its text): {len(held)}")
        lines += [f"    {k}: {'. '.join(p)}" for k, p in list(held.items())[:10]]
    if not_placed:
        lines.append(f"  keys no template holds: {len(not_placed)}, first {', '.join(not_placed[:10])}")
    if decided["unknown"]:
        lines.append(f"  report lines whose key is not in the final files: {len(decided['unknown'])}")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "locale": locale, "files": files, "placed": placed, "unchanged_tables": unchanged,
               "accepted": decided["accepted"], "rejected": decided["rejected"], "undecided": decided["undecided"],
               "not_placed": not_placed, "held_back": held, "unknown_report_keys": decided["unknown"], "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
