#!/usr/bin/env python3
"""Font missing-glyph ('tofu' box) and full width fallback scanner CLI facade.

Delegates font parsing, Unity TMP fallback chains and coverage scanning to gcl.infrastructure.fonts.
Pure Python 3.15, standard library only. Exit codes: 0 ok, 1 findings, 2 bad input.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcl.infrastructure.fonts import (  # noqa: E402
    CJK_LOCALES, FULL_WIDTH_EM, ChainEntry, ChainFont, ChainResult, FontChain, FontInfo, FontParseError,
    FontScanOptions, SfntFace, SfntFont, TmpAssetData, block_name as _block_name, cmap_glyph_id,
    collect_target_chars, find_assets_dir, format_font_report, guid_index, load_font_file, parse_cmap_table,
    parse_font_file, parse_tmp_asset, read_tmp_asset, resolve_chars, scan_font_coverage,
)
from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, emit_report, load_config, pick,
    resolve_input, run_main,
)

TOOL = "font_glyph_scanner"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog=TOOL,
        description="Scan localized strings for glyphs missing from a font chain of TTF/OTF/TTC/WOFF fonts "
                    "and Unity TMP FontAssets, and for marks that fall back to a full width glyph (exit 0 ok, 1 findings, 2 bad input)",
    )
    add_input_argument(ap, "Localized JSON, CSV/TSV, PO, Unity .asset string table, or plain text file")
    ap.add_argument("--dst-field", default=None, help="Target text column (default: dst)")
    ap.add_argument(
        "--font", action="append", required=True,
        help="Font file, .ttf, .otf, .ttc, .woff or a Unity TMP FontAsset .asset. Repeatable, the order is the fallback order "
             "and the first font is the primary. A TMP asset brings its own fallback table along",
    )
    ap.add_argument(
        "--locale", default=None,
        help="Target locale. The full width check is skipped for ja-JP, ko-KR, zh-CN and zh-Hant. "
             "Without it a --dst-field that names a locale counts",
    )
    ap.add_argument(
        "--full-width-check", choices=("auto", "on", "off"), default="auto",
        help="auto checks every locale except the CJK ones, on checks any locale, off never checks (default auto)",
    )
    ap.add_argument(
        "--full-width-em", type=float, default=FULL_WIDTH_EM,
        help=f"Advance, as a fraction of the em, from which a fallback glyph counts as full width (default {FULL_WIDTH_EM})",
    )
    ap.add_argument("--strict", action="store_true", help="Treat missing glyphs as ERR even when part of the font chain could not be resolved")
    ap.add_argument("--also-upper", action="store_true", help="Also scan the upper-cased text (runtime .ToUpper() / <uppercase> buttons)")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    if not args.full_width_em > 0:
        ap.error("--full-width-em must be greater than 0")
    cfg = load_config(Path(args.config)) if args.config else {}
    opts = FontScanOptions(
        dst_field=pick(args.dst_field, cfg, "dst_field", "dst"),
        locale=args.locale,
        full_width_check=args.full_width_check,
        full_width_em=args.full_width_em,
        strict=args.strict,
        also_upper=args.also_upper,
        placeholder_style=pick(None, cfg, "placeholder_style", "auto"),
        tool_name=TOOL,
    )
    run = scan_font_coverage(Path(args.input), [Path(fp) for fp in args.font], opts)
    emit_report(format_font_report(run, args.max_report), run.payload, args.json, args.output)
    return int(run.payload["exit_code"])


if __name__ == "__main__":
    run_main(main)
