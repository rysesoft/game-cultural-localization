#!/usr/bin/env python3
"""UI button / tab / badge text-expansion overflow detector.

For every (source, target) pair the script estimates the rendered width of the
widest line (rich-text tags stripped, NFC-normalised, combining and zero-width
characters ignored, East-Asian Wide/Fullwidth glyphs weighted at --cjk-cell-width
(default 1.8, as documented in the CJK playbooks), Ambiguous-width glyphs
optionally weighted the same with --ambiguous-wide) and compares the ratio
target/source against a per-locale expansion ceiling.

Expansion ceilings (visual-width ratio vs. English). Sources: the §9 "Text
Expansion & UI Fit" section of each references/<locale>.md playbook, which in turn
follows the common industry tables (IBM globalization guidelines / W3C
"Text size in translation"): de +35 %, fr/es/pt/pl/lt/ru +30 %, it/tr +25 %;
CJK locales need fewer characters (ja 0.6-0.8, ko ~0.8, zh 0.5-0.7 of the
English character count) but each glyph is ~1.8 Latin cells wide, so the
visual ceilings are ja 1.3, ko 1.4, zh 1.1.

Short strings legitimately expand far more than long sentences (the IBM rule of
thumb), so the allowed ratio is  factor + max(0, (10 - source_width) / 10):
a 2-character "ON" may grow to ~2.15x in German, a 10+ character label only 1.35x;
sentences wider than 24 cells (they wrap rather than clip) get +0.1 tolerance.

Risk levels
  WARN  ratio > allowed * --warn-factor (default 1.0)   or more lines than the source
  HIGH  ratio > allowed * --high-factor (default 1.5)   or width > budget
        (budget = per-row max_chars / max_width / max_length metadata, a per-key or
        per-locale entry in the config "max_width" table, or the global --max-width)

Exit codes: 0 clean, 1 HIGH risks with --fail-on-high (or WARN with --fail-on-warn),
2 usage / input error.  Python 3.15, standard library only.
"""

import argparse
import sys
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    CANONICAL_LOCALES, EXIT_FINDINGS, EXIT_OK, TAG_STYLES, L10nError, Row, add_common_args, add_input_argument, resolve_input, emit_report,
    line_count, load_config, load_table, normalize_locale, pick, run_main, visual_width, __version__,
)

TOOL = "ui_expansion_checker"

EXPANSION_FACTORS: dict[str, float] = {
    "en": 1.00, "tr-TR": 1.25, "de-DE": 1.35, "fr": 1.30, "es-ES": 1.30, "it-IT": 1.25,
    "pt-BR": 1.30, "pt-PT": 1.30, "pl-PL": 1.30, "lt-LT": 1.30, "ru-RU": 1.30,
    "ja-JP": 1.30, "ko-KR": 1.40, "zh-CN": 1.10, "zh-Hant": 1.10,
}
DEFAULT_CJK_CELL = 1.8
_BUDGET_FIELDS = ("max_chars", "max_width", "max_length", "maxLength", "maxChars", "char_limit")


class Risk(NamedTuple):
    level: str
    key: str
    src: str
    dst: str
    src_width: float
    dst_width: float
    ratio: float
    allowed: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level, "key": self.key, "src": self.src, "dst": self.dst,
            "src_width": round(self.src_width, 2), "dst_width": round(self.dst_width, 2),
            "ratio": round(self.ratio, 3), "allowed": round(self.allowed, 3), "reason": self.reason,
        }


class CheckOptions(NamedTuple):
    locale: str
    factor: float
    warn_factor: float = 1.0
    high_factor: float = 1.5
    max_width: float | None = None
    width_table: dict[str, Any] | None = None
    cjk_cell: float = DEFAULT_CJK_CELL
    ambiguous_wide: bool = False
    tag_style: str = "auto"


def allowed_ratio(src_width: float, factor: float) -> float:
    """Locale ceiling plus a short-string bonus: factor + max(0, (10 - src_width) / 10).

    Sentences longer than 24 cells wrap instead of clipping, so they get an extra
    0.1 of tolerance (a 1.37x German tooltip is normal; a 2.4x one is not).
    """
    bonus = max(0.0, (10.0 - src_width) / 10.0)
    if src_width > 24:
        bonus += 0.1
    return factor + bonus


