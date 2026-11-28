"""Gettext PO table parsing and export Strategy implementation."""

import re
from pathlib import Path
from typing import Any

from gcl.domain.models import Row
from gcl.ports.formats import ExportResult, TableLoadOptions

from .io_utils import read_text_bom

__layer__ = "infrastructure"
__pattern__ = "Strategy"
__owns__ = "gettext PO parsing with plurals, fuzzy and msgctxt plus clean export"

_PO_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def _po_unescape(s: str) -> str:
    def repl(m: re.Match[str]) -> str:
        c = m.group(1)
        if c in _PO_ESCAPES:
            return _PO_ESCAPES[c]
        if c.startswith("u"):
            return chr(int(c[1:], 16))
        if c[0] in "01234567":
            return chr(int(c, 8))
        return c
    return re.sub(r"\\(u[0-9A-Fa-f]{4}|[0-7]{1,3}|.)", repl, s)


def _po_quoted(line: str, prefix_re: str) -> str:
    m = re.match(prefix_re + r'\s*"((?:[^"\\]|\\.)*)"', line)
    return m.group(1) if m else ""


def _finalize_entry(entry: dict[str, Any] | None, rows: list[Row]) -> None:
    if entry is None:
        return
    msgid, plural, msgstr = entry["msgid"], entry["plural"], entry["msgstr"]
    if msgid == "" and plural is None and entry["ctxt"] is None:
        return
    base_key = f"{entry['ctxt']}|{msgid}" if entry["ctxt"] is not None else msgid
    meta_common = {"msgctxt": entry["ctxt"], "fuzzy": entry["fuzzy"], "msgid": msgid}
    if plural is None:
        rows.append(Row(base_key, msgid, msgstr.get(0, ""), dict(meta_common)))
        return
    forms = sorted(msgstr) or [0]
    for idx in forms:
        meta = dict(meta_common)
        meta.update({"plural_index": idx, "plural_nforms": len(forms), "msgid_plural": plural})
        rows.append(Row(f"{base_key}|[{idx}]", msgid if idx == 0 else plural, msgstr.get(idx, ""), meta))


def _ensure_cur(cur: dict[str, Any] | None, pending_ctxt: str | None) -> dict[str, Any]:
    return cur if cur is not None else {"msgid": "", "plural": None, "msgstr": {}, "ctxt": pending_ctxt, "fuzzy": False}


def parse_po(raw: str) -> list[Row]:
    """Parse gettext PO text into Row entries supporting plurals, fuzzy and msgctxt."""
    rows: list[Row] = []
    cur: dict[str, Any] | None = None
    pending_flags: list[str] = []
    pending_ctxt: str | None = None
    state: Any = None
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("#~"):
            _finalize_entry(cur, rows)
            cur, state = None, None
        elif s.startswith("#,"):
            pending_flags.extend(f.strip() for f in s[2:].split(","))
        elif s.startswith("msgctxt "):
            _finalize_entry(cur, rows)
            cur, pending_ctxt, state = None, _po_unescape(_po_quoted(s, r"msgctxt")), "ctxt"
        elif s.startswith("msgid_plural "):
            cur = _ensure_cur(cur, pending_ctxt)
            cur["plural"], state = _po_unescape(_po_quoted(s, r"msgid_plural")), "plural"
        elif s.startswith("msgid "):
            _finalize_entry(cur, rows)
            cur = {"msgid": _po_unescape(_po_quoted(s, r"msgid")), "plural": None, "msgstr": {},
                   "ctxt": pending_ctxt, "fuzzy": "fuzzy" in pending_flags}
            pending_flags, pending_ctxt, state = [], None, "msgid"
        elif s.startswith("msgstr"):
            cur = _ensure_cur(cur, pending_ctxt)
            m = re.match(r"msgstr(?:\[(\d+)\])?", s)
            idx = int(m.group(1)) if (m and m.group(1) is not None) else 0
            cur["msgstr"][idx] = _po_unescape(_po_quoted(s, r"msgstr(?:\[\d+\])?"))
            state = ("msgstr", idx)
        elif s.startswith('"'):
            frag = _po_unescape(_po_quoted(s, r""))
            if state == "ctxt":
                pending_ctxt = (pending_ctxt or "") + frag
            elif cur is not None and state == "msgid":
                cur["msgid"] += frag
            elif cur is not None and state == "plural":
                cur["plural"] = (cur["plural"] or "") + frag
            elif cur is not None and isinstance(state, tuple):
                cur["msgstr"][state[1]] = cur["msgstr"].get(state[1], "") + frag
    _finalize_entry(cur, rows)
    return rows


def po_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def export_po(final: dict[str, str], template: Path, out_dir: Path) -> dict[str, Any]:
    """Update msgstr entries in a PO template, clearing fuzzy when filled."""
    raw = read_text_bom(template)
    nl = "\r\n" if "\r\n" in raw else "\n"
    blocks = re.split(r"(?:\r?\n){2,}", raw.strip("\r\n"))
    placed, out_blocks = set(), []
    for block in blocks:
        rows = parse_po(block + nl)
        if not rows or not any(r.key in final for r in rows):
            out_blocks.append(block)
            continue
        lines = block.split(nl)
        first = next(i for i, ln in enumerate(lines) if ln.startswith("msgstr"))
        head = [ln for ln in (re.sub(r",\s*fuzzy\b", "", ln) if ln.startswith("#,") else ln for ln in lines[:first]) if ln.strip() != "#,"]
        if len(rows) > 1 or "|[" in rows[0].key:
            body = [f"msgstr[{idx}] {po_quote(final.get(r.key, r.dst))}" for idx, r in enumerate(rows)]
            placed.update(r.key for r in rows if r.key in final)
        else:
            body = [f"msgstr {po_quote(final.get(rows[0].key, rows[0].dst))}"]
            placed.add(rows[0].key)
        out_blocks.append(nl.join(head + body))
    (out_dir / template.name).write_bytes((nl + nl).join(out_blocks).encode("utf-8") + nl.encode("utf-8"))
    return {"files": [template.name], "placed": len(placed), "keys": placed}


class PoTableFormat:
    """TableFormatStrategy for .po files."""
    suffixes = (".po",)

    def read_rows(self, path: Path, options: TableLoadOptions) -> list[Row]:
        rows = parse_po(read_text_bom(path))
        return [Row(r.key, "", r.dst, r.meta) for r in rows] if options.target_only else rows

    def write_export(self, final_texts: dict[str, str], template: Path, out_dir: Path, *, dst_field: str, key_field: str) -> ExportResult:
        res = export_po(final_texts, template, out_dir)
        return ExportResult(tuple(res["files"]), int(res["placed"]), tuple(sorted(res["keys"])))
