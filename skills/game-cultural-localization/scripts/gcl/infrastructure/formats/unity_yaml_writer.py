"""Unity StringTable export writer and strict double-quoted YAML verifier."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from gcl.domain.errors import L10nError
from gcl.domain.locales import normalize_locale

from .io_utils import read_text_bom
from .unity_yaml_reader import _yaml_scalar, is_unity_asset_table, parse_unity_yaml

__layer__ = "infrastructure"
__pattern__ = "Strategy"
__owns__ = "strict YAML serialization and minimal diff Unity StringTable rewriting"

_ENTRY_ID = re.compile(r"^(\s*)- m_Id: (-?\d+)\s*$")
_LOCALIZED = re.compile(r"^(\s*)m_Localized:(.*)$")
_TABLE_DATA = re.compile(r"^(\s*)m_TableData:\s*(\[\])?\s*$")
_DQ_ESCAPES = {
    "\\": "\\", '"': '"', "/": "/", " ": " ", "0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t",
    "n": "\n", "v": "\v", "f": "\f", "r": "\r", "e": "\x1b", "N": "\x85", "_": "\xa0", "L": "\u2028", "P": "\u2029",
}
_DQ_HEX = {"x": 2, "u": 4, "U": 8}


def yaml_dq(text: str) -> str:
    """Serialize text as a single line double quoted YAML scalar for Unity."""
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch in ("\n", "\t", "\r"):
            out.append({"\n": "\\n", "\t": "\\t", "\r": "\\r"}[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def strict_dq(value: str) -> str:
    """Decode one double quoted YAML scalar strictly per YAML spec or raise ValueError."""
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
        elif esc in _DQ_ESCAPES:
            out.append(_DQ_ESCAPES[esc])
            i += 2
        else:
            raise ValueError(f"unknown escape \\{esc} at column {i}")
    return "".join(out)


def check_written(text: str, written: Dict[str, str]) -> List[str]:
    """Return key ids whose rewritten m_Localized fails strict YAML decoding."""
    seen: Dict[str, bool] = {}
    cur: Optional[str] = None
    for ln in text.splitlines():
        m = _ENTRY_ID.match(ln)
        if m:
            cur = m.group(2)
        else:
            lm = _LOCALIZED.match(ln)
            if lm and cur in written and cur not in seen:
                try:
                    seen[cur] = strict_dq(lm.group(2)) == written[cur]
                except ValueError:
                    seen[cur] = False
    return [i for i in written if not seen.get(i)]


def _append_missing_entries(
    out: List[str],
    missing: List[str],
    id_texts: Dict[str, str],
    written: Dict[str, str],
    quote_fn: Any = yaml_dq,
) -> None:
    idx = next((n for n, ln in enumerate(out) if _TABLE_DATA.match(ln)), None)
    if idx is None:
        raise L10nError("the template has no m_TableData list, it is not a Unity StringTable")
    tm = _TABLE_DATA.match(out[idx])
    base = tm.group(1) if tm else ""
    if tm and tm.group(2):
        out[idx] = f"{base}m_TableData:"
    last, j = idx, idx + 1
    while j < len(out):
        if out[j].strip():
            if not (out[j].startswith(base + "- ") or len(out[j]) - len(out[j].lstrip(" ")) > len(base)):
                break
            last = j
        j += 1
    block: List[str] = []
    for kid in missing:
        block += [f"{base}- m_Id: {kid}", f"{base}  m_Localized: {quote_fn(id_texts[kid])}", f"{base}  m_Metadata:", f"{base}    m_Items: []"]
        written[kid] = id_texts[kid]
    out[last + 1:last + 1] = block


def unity_rewrite(
    text: str,
    id_texts: Dict[str, str],
    written: Optional[Dict[str, str]] = None,
    quote_fn: Any = yaml_dq,
) -> str:
    """Replace m_Localized values for known ids and append entries for missing ids."""
    written = {} if written is None else written
    nl = "\r\n" if "\r\n" in text else "\n"
    lines, out, done, cur, i = text.split(nl), [], set(), None, 0
    while i < len(lines):
        ln = lines[i]
        m = _ENTRY_ID.match(ln)
        if m:
            cur = m.group(2)
        lm = _LOCALIZED.match(ln)
        if lm and cur in id_texts and cur not in done:
            indent = len(lm.group(1))
            value, used = _yaml_scalar(lm.group(2), lines[i + 1:], indent, indent)
            if value == id_texts[cur]:
                out.extend(lines[i:i + 1 + used])
            else:
                out.append(f"{lm.group(1)}m_Localized: {quote_fn(id_texts[cur])}")
                written[cur] = id_texts[cur]
            done.add(cur)
            i += 1 + used
            continue
        out.append(ln)
        i += 1
    missing = [k for k in id_texts if k not in done]
    if missing:
        _append_missing_entries(out, missing, id_texts, written, quote_fn=quote_fn)
    return nl.join(out)


def unity_tables(template_dir: Path, locale: str) -> List[Path]:
    """Return every Unity StringTable under template_dir matching locale (excluding AssetTables)."""
    found = []
    for p in sorted(template_dir.rglob("*.asset")):
        text = read_text_bom(p)
        m = re.search(r"m_LocaleId:\s*\n\s+m_Code: (\S+)", text[:4000])
        if m and normalize_locale(m.group(1))[0] == locale and not is_unity_asset_table(text):
            found.append(p)
    return found


def shared_of(table: Path, text: str, override: Optional[Path]) -> Path:
    if override is not None:
        return override
    m = re.search(r"m_SharedData: \{fileID: -?\d+, guid: (\w+)", text)
    if m:
        for meta in table.parent.glob("*.asset.meta"):
            if f"guid: {m.group(1)}" in read_text_bom(meta):
                return meta.with_name(meta.name[:-len(".meta")])
    raise L10nError(f"{table}: its Shared Data asset was not found next to it, pass --shared-table")


def assign_unity_keys(final: Dict[str, str], tables: Dict[Path, Tuple[str, Dict[str, str]]]) -> Dict[Path, Dict[str, str]]:
    """Map localized keys to matching Unity table ids using Table:Key disambiguation."""
    per_table: Dict[Path, Dict[str, str]] = {t: {} for t in tables}
    labelled = {k.split(":", 1)[1]: k.split(":", 1)[0] for k in final if ":" in k}
    for key, text in final.items():
        hits = []
        for t, (collection, name_to_id) in tables.items():
            if key in name_to_id:
                hits.append((t, name_to_id[key]))
            elif ":" in key and key.split(":", 1)[0] == collection and key.split(":", 1)[1] in name_to_id:
                hits.append((t, name_to_id[key.split(":", 1)[1]]))
        if len(hits) > 1 and ":" not in key:
            hits = [(t, i) for t, i in hits if tables[t][0] != labelled.get(key)]
        if len(hits) > 1:
            names = ", ".join(sorted(tables[t][0] for t, _ in hits))
            raise L10nError(f"key '{key}' is in the tables {names}, label it Table:Key in the final file")
        if hits:
            per_table[hits[0][0]][hits[0][1]] = text
    return per_table


def _unity_key_in(key: str, table: Tuple[str, Dict[str, str]]) -> bool:
    collection, name_to_id = table
    return key in name_to_id or (":" in key and key.split(":", 1)[0] == collection and key.split(":", 1)[1] in name_to_id)


def export_unity(
    final: Dict[str, str],
    templates: Sequence[Path],
    shared_override: Optional[Path],
    out_dir: Path,
    quote_fn: Any = yaml_dq,
) -> Dict[str, Any]:
    """Write modified Unity StringTables after strict roundtrip YAML verification."""
    tables, texts = {}, {}
    for t in templates:
        text = read_text_bom(t)
        shared = shared_of(t, text, shared_override)
        sraw = read_text_bom(shared)
        sdata = parse_unity_yaml(sraw)
        col = re.search(r"\n\s*m_TableCollectionName: (.+)", sraw)
        tables[t] = ((col.group(1).strip() if col else shared.stem), {e["key"]: e["id"] for e in sdata["entries"] if e.get("key") is not None and e.get("id") is not None})
        texts[t] = text
    per_table = assign_unity_keys(final, tables)
    placed, files, unchanged = 0, [], 0
    for t, id_texts in per_table.items():
        if not id_texts:
            continue
        written: Dict[str, str] = {}
        new = unity_rewrite(texts[t], id_texts, written, quote_fn=quote_fn)
        placed += len(id_texts)
        if new == texts[t]:
            unchanged += 1
            continue
        got = {e["id"]: e["text"] for e in parse_unity_yaml(new)["entries"] if e.get("text") is not None}
        wrong = [i for i, s in id_texts.items() if got.get(i) != s]
        wrong += [i for i in check_written(new, written) if i not in wrong]
        if wrong:
            raise L10nError(f"{t.name}: read back differs for key ids {', '.join(wrong[:5])}, nothing written")
        (out_dir / t.name).write_bytes(new.encode("utf-8"))
        files.append(t.name)
    keys_placed = {k for k in final if any(_unity_key_in(k, tables[t]) for t in tables)}
    return {"files": files, "placed": placed, "unchanged": unchanged, "not_placed": sorted(set(final) - keys_placed)}