def _budget(row: Row, opt: CheckOptions) -> float | None:
    for f in _BUDGET_FIELDS:
        v = row.meta.get(f)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                raise L10nError(f"row '{row.key}': {f}={v!r} is not a number")
    table = opt.width_table or {}
    if row.key in table:
        return float(table[row.key])
    if opt.locale in table:
        return float(table[opt.locale])
    if "*" in table:
        return float(table["*"])
    return opt.max_width


def check_rows(rows: list[Row], opt: CheckOptions) -> list[Risk]:
    """Return expansion risks sorted by (level, ratio desc, key) - deterministic."""
    risks: list[Risk] = []
    for row in rows:
        src, dst = row.src, row.dst
        if not dst.strip():
            continue
        dw = visual_width(dst, opt.cjk_cell, opt.ambiguous_wide, opt.tag_style)
        budget = _budget(row, opt)
        if budget is not None and dw > budget:
            risks.append(Risk("HIGH", row.key, src, dst, visual_width(src, opt.cjk_cell, opt.ambiguous_wide, opt.tag_style) if src.strip() else 0.0, dw, 0.0, 0.0, f"width {dw:.0f} exceeds budget {budget:.0f}"))
            continue
        if not src.strip():
            continue  # target-only input: only budgets can be judged
        sw = visual_width(src, opt.cjk_cell, opt.ambiguous_wide, opt.tag_style)
        if sw <= 0:
            continue
        ratio = dw / sw
        allowed = allowed_ratio(sw, opt.factor)
        src_lines, dst_lines = line_count(src), line_count(dst)
        if dw - sw >= 2 and ratio > allowed * opt.high_factor and sw <= 40:
            risks.append(Risk("HIGH", row.key, src, dst, sw, dw, ratio, allowed, f"ratio {ratio:.2f}x > {allowed * opt.high_factor:.2f}x (HIGH threshold for {opt.locale})"))
        elif dw - sw >= 2 and ratio > allowed * opt.warn_factor:
            risks.append(Risk("WARN", row.key, src, dst, sw, dw, ratio, allowed, f"ratio {ratio:.2f}x > {allowed * opt.warn_factor:.2f}x (expected ceiling for {opt.locale})"))
        elif dst_lines > src_lines:
            risks.append(Risk("WARN", row.key, src, dst, sw, dw, ratio, allowed, f"{dst_lines} lines vs {src_lines} in source (vertical overflow)"))
    order = {"HIGH": 0, "WARN": 1}
    risks.sort(key=lambda r: (order[r.level], -r.ratio, -r.dst_width, r.key))
    return risks


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="UI button, tab & badge expansion-risk analyzer (exit 0 clean / 1 risks with --fail-on-high / 2 usage error)")
    add_input_argument(ap, "JSON, CSV/TSV, PO, or Unity .asset localization pairs")
    ap.add_argument("--locale", required=True, help="Target locale (" + ", ".join(CANONICAL_LOCALES) + "; aliases accepted)")
    ap.add_argument("--src-field", default=None, help="Source text column (default: en)")
    ap.add_argument("--dst-field", default=None, help="Target text column (default: dst)")
    ap.add_argument("--key-field", default=None, help="Key column (default: key)")
    ap.add_argument("--src-input", help="Unity .asset: source-locale StringTable to pair entries by m_Id")
    ap.add_argument("--shared-table", help="Unity .asset: SharedTableData to resolve key names")
    ap.add_argument("--delimiter", default=None, help="CSV delimiter (default: sniffed)")
    ap.add_argument("--factor", type=float, default=None, help="Override the locale expansion ceiling (e.g. 1.35)")
    ap.add_argument("--warn-factor", type=float, default=1.0, help="WARN when ratio > allowed * this (default 1.0)")
    ap.add_argument("--high-factor", type=float, default=1.5, help="HIGH when ratio > allowed * this (default 1.5)")
    ap.add_argument("--max-width", type=float, default=None, help="Global width budget in Latin cells; any target wider is HIGH")
    ap.add_argument("--cjk-cell-width", type=float, default=None, help="Width of a Wide/Fullwidth glyph in Latin cells (default 1.8)")
    ap.add_argument("--ambiguous-wide", action="store_true", default=None, help="Count East-Asian Ambiguous glyphs (… “ ” →) as wide (recommended for ja/ko/zh)")
    ap.add_argument("--tag-style", choices=TAG_STYLES, default=None, help="Rich-text tag syntax to strip (default auto)")
    ap.add_argument("--fail-on-high", action="store_true", help="Exit 1 if HIGH risks are found (recommended for CI gates)")
    ap.add_argument("--fail-on-warn", action="store_true", help="Exit 1 if any WARN or HIGH risk is found")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    cfg = load_config(Path(args.config)) if args.config else {}
    locale, _variant = normalize_locale(args.locale)
    factor = args.factor
    if factor is None:
        factor = float((cfg.get("expansion") or {}).get(locale, EXPANSION_FACTORS[locale]))
    if factor <= 0:
        raise L10nError("--factor must be positive")
    tag_style = pick(args.tag_style, cfg, "tag_style", "auto")
    if tag_style not in TAG_STYLES:
        raise L10nError(f"tag_style '{tag_style}' is invalid")
    width_cfg = cfg.get("max_width")
    width_table = width_cfg if isinstance(width_cfg, dict) else None
    max_width = args.max_width if args.max_width is not None else (float(width_cfg) if isinstance(width_cfg, (int, float)) and not isinstance(width_cfg, bool) else None)
    if locale in ("ja-JP", "ko-KR", "zh-CN", "zh-Hant") and args.ambiguous_wide is None and "ambiguous_wide" not in cfg:
        ambiguous_wide = True  # CJK fonts render Ambiguous glyphs full-width
    else:
        ambiguous_wide = bool(pick(args.ambiguous_wide, cfg, "ambiguous_wide", False))
    opt = CheckOptions(
        locale=locale, factor=factor, warn_factor=args.warn_factor, high_factor=args.high_factor,
        max_width=max_width, width_table=width_table,
        cjk_cell=float(pick(args.cjk_cell_width, cfg, "cjk_cell_width", DEFAULT_CJK_CELL)),
        ambiguous_wide=ambiguous_wide, tag_style=tag_style,
    )
    rows = load_table(
        Path(args.input), pick(args.src_field, cfg, "src_field", "en"), pick(args.dst_field, cfg, "dst_field", "dst"),
        pick(args.key_field, cfg, "key_field", "key"), target_only=False if not args.input.lower().endswith((".asset", ".yaml", ".yml")) else True,
        delimiter=pick(args.delimiter, cfg, "delimiter", None),
        src_input=Path(args.src_input) if args.src_input else None,
        shared_table=Path(args.shared_table) if args.shared_table else None,
    )
    risks = check_rows(rows, opt)
    high = [r for r in risks if r.level == "HIGH"]
    warn = [r for r in risks if r.level == "WARN"]
    exit_code = EXIT_FINDINGS if (args.fail_on_high and high) or (args.fail_on_warn and risks) else EXIT_OK

    lines = [
        f"UI Expansion Analysis ({locale}, factor {factor:.2f}, CJK cell {opt.cjk_cell}, ambiguous_wide={ambiguous_wide}): {len(rows)} entries",
        f"  HIGH clipping risks : {len(high)}",
        f"  WARN expansion risks: {len(warn)}",
    ]
    limit = args.max_report if args.max_report is not None else len(risks)
    for label, group in (("HIGH", high), ("WARN", warn)):
        for r in group[:limit]:
            lines.append(f"  [{label} {r.ratio:4.2f}x | {r.src_width:.0f}->{r.dst_width:.0f}] {r.key}: {r.src!r} -> {r.dst!r} ({r.reason})")
        if len(group) > limit:
            lines.append(f"  ... and {len(group) - limit} more {label} risks (raise --max-report or use --json).")
    if not args.fail_on_high and high:
        lines.append("  NOTE: HIGH risks found but --fail-on-high not given; exit code stays 0.")
    lines.append(f"  Exit code: {exit_code}")
    payload = {
        "tool": TOOL, "version": __version__, "locale": locale, "factor": factor, "cjk_cell_width": opt.cjk_cell,
        "ambiguous_wide": ambiguous_wide, "input": str(args.input), "entries_checked": len(rows),
        "summary": {"high": len(high), "warn": len(warn)}, "risks": [r.as_dict() for r in risks], "exit_code": exit_code,
    }
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
