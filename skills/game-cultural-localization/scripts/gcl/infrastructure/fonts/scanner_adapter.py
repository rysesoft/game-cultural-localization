"""In process FontScannerPort implementation and report renderer."""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gcl.domain.errors import EXIT_FINDINGS, EXIT_OK, L10nError, __version__
from gcl.domain.locales import normalize_locale

from .font_chain import (
    CJK_LOCALES, FULL_WIDTH_EM, ChainEntry, ChainResult, FontChain, block_name, collect_target_chars, resolve_chars,
)

__layer__ = "infrastructure"
__pattern__ = "Port Adapter"
__owns__ = "in process DefaultFontScannerAdapter implementing FontScannerPort and text report formatting"


@dataclass(frozen=True, slots=True)
class FontScanOptions:
    """Options controlling glyph coverage, upper-case variants and full-width detection."""

    dst_field: str = "dst"
    locale: str | None = None
    full_width_check: str = "auto"
    full_width_em: float = FULL_WIDTH_EM
    strict: bool = False
    also_upper: bool = False
    placeholder_style: str = "auto"
    tool_name: str = "font_glyph_scanner"


@dataclass(frozen=True, slots=True)
class FontScanRun:
    """Completed glyph scan bundle holding machine JSON payload and display metadata."""

    payload: dict[str, Any]
    order: tuple[ChainEntry, ...]
    used: dict[int, tuple[str, str, int]]
    result: ChainResult
    served_count: tuple[int, ...]
    served_chars: tuple[tuple[str, ...], ...]
    locale: str | None
    full_width_mode: str
    check_wide: bool
    lenient: bool
    level: str


def resolve_scan_locale(explicit: str | None, dst_field: str) -> str | None:
    if explicit:
        return normalize_locale(explicit)[0]
    try:
        return normalize_locale(dst_field)[0]
    except L10nError:
        return None


def scan_font_coverage(input_path: Path, fonts: Sequence[Path], opts: FontScanOptions) -> FontScanRun:
    """Execute complete glyph coverage and full-width fallback analysis in process."""
    locale = resolve_scan_locale(opts.locale, opts.dst_field)
    check_wide = opts.full_width_check == "on" or (opts.full_width_check == "auto" and locale not in CJK_LOCALES)
    chain = FontChain()
    roots = [chain.load(Path(fp)) for fp in fonts]
    order = tuple(chain.search_order(roots))
    used = collect_target_chars(Path(input_path), opts.dst_field, opts.also_upper, opts.placeholder_style)
    result = resolve_chars(list(order), used, check_wide, opts.full_width_em)
    missing = result.missing
    lenient = (not opts.strict) and any(not e.font.info.coverage_known for e in order)
    exit_code = EXIT_FINDINGS if ((missing and not lenient) or result.full_width) else EXIT_OK
    level = "WARN" if lenient else "ERR"
    warnings = [(e.font, code, msg) for e in order for code, msg in e.font.notes]
    served_count = [0] * len(order)
    served_chars: list[list[str]] = [[] for _ in order]
    for cp, idx in result.served.items():
        if idx is not None:
            served_count[idx] += 1
            served_chars[idx].append(used[cp][0])
    font_rows = []
    for n, e in enumerate(order):
        entry = e.font.info._replace(fallback_of=str(e.parent.path) if e.parent is not None else None)._asdict()
        entry["served"] = served_count[n]
        font_rows.append(entry)
    payload = {
        "tool": opts.tool_name, "version": __version__, "input": str(input_path),
        "fonts": font_rows, "lenient": lenient, "locale": locale, "full_width_checked": check_wide,
        "unique_chars": len(used),
        "summary": {"missing": len(missing), "severity": level, "full_width": len(result.full_width), "warnings": len(warnings)},
        "missing": [{"codepoint": f"U+{cp:04X}", "char": used[cp][0], "name": unicodedata.name(used[cp][0], "UNKNOWN"),
                     "count": used[cp][2], "first_key": used[cp][1]} for cp in missing],
        "full_width": [{"codepoint": f"U+{cp:04X}", "char": used[cp][0], "name": unicodedata.name(used[cp][0], "UNKNOWN"),
                        "count": used[cp][2], "first_key": used[cp][1], "font": str(order[idx].font.path), "advance_em": round(em, 3)}
                       for cp, idx, em in result.full_width],
        "chars": [{"codepoint": f"U+{cp:04X}", "char": used[cp][0], "count": used[cp][2], "first_key": used[cp][1],
                   "font": str(order[idx].font.path) if idx is not None else None} for cp, idx in result.served.items()],
        "warnings": [{"font": str(font.path), "code": code, "message": msg} for font, code, msg in warnings],
        "exit_code": exit_code,
    }
    return FontScanRun(
        payload, order, used, result, tuple(served_count), tuple(tuple(c) for c in served_chars),
        locale, opts.full_width_check, check_wide, lenient, level,
    )


