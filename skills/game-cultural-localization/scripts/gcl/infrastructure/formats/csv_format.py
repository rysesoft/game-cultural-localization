"""CSV and TSV localization table Strategy implementation."""
from __future__ import annotations

import codecs
import csv
import io
from pathlib import Path
from typing import Any, Dict, List

from gcl.domain.errors import L10nError
from gcl.domain.models import Row
from gcl.ports.formats import ExportResult, TableLoadOptions

from .io_utils import as_str, check_columns, read_text_bom, sniff_delimiter

__layer__ = "infrastructure"
__pattern__ = "Strategy"
__owns__ = "CSV and TSV localization reading and BOM preserving export"


def export_csv(final: Dict[str, str], template: Path, dst_field: str, key_field: str, out_dir: Path) -> Dict[str, Any]:
    """Update dst_field column in CSV/TSV template keeping BOM, line endings and extra columns."""
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


class CsvTableFormat:
    """TableFormatStrategy for .csv and .tsv files."""
    suffixes = (".csv", ".tsv")

    def read_rows(self, path: Path, options: TableLoadOptions) -> List[Row]:
        req = {"target": options.dst_field} if options.target_only else {"source": options.src_field, "target": options.dst_field}
        raw = read_text_bom(path)
        if raw.strip() == "":
            raise L10nError(f"{path}: file is empty")
        delim = options.delimiter or sniff_delimiter(raw, path.suffix.lower())
        reader = csv.DictReader(raw.splitlines(keepends=True), delimiter=delim)
        fieldnames = [f.strip() for f in (reader.fieldnames or [])]
        reader.fieldnames = fieldnames
        check_columns(fieldnames, req, path)
        rows: List[Row] = []
        for idx, row in enumerate(reader):
            k = as_str(row.get(options.key_field)) or f"row_{idx}"
            rows.append(Row(k, "" if options.target_only else as_str(row.get(options.src_field)), as_str(row.get(options.dst_field)), dict(row)))
        return rows

    def write_export(self, final_texts: Dict[str, str], template: Path, out_dir: Path, *, dst_field: str, key_field: str) -> ExportResult:
        res = export_csv(final_texts, template, dst_field, key_field, out_dir)
        return ExportResult(tuple(res["files"]), int(res["placed"]), tuple(sorted(res["keys"])))
