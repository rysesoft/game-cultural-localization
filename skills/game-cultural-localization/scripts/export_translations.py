#!/usr/bin/env python3
"""Final translations exporter CLI Facade delegating to TableFormatRegistry and export services.

Exit codes: 0 clean, 1 undecided lines / held back texts / unplaced keys, 2 usage error.
Python 3.15, standard library only.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcl.domain.errors import EXIT_FINDINGS, EXIT_OK, L10nError, __version__  # noqa: E402
from gcl.domain.locales import normalize_locale  # noqa: E402
from gcl.infrastructure.formats.cli_support import (  # noqa: E402
    add_common_args, add_input_argument, emit_report, resolve_input, run_main,
)
from gcl.infrastructure.formats.csv_format import export_csv  # noqa: E402,F401
from gcl.infrastructure.formats.export_decisions import (  # noqa: E402
    DECISIONS, apply_decisions, collect_inputs, dispatch_non_unity_export, hold_back_broken, load_finals,
)
from gcl.infrastructure.formats.io_utils import game_root  # noqa: E402
from gcl.infrastructure.formats.json_format import export_json  # noqa: E402,F401
from gcl.infrastructure.formats.po_format import export_po, po_quote  # noqa: E402,F401
from gcl.infrastructure.formats.project_config import apply_config  # noqa: E402
from gcl.infrastructure.formats.registry import DEFAULT_FORMAT_REGISTRY  # noqa: E402
from gcl.infrastructure.formats.unity_yaml_writer import (  # noqa: E402,F401
    assign_unity_keys, check_written, export_unity as _export_unity, shared_of, strict_dq, unity_rewrite as _unity_rewrite,
    unity_tables, yaml_dq,
)
from gcl.infrastructure.tokens.placeholders import PLACEHOLDER_STYLES  # noqa: E402
from gcl.infrastructure.tokens.rich_tags import TAG_STYLES  # noqa: E402

TOOL = "export_translations"
TEMPLATE_SUFFIXES = (".asset", ".csv", ".tsv", ".json", ".po")


def unity_rewrite(text: str, id_texts: dict[str, str], written: Any = None) -> str:
    return _unity_rewrite(text, id_texts, written, quote_fn=yaml_dq)


def export_unity(final: dict[str, str], templates: Any, shared_override: Any, out_dir: Path) -> dict[str, Any]:
    return _export_unity(final, templates, shared_override, out_dir, quote_fn=yaml_dq)


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


def _resolve_templates(ap: argparse.ArgumentParser, args: Any, locale: str) -> list[Path]:
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
    return templates


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    apply_config(args, {"placeholder_style": "auto", "tag_style": "auto"})
    locale, _v = normalize_locale(args.locale)
    templates = _resolve_templates(ap, args, locale)
    out_dir = Path(args.out)
    root = game_root(out_dir if out_dir.exists() else out_dir.parent)
    if root is not None:
        raise L10nError(f"--out {out_dir} lies inside the game project {root.name}, the export never writes into a game project")
    if any(out_dir.resolve() == t.resolve().parent for t in templates):
        raise L10nError("--out must not be the folder of a template, the export never overwrites the game's own files")
    finals, reports = collect_inputs(Path(args.input), locale, args.changes)
    sources: dict[str, str] = {}
    final = load_finals(finals, locale, args.dst_field, args.key_field, sources)
    decided = apply_decisions(final, reports)
    held = hold_back_broken(final, sources, args.placeholder_style, args.tag_style)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst_field = args.dst_field or locale
    unity = [t for t in templates if t.suffix.lower() == ".asset"]
    files: list[str] = []
    placed, unchanged, placed_keys = 0, 0, set()
    if unity:
        ures = export_unity(final, unity, Path(args.shared_table) if args.shared_table else None, out_dir)
        files += ures["files"]
        placed += ures["placed"]
        unchanged = ures["unchanged"]
        placed_keys |= set(final) - set(ures["not_placed"])
    f2, p2, k2 = dispatch_non_unity_export(DEFAULT_FORMAT_REGISTRY, templates, final, out_dir, dst_field=dst_field, key_field=args.key_field)
    files, placed, placed_keys = files + f2, placed + p2, placed_keys | k2
    not_placed = sorted(set(final) - placed_keys)
    exit_code = EXIT_FINDINGS if bool(decided["undecided"] or not_placed or held) else EXIT_OK
    lines = [
        f"Export {locale}: {len(final) + len(held)} final lines from {len(finals)} file(s), {len(reports)} change report(s)",
        f"  decisions accepted {decided['accepted']}, rejected {decided['rejected']}, changed lines without a decision {len(decided['undecided'])}",
        f"  placed {placed} texts, wrote {len(files)} file(s) with changes to {out_dir}: {', '.join(files) or 'none'}"
        + (f", {unchanged} Unity table(s) already hold every text and were not written" if unchanged else ""),
    ]
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
    payload = {
        "tool": TOOL, "version": __version__, "locale": locale, "files": files, "placed": placed, "unchanged_tables": unchanged,
        "accepted": decided["accepted"], "rejected": decided["rejected"], "undecided": decided["undecided"],
        "not_placed": not_placed, "held_back": held, "unknown_report_keys": decided["unknown"], "exit_code": exit_code,
    }
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
