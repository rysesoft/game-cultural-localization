"""Unity Localization YAML StringTable reader and AssetTable guard."""

import re
from pathlib import Path
from typing import Any

from gcl.domain.errors import L10nError
from gcl.domain.models import Row

from .io_utils import read_text_bom

__layer__ = "infrastructure"
__pattern__ = "YAML Asset Reader"
__owns__ = "Unity StringTable parsing, YAML scalar folding and AssetTable detection"

_YAML_SCALAR_RE = re.compile(r"^(\s*)(?:- )?(m_Localized|m_Key|m_Id|m_Code|m_Name):\s*(.*)$")
_YAML_DQ_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "0": "\0", "/": "/"}
UNITY_ASSET_TABLE_SCRIPT = "97269afb30aa84742ae3f3342603618a"
_ASSET_GUID_RE = re.compile(r"[0-9a-f]{32}")


def _decode_dq(inner: str) -> str:
    return re.sub(
        r"\\(u[0-9A-Fa-f]{4}|x[0-9A-Fa-f]{2}|.)",
        lambda m: _YAML_DQ_ESCAPES.get(m.group(1), m.group(1)) if len(m.group(1)) == 1 else chr(int(m.group(1)[1:], 16)),
        inner,
    )


def _quote_end(text: str, quote: str) -> int:
    i = 0
    while i < len(text):
        c = text[i]
        if quote == '"' and c == "\\":
            i += 2
            continue
        if c == quote:
            if quote == "'" and text[i + 1:i + 2] == "'":
                i += 2
                continue
            return i
        i += 1
    return -1


def _fold_flow(lines: list[str], double: bool) -> str:
    out, empties = lines[0].rstrip(" \t"), 0
    for ln in lines[1:]:
        s = ln.strip(" \t")
        if s == "":
            empties += 1
            continue
        tail = len(out) - len(out.rstrip("\\"))
        if double and tail % 2 == 1 and not empties:
            out = out[:-1] + s
        else:
            out += ("\n" * empties if empties else " ") + s
        empties = 0
    return out + "\n" * empties


def _block_scalar(v: str, following: list[str], indent: int) -> tuple[str, int]:
    block: list[str] = []
    for ln in following:
        if ln.strip() == "" or (len(ln) - len(ln.lstrip(" "))) > indent:
            block.append(ln)
        else:
            break
    non_empty = [b for b in block if b.strip()]
    base = min((len(b) - len(b.lstrip(" "))) for b in non_empty) if non_empty else 0
    lines = [b[base:] if b.strip() else "" for b in block]
    while lines and lines[-1] == "":
        lines.pop()
    text = "\n".join(lines) if v.startswith("|") else " ".join(l for l in lines if l)
    return text + ("" if v.endswith("-") else "\n"), len(block)


def _yaml_scalar(value: str, following: list[str], indent: int, content_indent: int | None = None) -> tuple[str, int]:
    """Decode single/multiline quoted, block or plain YAML scalar returning (text, lines_consumed)."""
    v = value.strip()
    if v[:1] in ("'", '"'):
        q = v[0]
        body, used = [value.lstrip()[1:]], 0
        while _quote_end("\n".join(body), q) < 0 and used < len(following):
            body.append(following[used])
            used += 1
        if used:
            joined = "\n".join(body)
            end = _quote_end(joined, q)
            inner = _fold_flow((joined[:end] if end >= 0 else joined).split("\n"), q == '"')
            return (inner.replace("''", "'") if q == "'" else _decode_dq(inner)), used
    if v in ("|", "|-", "|+", ">", ">-", ">+"):
        return _block_scalar(v, following, indent)
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return _decode_dq(v[1:-1]), 0
    if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
        return v[1:-1].replace("''", "'"), 0
    if v and content_indent is not None:
        more: list[str] = []
        for ln in following:
            if ln.strip() == "" or (len(ln) - len(ln.lstrip(" "))) > content_indent:
                more.append(ln)
            else:
                break
        while more and more[-1].strip() == "":
            more.pop()
        if more:
            return _fold_flow([v] + more, False), len(more)
    return v, 0


def is_unity_asset_table(text: str) -> bool:
    """True when text is a Unity AssetTable holding GUIDs rather than localized strings."""
    if f"guid: {UNITY_ASSET_TABLE_SCRIPT}" in text[:4000]:
        return True
    if "m_TableData:" not in text or "m_SharedData:" not in text:
        return False
    values = [v.strip().strip("'\"") for v in re.findall(r"\n\s+m_Localized: (.*)", text)]
    values = [v for v in values if v]
    return bool(values) and all(_ASSET_GUID_RE.fullmatch(v) for v in values)


def parse_unity_yaml(text: str) -> dict[str, Any]:
    """Extract entries, locale and collection name from a Unity StringTable or SharedData."""
    lines, entries = text.splitlines(), []
    cur: dict[str, Any] | None = None
    locale_code = name = None
    i = 0
    while i < len(lines):
        m = _YAML_SCALAR_RE.match(lines[i])
        if not m:
            i += 1
            continue
        indent, field, value = len(m.group(1)), m.group(2), m.group(3)
        is_item = lines[i].lstrip().startswith("- ")
        scalar, used = _yaml_scalar(value, lines[i + 1:], indent, indent + 2 if is_item else indent)
        if field in ("m_Id", "m_Key", "m_Localized"):
            attr = {"m_Id": "id", "m_Key": "key", "m_Localized": "text"}[field]
            if is_item or cur is None or cur.get(attr) is not None:
                cur = {"id": None, "key": None, "text": None}
                entries.append(cur)
            cur[attr] = scalar
        elif field == "m_Code":
            locale_code = locale_code or scalar
        elif field == "m_Name":
            name = name or scalar
        i += 1 + used
    kind = "string_table" if any(e["text"] is not None for e in entries) else ("shared_table" if any(e["key"] is not None for e in entries) else "unknown")
    return {"entries": entries, "locale": locale_code, "name": name, "kind": kind}


def load_unity_rows(path: Path, src_input: Path | None, shared_table: Path | None) -> list[Row]:
    """Load Row entries from a Unity Localization .asset table."""
    raw = read_text_bom(path)
    if is_unity_asset_table(raw):
        raise L10nError(f"{path}: this is a Unity Localization AssetTable (asset GUIDs, not text), it has nothing to translate")
    data = parse_unity_yaml(raw)
    if data["kind"] != "string_table":
        raise L10nError(f"{path}: no 'm_Localized' entries found; expected a Unity Localization StringTable .asset")
    key_names = {}
    if shared_table is not None:
        key_names = {e["id"]: e["key"] for e in parse_unity_yaml(read_text_bom(shared_table))["entries"] if e["id"] and e["key"] is not None}
    src_texts = {}
    if src_input is not None:
        src_data = parse_unity_yaml(read_text_bom(src_input))
        if src_data["kind"] != "string_table":
            raise L10nError(f"{src_input}: no 'm_Localized' entries found in --src-input table")
        src_texts = {e["id"]: e["text"] or "" for e in src_data["entries"] if e["id"] is not None}
    rows: list[Row] = []
    for idx, e in enumerate(data["entries"]):
        if e["text"] is not None:
            eid = e["id"] or f"row_{idx}"
            rows.append(Row(key_names.get(eid, eid), src_texts.get(eid, ""), e["text"], {"unity_id": eid, "locale": data["locale"]}))
    return rows
