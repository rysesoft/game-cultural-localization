#!/usr/bin/env python3
"""Multi-language LQA linter CLI facade delegating to gcl.application.gates and gcl.infrastructure."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcl.application.gates import LintOptions, ROW_CONTEXTS, RULE_CONTEXTS, Rule, row_contexts, rule_applies  # noqa: E402
from gcl.application.gates.lint_chain import _CONTROL_RE, _MOJIBAKE_RE, lint_rows as _lint_rows  # noqa: E402
from gcl.domain.models import Finding  # noqa: E402
from gcl.infrastructure.formats.lint_rules_io import (  # noqa: E402
    _FLAG_MAP, _compile_rule_file, compile_rule_files, load_rules,
)
from gcl.infrastructure.tokens.parity_adapter import DefaultTokenParityAdapter  # noqa: E402
from l10n_common import (  # noqa: E402
    CANONICAL_LOCALES, DEFAULT_RULES_DIR, EXIT_FINDINGS, EXIT_OK, PLACEHOLDER_STYLES, PLURAL_FORMS, TAG_STYLES,
    GlossaryTerm, L10nError, Row, add_common_args, add_input_argument, emit_report, load_config, load_glossary,
    load_table, normalize_locale, pick, resolve_input, run_main, __version__,
)

TOOL = "lqa_linter"
_PARITY = DefaultTokenParityAdapter()


def lint_rows(rows: Sequence[Row], rules: Sequence[Rule], opt: LintOptions) -> List[Finding]:
    """Lint rows via Chain of Responsibility and return findings in input order."""
    return _lint_rows(rows, rules, opt, _PARITY)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Multi-language game culturalization & technical LQA linter (exit 0 clean / 1 findings / 2 usage error)")
    add_input_argument(ap, "JSON, CSV, TSV, PO, or Unity Localization .asset string table")
    ap.add_argument("--locale", required=True, help="Target locale (" + ", ".join(CANONICAL_LOCALES) + "; aliases like de, pt_BR, zh-TW, zh-HK accepted)")
    ap.add_argument("--variant", help="Regional variant that relaxes some rules (e.g. 'hk' for zh-Hant; implied by zh-HK)")
    ap.add_argument("--src-field", default=None, help="Source text column (default: en)")
    ap.add_argument("--dst-field", default=None, help="Target text column (default: dst)")
    ap.add_argument("--key-field", default=None, help="Key column (default: key)")
    ap.add_argument("--target-only", action="store_true", help="Input has no source column (blind slices); parity checks are skipped")
    ap.add_argument("--src-input", help="Unity .asset: the source-locale StringTable used to pair entries by m_Id")
    ap.add_argument("--shared-table", help="Unity .asset: SharedTableData file used to resolve m_Id -> key names")
    ap.add_argument("--delimiter", default=None, help="CSV delimiter (default: sniffed among , ; tab |)")
    ap.add_argument("--placeholder-style", choices=PLACEHOLDER_STYLES, default=None, help="Placeholder syntax (default: auto = braces + printf)")
    ap.add_argument("--placeholder-regex", default=None, help="Extra regex for project-specific placeholders, e.g. '\\$\\w+\\$' or '\\[[A-Z_]+\\]'")
    ap.add_argument("--tag-style", choices=TAG_STYLES, default=None, help="Rich-text tag syntax (default: auto = angle tags + known BBCode)")
    ap.add_argument("--rules", action="append", default=[], metavar="DIR_OR_FILE", help="Extra rule file/directory (repeatable)")
    ap.add_argument("--no-builtin-rules", action="store_true", help="Skip the bundled locale rules (only --rules files)")
    ap.add_argument("--glossary", default=None, help="Termbase CSV (term_en,<locale>,notes or source,target[,locale])")
    ap.add_argument("--glossary-severity", choices=("ERR", "WARN"), default=None, help="Severity of [GLOSSARY] findings (default WARN)")
    ap.add_argument("--forbid-chars", default=None, help="Characters strictly forbidden in target text, e.g. ';—–'")
    ap.add_argument("--forbid-spaced-hyphen", action="store_true", default=None, help="Forbid ' - ' in target strings")
    ap.add_argument("--allow-spaced-hyphen-substr", action="append", default=[], help="Substring that makes ' - ' acceptable (repeatable)")
    ap.add_argument("--strict-whitespace", action="store_true", default=None, help="Enforce leading/trailing whitespace and trailing-newline parity")
    ap.add_argument("--no-untranslated-check", action="store_true", help="Do not warn when target == source")
    ap.add_argument("--fail-on-error", action="store_true", help="Exit 1 on ERR findings (this is the default; flag accepted for explicit runbooks)")
    ap.add_argument("--fail-on-warn", action="store_true", default=None, help="Also exit 1 when only WARN findings exist")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    cfg = load_config(Path(args.config)) if args.config else {}
    locale, variant = normalize_locale(args.locale)
    variant = args.variant or pick(None, cfg, "variant", None) or variant
    if cfg.get("locales") and locale not in [normalize_locale(l)[0] for l in cfg["locales"]]:
        raise L10nError(f"locale '{locale}' is not in the project's configured locales {cfg['locales']}")

    src_field = pick(args.src_field, cfg, "src_field", "en")
    dst_field = pick(args.dst_field, cfg, "dst_field", "dst")
    key_field = pick(args.key_field, cfg, "key_field", "key")
    ph_style = pick(args.placeholder_style, cfg, "placeholder_style", "auto")
    tag_style = pick(args.tag_style, cfg, "tag_style", "auto")
    if ph_style not in PLACEHOLDER_STYLES:
        raise L10nError(f"placeholder_style '{ph_style}' is invalid; choose from {', '.join(PLACEHOLDER_STYLES)}")
    if tag_style not in TAG_STYLES:
        raise L10nError(f"tag_style '{tag_style}' is invalid; choose from {', '.join(TAG_STYLES)}")
    ph_regex_src = pick(args.placeholder_regex, cfg, "placeholder_regex", None)
    ph_regex = None
    if ph_regex_src:
        try:
            ph_regex = re.compile(ph_regex_src)
        except re.error as exc:
            raise L10nError(f"--placeholder-regex is invalid: {exc}")

    rows = load_table(
        Path(args.input), src_field, dst_field, key_field, target_only=args.target_only,
        delimiter=pick(args.delimiter, cfg, "delimiter", None),
        src_input=Path(args.src_input) if args.src_input else None,
        shared_table=Path(args.shared_table) if args.shared_table else None,
    )
    extra_dirs = [Path(p) for p in args.rules]
    cfg_rules = cfg.get("rules_dir")
    if cfg_rules:
        extra_dirs.append(Path(cfg_rules))
    if args.no_builtin_rules:
        custom_files: List[Path] = []
        for d in extra_dirs:
            paths = [d] if d.is_file() else sorted(d.glob("*.json")) if d.is_dir() else []
            if not paths and not d.exists():
                raise L10nError(f"--rules path does not exist: {d}")
            custom_files.extend(paths)
        rules = compile_rule_files(custom_files, locale, variant)
    else:
        rules = load_rules(locale, variant, extra_dirs)

    gl_path = pick(args.glossary, cfg, "glossary", None)
    glossary: List[GlossaryTerm] = load_glossary(Path(gl_path), locale) if gl_path else []

    opt = LintOptions(
        locale=locale, placeholder_style=ph_style, tag_style=tag_style, placeholder_regex=ph_regex,
        forbid_chars=pick(args.forbid_chars, cfg, "forbid_chars", ""),
        forbid_spaced_hyphen=bool(pick(args.forbid_spaced_hyphen, cfg, "forbid_spaced_hyphen", False)),
        allow_spaced_hyphen_substr=tuple(args.allow_spaced_hyphen_substr),
        strict_whitespace=bool(pick(args.strict_whitespace, cfg, "strict_whitespace", False)),
        glossary=glossary, glossary_severity=pick(args.glossary_severity, cfg, "glossary_severity", "WARN"),
        check_untranslated=not args.no_untranslated_check,
    )
    findings = lint_rows(rows, rules, opt)
    errors = [f for f in findings if f.severity == "ERR"]
    warnings = [f for f in findings if f.severity == "WARN"]
    fail_on_warn = bool(pick(args.fail_on_warn, cfg, "fail_on_warn", False))
    exit_code = EXIT_FINDINGS if errors or (fail_on_warn and warnings) else EXIT_OK

    lines = [
        f"LQA Linter checked {len(rows)} entries for locale '{locale}'" + (f" (variant {variant})" if variant else "") + f" with {len(rules)} rules.",
        f"  Errors  : {len(errors)}",
        f"  Warnings: {len(warnings)}",
    ]
    limit = args.max_report if args.max_report is not None else len(findings)
    for label, group in (("WARN", warnings), ("ERR ", errors)):
        for f in group[:limit]:
            lines.append(f"  {label}: [{f.code}] {f.key}: {f.message} -> {f.target[:110]!r}")
        if len(group) > limit:
            lines.append(f"  ... and {len(group) - limit} more {label.strip()} findings (raise --max-report or use --json).")
    lines.append(f"  Exit code: {exit_code}")
    payload = {
        "tool": TOOL, "version": __version__, "locale": locale, "variant": variant, "input": str(args.input),
        "entries_checked": len(rows), "rules_loaded": len(rules),
        "summary": {"errors": len(errors), "warnings": len(warnings)},
        "findings": [f.as_dict() for f in findings], "exit_code": exit_code,
    }
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
