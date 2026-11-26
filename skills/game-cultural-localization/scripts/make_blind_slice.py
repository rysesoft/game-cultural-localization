#!/usr/bin/env python3
"""Create a target-only "blind slice" for the native-ear critic.

The critic must never see the source language (Law 7 / Phase 2 of the
methodology).  This script copies ONLY key + optional context columns
(category, speaker, ...) + the target text into a new file.  The source column
is refused as a context column, and the output is re-checked so that no source
text leaks through.

Input:  JSON (list or map), CSV / TSV, gettext PO, Unity Localization .asset
Output: JSON list  [{"key": ..., "category": ..., "speaker": ..., "target": ...}]
        or CSV when --out ends with .csv / .tsv (same columns).

Usage:
  python make_blind_slice.py <input> --locale de-DE --out blind_de-DE_01.json
         [--key-col key] [--target-col de-DE] [--context-cols category,speaker]
         [--source-col en] [--max-rows N] [--skip-empty]

Exit codes: 0 slice written, 2 usage / input error (including a source leak).
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_OK, L10nError, add_common_args, add_input_argument, resolve_input, load_config, load_table, normalize_locale, pick, run_main, __version__,
)

TOOL = "make_blind_slice"
DEFAULT_CONTEXT_COLS = ("category", "speaker")
_RESERVED = {"target", "key"}


def build_slice(rows: List[Any], context_cols: List[str], source_col: str, skip_empty: bool, max_rows: int) -> List[Dict[str, Any]]:
    """Reduce loaded rows to key + context + target dictionaries (never the source)."""
    out: List[Dict[str, Any]] = []
    for row in rows:
        if skip_empty and not row.dst.strip():
            continue
        entry: Dict[str, Any] = {"key": row.key}
        for col in context_cols:
            val = row.meta.get(col)
            if val not in (None, ""):
                entry[col] = str(val)
        if row.meta.get("msgctxt"):
            entry.setdefault("msgctxt", row.meta["msgctxt"])
        if row.meta.get("plural_index") is not None:
            entry["plural_index"] = row.meta["plural_index"]
        entry["target"] = row.dst
        out.append(entry)
        if max_rows and len(out) >= max_rows:
            break
    return out


def verify_no_leak(entries: List[Dict[str, Any]], rows: List[Any], source_col: str) -> None:
    """Abort if any entry carries the source column or any entry value equals a non-trivial source text."""
    sources = {r.src for r in rows if r.src.strip() and len(r.src.strip()) > 2}
    for e in entries:
        if source_col in e:
            raise L10nError(f"blind slice would contain the source column '{source_col}' for key '{e['key']}'")
        for k, v in e.items():
            if k in ("key", "target", "plural_index"):
                continue
            if isinstance(v, str) and v in sources:
                raise L10nError(f"context column '{k}' of key '{e['key']}' contains source text; remove it from --context-cols")


def write_slice(entries: List[Dict[str, Any]], out: Path, locale: str, source_file: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() in (".csv", ".tsv"):
        cols: List[str] = ["key"]
        for e in entries:
            for k in e:
                if k not in cols and k != "target":
                    cols.append(k)
        cols.append("target")
        with out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t" if out.suffix.lower() == ".tsv" else ",", extrasaction="ignore")
            w.writeheader()
            for e in entries:
                w.writerow(e)
    else:
        payload = {"locale": locale, "source_file": source_file, "blind": True, "entries": entries}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Create a source-free blind slice (key + context + target) for the native-ear critic")
    add_input_argument(ap, "String table: JSON, CSV/TSV, PO, or Unity .asset")
    ap.add_argument("--locale", required=True, help="Target locale (recorded in the slice; also the default --target-col for multi-locale CSVs)")
    ap.add_argument("--out", required=True, help="Output path (.json, or .csv/.tsv for a flat table)")
    ap.add_argument("--key-col", default=None, help="Key column (default: key)")
    ap.add_argument("--target-col", default=None, help="Target text column (default: dst, or the locale code when such a column exists)")
    ap.add_argument("--source-col", default=None, help="Source column name, refused as context and used for the leak check (default: en)")
    ap.add_argument("--context-cols", default=",".join(DEFAULT_CONTEXT_COLS), help="Comma-separated context columns to keep (default: category,speaker)")
    ap.add_argument("--src-input", help="Unity .asset: not needed for a blind slice (ignored)")
    ap.add_argument("--shared-table", help="Unity .asset: SharedTableData used to resolve key names")
    ap.add_argument("--delimiter", default=None, help="CSV delimiter (default: sniffed)")
    ap.add_argument("--skip-empty", action="store_true", help="Drop rows whose target is empty")
    ap.add_argument("--max-rows", type=int, default=0, help="Stop after N rows (batching)")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    cfg = load_config(Path(args.config)) if args.config else {}
    locale, _variant = normalize_locale(args.locale)
    key_col = pick(args.key_col, cfg, "key_field", "key")
    source_col = pick(args.source_col, cfg, "src_field", "en")
    context_cols = [c.strip() for c in args.context_cols.split(",") if c.strip()]
    if source_col in context_cols:
        raise L10nError(f"'{source_col}' is the source column and cannot be a context column of a blind slice")
    for c in context_cols:
        if c in _RESERVED:
            raise L10nError(f"context column name '{c}' is reserved")
    path = Path(args.input)
    target_col = args.target_col or cfg.get("dst_field")
    if target_col is None:
        # Multi-locale tables (key,en,de-DE,fr...): prefer a column named after the locale.
        probe_rows: List[Any] = []
        for candidate in (args.locale, locale, "dst", "target", "text"):
            try:
                probe_rows = load_table(path, source_col, candidate, key_col, target_only=True,
                                        delimiter=pick(args.delimiter, cfg, "delimiter", None),
                                        shared_table=Path(args.shared_table) if args.shared_table else None)
                target_col = candidate
                break
            except L10nError:
                continue
        if target_col is None:
            raise L10nError(f"{path}: cannot find a target column; pass --target-col")
        rows = probe_rows
    else:
        rows = load_table(path, source_col, target_col, key_col, target_only=True,
                          delimiter=pick(args.delimiter, cfg, "delimiter", None),
                          shared_table=Path(args.shared_table) if args.shared_table else None)
    # Re-load with the source column only for the leak check (never written out).
    try:
        full_rows = load_table(path, source_col, target_col, key_col, delimiter=pick(args.delimiter, cfg, "delimiter", None),
                               shared_table=Path(args.shared_table) if args.shared_table else None)
    except L10nError:
        full_rows = rows
    entries = build_slice(rows, context_cols, source_col, args.skip_empty, args.max_rows)
    verify_no_leak(entries, full_rows, source_col)
    out = Path(args.out)
    write_slice(entries, out, locale, str(path))
    print(f"Blind slice written: {out} ({len(entries)} entries, locale {locale}, columns: key, {', '.join(c for c in context_cols)}, target)")
    return EXIT_OK


if __name__ == "__main__":
    run_main(main)
