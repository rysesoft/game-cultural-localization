#!/usr/bin/env python3
"""Context map facts CLI facade (Unity scan, slices, coverage check and juror leak audit).

Python 3.15, standard library only.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcl.application.context import (  # noqa: E402
    APPENDIX_HEADER, JUROR_FIELDS, JURY_MAP, JURY_NOTES, MAP_HEADER, WRITER_FIELDS,
    ContextPack, check_leak, load_context, render_summary, summary, target_only_words,
)
from gcl.infrastructure.unity_scan import (  # noqa: E402
    ASSET_EXTS, CODE_LINES_PER_FIELD, THIS, TRACE_NOTE, UNASSIGNED, USE_SITES_PER_KEY,
    _CsFile, _HOLE, _Str, _mask_cs, _render, build_slices, check_slices, find_unity_root,
    load_slice_spec, load_tables, locale_tables, object_paths, read_text, scan_unity,
    script_classes, table_texts, trace_uses,
)
from l10n_common import EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, emit_report, load_table, run_main, __version__  # noqa: E402

TOOL = "build_context_map"

__all__ = [
    "APPENDIX_HEADER", "ASSET_EXTS", "CODE_LINES_PER_FIELD", "ContextPack", "JUROR_FIELDS",
    "JURY_MAP", "JURY_NOTES", "MAP_HEADER", "THIS", "TRACE_NOTE", "TOOL", "UNASSIGNED",
    "USE_SITES_PER_KEY", "WRITER_FIELDS", "_CsFile", "_HOLE", "_Str", "_mask_cs", "_render",
    "build_parser", "build_slices", "check_leak", "check_slices", "find_unity_root", "load_context",
    "load_slice_spec", "load_tables", "locale_tables", "main", "object_paths", "read_text",
    "render_summary", "scan_unity", "script_classes", "summary", "table_texts",
    "target_only_words", "trace_uses",
]


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Context map facts. Where every localization key of a game project is used (Unity for now)")
    ap.add_argument("--scan", action="store_true", help="Scan the project and write key_usage.json and scan_summary.md")
    ap.add_argument("--slices", default=None, metavar="SPEC", help="Also write one scout input per slice to <out>/slices, SPEC is JSON {\"slice\": [\"TableName\", \"Table*\"]}")
    ap.add_argument("--source-locale", default="en", help="Locale of the source texts in the slice inputs (default en)")
    ap.add_argument("--locale", default=None, help="Target locale whose existing texts go into the slice inputs, for example tr-TR")
    ap.add_argument("--check-slices", action="store_true", help="Check that every key of <out>/slices/<slice>.input.json sits in exactly one entry of <slice>.report.json")
    ap.add_argument("--check-leak", action="store_true", help="Check the jurors' view of --context-map against an existing translation (--reference) for its words and quoted source lines")
    ap.add_argument("--context-map", default=None, help="CONTEXT_MAP.md for --check-leak (the jury files next to it are checked when present)")
    ap.add_argument("--reference", default=None, help="Existing translation with key, en and the --locale column, for --check-leak")
    ap.add_argument("--project", default=None, help="Game project folder (a Unity project or its Assets folder)")
    ap.add_argument("--out", default=None, help="Output folder, for example loc_work/context (never inside the game project)")
    ap.add_argument("--keys-from", default=None, help="String table whose keys must be covered (for example the studio reference), reports keys without a usage")
    ap.add_argument("--code-lines", type=int, default=CODE_LINES_PER_FIELD, help=f"Code lines kept per localized field (default {CODE_LINES_PER_FIELD})")
    ap.add_argument("--use-sites", type=int, default=USE_SITES_PER_KEY, help=f"Use sites kept per key by the heuristic use trace (default {USE_SITES_PER_KEY}, 0 turns the trace off)")
    add_common_args(ap, TOOL)
    return ap


def _check_main(args: argparse.Namespace, out: Path) -> int:
    res = check_slices(out / "slices")
    bad = {n: r for n, r in res.items() if not r["report"] or r["missing"] or r["duplicated"] or r["unknown"]}
    exit_code = EXIT_FINDINGS if bad else EXIT_OK
    lines = [
        f"Scout report coverage in {out / 'slices'}: {len(res)} slices, {sum(r['keys'] for r in res.values())} keys, "
        f"{sum(r['questions'] for r in res.values())} questions"
    ]
    for n, r in res.items():
        if not r["report"]:
            lines.append(f"  {n}: no report yet ({r['keys']} keys)")
        elif n in bad:
            first = ", ".join((r["missing"] + r["duplicated"] + r["unknown"])[:5])
            lines.append(f"  {n}: {len(r['missing'])} keys missing, {len(r['duplicated'])} in two entries, {len(r['unknown'])} not in the input (first {first})")
        else:
            lines.append(f"  {n}: {r['keys']} keys, each in exactly one entry")
    lines.append(f"  Exit code: {exit_code}")
    emit_report("\n".join(lines), {"tool": TOOL, "version": __version__, "slices": res, "exit_code": exit_code}, args.json, args.output)
    return exit_code


def _leak_main(args: argparse.Namespace) -> int:
    ref = Path(args.reference)
    if not ref.is_file():
        raise L10nError(f"--reference file not found: {ref}")
    rows = None
    for col in (args.locale, "dst", "target"):
        try:
            rows = load_table(ref, "en", col, "key")
            break
        except L10nError:
            continue
    if rows is None:
        raise L10nError(f"{ref}: no '{args.locale}' column")
    res = check_leak(load_context(Path(args.context_map), args.locale), rows)
    exit_code = EXIT_FINDINGS if res["words"] or res["quoted_source_lines"] else EXIT_OK
    lines = [
        f"Leak check of the jurors' view ({res['view']}) against {ref.name}: {res['notes']} line notes, "
        f"{res['notes_with_leaks']} with words of the existing translation, {len(res['words'])} distinct words, "
        f"{len(res['quoted_source_lines'])} quoted source lines"
    ]
    lines.extend(f"  {w} {n}x, first in {first}" for w, n, first in res["words"][:15])
    lines.append(f"  Exit code: {exit_code}")
    emit_report("\n".join(lines), {"tool": TOOL, "version": __version__, **res, "exit_code": exit_code}, args.json, args.output)
    return exit_code


def _scan_main(args: argparse.Namespace, out: Path) -> int:
    project = Path(args.project)
    if out.resolve().is_relative_to(project.resolve()):
        raise L10nError("--out must not be inside the game project, the scan never writes into it")
    if args.code_lines < 0:
        raise L10nError("--code-lines must be 0 or more")
    if args.use_sites < 0:
        raise L10nError("--use-sites must be 0 or more")
    spec = load_slice_spec(Path(args.slices)) if args.slices else None
    tables: dict[str, dict[str, Any]] = {}
    scan = scan_unity(project, args.code_lines, tables, args.use_sites)
    wanted, ref_meta = None, {}
    if args.keys_from:
        ref = Path(args.keys_from)
        if not ref.is_file():
            raise L10nError(f"--keys-from file not found: {ref}")
        ref_rows = load_table(ref, "en", "en", "key", target_only=True)
        wanted = [r.key for r in ref_rows]
        ref_meta = {r.key: r.meta for r in ref_rows}
    s = summary(scan, wanted)
    out.mkdir(parents=True, exist_ok=True)
    (out / "key_usage.json").write_text(json.dumps(scan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "scan_summary.md").write_text(render_summary(scan, s), encoding="utf-8")
    findings = bool(s.get("wanted_missing"))
    lines = [
        f"Context scan {scan['project']} ({scan['engine']}): {s['keys']} keys in {len(scan['tables'])} tables, {s['used']} with a usage",
        f"  code lines that glue texts together: {s['concat_lines']}",
        f"  references to a missing key: {s['dangling_references']}, to a missing table: {sum(s['missing_table_references'].values())}",
    ]
    if "with_uses" in s:
        lines.append(f"  use trace (heuristic, regex over {scan['use_trace']['code_files']} C# files): {s['with_uses']} keys with use sites, {len(s['loaded_not_shown'])} loaded but never shown")
    if wanted is not None:
        lines.append(f"  keys of {Path(args.keys_from).name}: {s['wanted']}, without a usage: {len(s['wanted_missing'])}")
    lines.append(f"  wrote {out / 'key_usage.json'} and {out / 'scan_summary.md'}")
    payload: dict[str, Any] = {"tool": TOOL, "version": __version__, "project": scan["project"], "summary": s}
    if spec is not None:
        slices, stats = build_slices(scan, tables, spec, args.source_locale, args.locale, ref_meta)
        sdir = out / "slices"
        sdir.mkdir(parents=True, exist_ok=True)
        for name, rows in slices.items():
            (sdir / f"{name}.input.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        findings = findings or bool(stats["unassigned_tables"] or stats["missing_locale_tables"])
        lines.append(f"  slices: {', '.join(f'{n} {c}' for n, c in stats['slices'].items())}, written to {sdir}")
        if stats["unassigned_tables"]:
            lines.append(f"  tables no slice claims, written to {UNASSIGNED}.input.json: {', '.join(stats['unassigned_tables'])}")
        if stats["missing_locale_tables"]:
            lines.append(f"  string tables not found for: {', '.join(stats['missing_locale_tables'][:10])}")
        payload["slices"] = stats
    exit_code = EXIT_FINDINGS if findings else EXIT_OK
    lines.append(f"  Exit code: {exit_code}")
    payload["exit_code"] = exit_code
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    modes = sum(1 for m in (args.scan or bool(args.slices), args.check_slices, args.check_leak) if m)
    if modes != 1:
        ap.error("choose one mode, --scan (optionally with --slices), --check-slices or --check-leak")
    if args.check_leak:
        if not (args.context_map and args.reference and args.locale):
            ap.error("--check-leak needs --context-map, --reference and --locale")
        return _leak_main(args)
    if not args.out:
        ap.error("--out is required")
    out = Path(args.out)
    if args.check_slices:
        return _check_main(args, out)
    if not args.project:
        ap.error("--scan and --slices need --project")
    return _scan_main(args, out)


if __name__ == "__main__":
    run_main(main)