def _cut(items: Sequence[Any], limit: int | None) -> Sequence[Any]:
    return items if limit is None else items[:limit]


def _sample(chars: Sequence[str], limit: int = 60) -> str:
    text = "".join(chars)
    return text if len(text) <= limit else text[:limit] + " ..."


def format_font_report(run: FontScanRun, limit: int | None = None) -> str:
    """Render human readable text report from completed FontScanRun."""
    lines = ["Font Coverage Report:", "  Search order (the first --font is the primary, a TMP asset's own fallback table comes before the next --font)"]
    for n, e in enumerate(run.order):
        i = e.font.info
        desc = [i.kind] + ([f"{i.sub_fonts} sub-fonts"] if i.kind == "ttc" else [])
        if i.kind == "tmp-asset":
            desc.append(("dynamic atlas" + (f" from {Path(i.source_font).name}" if i.source_font else "")) if i.dynamic else "static atlas")
        if e.parent is not None:
            desc.append(f"fallback of {e.parent.path.name}")
        lines.append(f"  {n + 1}. {'  ' * e.depth}{e.font.path.name}: {i.glyphs} code points ({', '.join(desc)}), serves {run.served_count[n]}")
    missing = run.result.missing
    lines.append(f"  Unique target characters used: {len(run.used)}")
    lines.append(f"  Missing characters (tofu)     : {len(missing)}" + (" [WARN, part of the font chain could not be resolved, pass --strict to fail]" if run.lenient and missing else ""))
    blocks: dict[str, int] = {}
    for cp in missing:
        b = block_name(run.used[cp][0])
        blocks[b] = blocks.get(b, 0) + 1
    for cp in _cut(missing, limit):
        ch, key, n = run.used[cp]
        lines.append(f"  {run.level} U+{cp:04X} {ch!r} {unicodedata.name(ch, 'UNKNOWN')} x{n}, first seen in '{key}'")
    if limit is not None and len(missing) > limit:
        lines.append(f"  ... and {len(missing) - limit} more (raise --max-report or use --json).")
    if blocks:
        lines.append("  By script/block: " + ", ".join(f"{b}: {n}" for b, n in sorted(blocks.items())))
    _append_wide_and_warnings(lines, run, limit)
    lines.append(f"  Exit code: {run.payload['exit_code']}")
    return "\n".join(lines)


def _append_wide_and_warnings(lines: list[str], run: FontScanRun, limit: int | None) -> None:
    if run.check_wide:
        lines.append(f"  Full width fallbacks          : {len(run.result.full_width)}")
        for cp, idx, em in _cut(run.result.full_width, limit):
            ch, key, n = run.used[cp]
            lines.append(f"  WIDE U+{cp:04X} {ch!r} {unicodedata.name(ch, 'UNKNOWN')} x{n}, {em:.2f} em in {run.order[idx].font.path.name} which the primary font lacks, first seen in '{key}'")
        if limit is not None and len(run.result.full_width) > limit:
            lines.append(f"  ... and {len(run.result.full_width) - limit} more (raise --max-report or use --json).")
    else:
        reason = "--full-width-check off" if run.full_width_mode == "off" else str(run.locale)
        lines.append(f"  Full width fallbacks          : not checked ({reason})")
    for n, e in enumerate(run.order):
        if n and run.served_chars[n]:
            lines.append(f"  Served by {e.font.path.name} ({run.served_count[n]}) {_sample(run.served_chars[n])}")
    warnings = [(e.font, code, msg) for e in run.order for code, msg in e.font.notes]
    if warnings:
        lines.append(f"  Font chain warnings           : {len(warnings)}")
        for font, code, msg in _cut(warnings, limit):
            lines.append(f"  WARN {font.path.name} {code}, {msg}")
        if limit is not None and len(warnings) > limit:
            lines.append(f"  ... and {len(warnings) - limit} more (raise --max-report or use --json).")


@dataclass(frozen=True, slots=True)
class DefaultFontScannerAdapter:
    """In process FontScannerPort adapter delegating to scan_font_coverage."""

    def scan(self, table_path: Path, dst_field: str, locale: str | None, fonts: Sequence[Path]) -> dict[str, Any]:
        run = scan_font_coverage(Path(table_path), fonts, FontScanOptions(dst_field=dst_field, locale=locale))
        return run.payload
