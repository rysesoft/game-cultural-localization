"""JSON localization table Strategy implementation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from gcl.domain.errors import L10nError
from gcl.domain.models import Row
from gcl.ports.formats import ExportResult, TableLoadOptions

from .io_utils import as_str, check_columns, load_json_data

__layer__ = "infrastructure"
__pattern__ = "Strategy"
__owns__ = "JSON list and map localization table reading and exporting"


def _rows_from_list(data: List[Any], path: Path, opt: TableLoadOptions, req: Dict[str, str]) -> List[Row]:
    keys: set = set()
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise L10nError(f"{path}: item #{idx} is {type(item).__name__}, expected an object with '{opt.key_field}'/'{opt.dst_field}' fields")
        keys.update(item.keys())
    if data:
        check_columns(keys, req, path)
    rows: List[Row] = []
    for idx, item in enumerate(data):
        k = as_str(item.get(opt.key_field) or item.get("id") or f"row_{idx}")
        table = as_str(item.get("table"))
        label = f"{table}:{k}" if table else k
        rows.append(Row(label, "" if opt.target_only else as_str(item.get(opt.src_field)), as_str(item.get(opt.dst_field)), dict(item)))
    return rows


def _rows_from_dict(data: Dict[str, Any], path: Path, opt: TableLoadOptions, req: Dict[str, str]) -> List[Row]:
    dict_values = [v for v in data.values() if isinstance(v, dict)]
    if dict_values:
        keys: set = set()
        for v in dict_values:
            keys.update(v.keys())
        check_columns(keys, req, path)
    rows: List[Row] = []
    for k, v in data.items():
        if isinstance(v, dict):
            rows.append(Row(str(k), "" if opt.target_only else as_str(v.get(opt.src_field)), as_str(v.get(opt.dst_field)), dict(v)))
        elif isinstance(v, (str, int, float)) or v is None:
            rows.append(Row(str(k), "", as_str(v), {"kv_map": True}))
        else:
            raise L10nError(f"{path}: value of '{k}' is {type(v).__name__}; expected string or object")
    return rows


def export_json(final: Dict[str, str], template: Path, dst_field: str, key_field: str, out_dir: Path) -> Dict[str, Any]:
    """Write final texts into a JSON list or map template under out_dir."""
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


class JsonTableFormat:
    """TableFormatStrategy for .json files."""
    suffixes = (".json",)

    def read_rows(self, path: Path, options: TableLoadOptions) -> List[Row]:
        req = {"target": options.dst_field} if options.target_only else {"source": options.src_field, "target": options.dst_field}
        data = load_json_data(path)
        if isinstance(data, list):
            return _rows_from_list(data, path, options, req)
        if isinstance(data, dict):
            return _rows_from_dict(data, path, options, req)
        raise L10nError(f"{path}: top-level JSON must be a list or an object, got {type(data).__name__}")

    def write_export(self, final_texts: Dict[str, str], template: Path, out_dir: Path, *, dst_field: str, key_field: str) -> ExportResult:
        res = export_json(final_texts, template, dst_field, key_field, out_dir)
        return ExportResult(tuple(res["files"]), int(res["placed"]), tuple(sorted(res["keys"])))
