#!/usr/bin/env python3
"""Multi-language anti-translationese & technical LQA linter (15 locales).

Checks every target string for:
  * [EMPTY] / [FUZZY] / [PLURAL_FORMS] / [UNTRANSLATED] completeness problems
  * [ENCODING] U+FFFD, mojibake, control characters
  * [PLACEHOLDER] parity for unity / unreal / godot / icu / printf / python styles
  * [RICH_TAG] parity + open/close structure for TMP / HTML / BBCode tags
  * [LEADING_SPACE] / [TRAILING_SPACE] / [TRAILING_NEWLINE] (with --strict-whitespace)
  * [FORBIDDEN_CHAR] / [SPACED_HYPHEN] project punctuation bans
  * [GLOSSARY] locked-term consistency (--glossary termbase.csv)
  * [<locale>:<RULE-ID>] data-driven locale rules from scripts/rules/<locale>.json
    (+ scripts/rules/custom/*.json and any --rules <dir>)

Input: JSON (list or map), CSV / TSV (delimiter sniffed), gettext PO, Unity
Localization StringTable .asset.  Exit codes: 0 clean, 1 findings
(ERR, or WARN with --fail-on-warn), 2 usage / input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    CANONICAL_LOCALES, DEFAULT_RULES_DIR, EXIT_FINDINGS, EXIT_OK, PLACEHOLDER_STYLES, PLURAL_FORMS, TAG_STYLES,
    GlossaryTerm, L10nError, Row, add_common_args, add_input_argument, resolve_input, compare_placeholders, compare_tags, emit_report,
    extract_placeholders, extract_tags, glossary_violations, load_config, load_glossary, load_json_data,
    load_table, normalize_locale, pick, run_main, __version__,
)

TOOL = "lqa_linter"
_MOJIBAKE_RE = re.compile(r"[ÃÂ][\u0080-\u00ff]|â€[\u0080-\u00ff\x9d\x9c\x9e\x99]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


RULE_CONTEXTS = ("any", "ui", "dialog", "player", "button")


class Rule(NamedTuple):
    id: str
    severity: str
    regex: re.Pattern
    message: str
    context: str        # any | ui | dialog | player | button
    skip_variants: tuple
    source: str


class Finding(NamedTuple):
    severity: str   # ERR | WARN
    code: str       # PLACEHOLDER, RICH_TAG, <RULE-ID> ...
    key: str
    message: str
    target: str

    def as_dict(self) -> Dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "key": self.key, "message": self.message, "target": self.target}


# --------------------------------------------------------------------------- #
# Rule loading
# --------------------------------------------------------------------------- #
_FLAG_MAP = {"i": re.IGNORECASE, "m": re.MULTILINE, "x": re.VERBOSE, "s": re.DOTALL}


def _compile_rule_file(path: Path, locale: str, variant: Optional[str]) -> List[Rule]:
    data = load_json_data(path)
    if not isinstance(data, dict) or "rules" not in data:
        raise L10nError(f"{path}: rule file must be an object with a 'rules' array")
    file_locale = data.get("locale")
    if file_locale is not None:
        try:
            if normalize_locale(str(file_locale))[0] != locale:
                return []
        except L10nError:
            raise L10nError(f"{path}: unknown 'locale' value {file_locale!r}")
    rules: List[Rule] = []
    for idx, raw in enumerate(data["rules"]):
        if not isinstance(raw, dict):
            raise L10nError(f"{path}: rule #{idx} is not an object")
        for req in ("id", "severity", "pattern", "message"):
            if req not in raw:
                raise L10nError(f"{path}: rule #{idx} ({raw.get('id', '?')}) is missing '{req}'")
        sev = str(raw["severity"]).upper()
        if sev not in ("ERR", "WARN"):
            raise L10nError(f"{path}: rule {raw['id']} has invalid severity {raw['severity']!r} (ERR|WARN)")
        flags = 0
        for ch in str(raw.get("flags", "")):
            if ch not in _FLAG_MAP:
                raise L10nError(f"{path}: rule {raw['id']} has unknown flag '{ch}' (i, m, x, s)")
            flags |= _FLAG_MAP[ch]
        try:
            rx = re.compile(str(raw["pattern"]), flags)
        except re.error as exc:
            raise L10nError(f"{path}: rule {raw['id']} has an invalid regex: {exc}")
        ctx = str(raw.get("context", "any"))
        if ctx not in RULE_CONTEXTS:
            raise L10nError(f"{path}: rule {raw['id']} has invalid context {ctx!r} ({'|'.join(RULE_CONTEXTS)})")
        skip = tuple(str(v).lower() for v in raw.get("skip_variants", []) or [])
        if variant and variant.lower() in skip:
            continue
        vsev = raw.get("variant_severity") or {}
        if not isinstance(vsev, dict):
            raise L10nError(f"{path}: rule {raw['id']}: 'variant_severity' must be an object like {{\"hk\": \"WARN\"}}")
        if variant and variant.lower() in {k.lower(): v for k, v in vsev.items()}:
            sev = str({k.lower(): v for k, v in vsev.items()}[variant.lower()]).upper()
            if sev not in ("ERR", "WARN"):
                raise L10nError(f"{path}: rule {raw['id']} variant_severity has invalid severity {sev!r}")
        rules.append(Rule(str(raw["id"]), sev, rx, str(raw["message"]), ctx, skip, path.name))
    return rules


def load_rules(locale: str, variant: Optional[str] = None, extra_dirs: Sequence[Path] = (), builtin_dir: Path = DEFAULT_RULES_DIR) -> List[Rule]:
    """Load built-in rules/<locale>.json, rules/custom/*.json and every *.json in extra_dirs (deterministic order)."""
    files: List[Path] = []
    builtin = builtin_dir / f"{locale}.json"
    if not builtin.is_file():
        raise L10nError(f"no built-in rule file for locale '{locale}' (expected {builtin})")
    files.append(builtin)
    custom_dir = builtin_dir / "custom"
    if custom_dir.is_dir():
        files.extend(sorted(p for p in custom_dir.glob("*.json") if p.name != "rules.schema.json"))
    for d in extra_dirs:
        d = Path(d)
        if d.is_file():
            files.append(d)
        elif d.is_dir():
            files.extend(sorted(p for p in d.glob("*.json") if p.name != "rules.schema.json"))
        else:
            raise L10nError(f"--rules path does not exist: {d}")
    rules: List[Rule] = []
    seen: Dict[str, str] = {}
    for f in files:
        for r in _compile_rule_file(f, locale, variant):
            if r.id in seen:
                raise L10nError(f"duplicate rule id '{r.id}' in {f.name} (already defined in {seen[r.id]})")
            seen[r.id] = f.name
            rules.append(r)
    return rules


# --------------------------------------------------------------------------- #
# Core lint
# --------------------------------------------------------------------------- #
class LintOptions(NamedTuple):
    locale: str
    placeholder_style: str = "auto"
    tag_style: str = "auto"
    placeholder_regex: Optional[re.Pattern] = None
    forbid_chars: str = ""
    forbid_spaced_hyphen: bool = False
    allow_spaced_hyphen_substr: Sequence[str] = ()
    strict_whitespace: bool = False
    glossary: Sequence[GlossaryTerm] = ()
    glossary_severity: str = "WARN"
    check_untranslated: bool = True


_UI_WORDS = ("ui", "button", "menu", "label", "tooltip", "hud", "toast", "warning", "tab", "badge", "prompt", "keybind")
_DIALOG_WORDS = ("dialog", "dialogue", "speech", "letter", "story", "npc", "bark", "cutscene", "mail", "news")


def row_contexts(key: str, meta: Dict[str, Any]) -> set:
    """Derive the context tags of a row from its metadata and key.

    'ui' / 'dialog' come from category/context/type fields; 'button' from a button
    category or a key containing BTN/BUTTON; 'player' from a truthy 'player' field,
    an 'audience'/'tags' value containing 'player', or category 'player'.
    """
    tags: set = set()
    values = []
    for k in ("category", "context", "type", "ui_type", "speaker_or_ui_type", "audience", "tags"):
        v = meta.get(k)
        if isinstance(v, (list, tuple)):
            values.extend(str(x).lower() for x in v)
        elif v not in (None, ""):
            values.append(str(v).lower())
    for v in values:
        parts = {p.strip() for p in re.split(r"[,;/|\s]+", v) if p.strip()}
        if parts & set(_UI_WORDS):
            tags.add("ui")
        if parts & set(_DIALOG_WORDS):
            tags.add("dialog")
        if "button" in parts:
            tags.add("button")
        if "player" in parts:
            tags.add("player")
    if meta.get("player") in (True, 1, "1", "true", "True", "yes"):
        tags.add("player")
    if re.search(r"(?i)(?:^|[_.])(?:btn|button)(?:$|[_.])", key):
        tags.update({"button", "ui"})
    return tags


def rule_applies(rule: "Rule", contexts: set) -> bool:
    """ui/dialog rules apply unless the row is tagged with the other context; player/button rules need an explicit tag."""
    if rule.context == "any":
        return True
    if rule.context in ("player", "button"):
        return rule.context in contexts
    if rule.context == "ui":
        return "ui" in contexts or "dialog" not in contexts
    return "dialog" in contexts or "ui" not in contexts


def _ignored_rules(meta: Dict[str, Any]) -> set:
    v = meta.get("lqa_ignore")
    if not v:
        return set()
    if isinstance(v, str):
        return {x.strip() for x in v.split(",") if x.strip()}
    return {str(x).strip() for x in v}


def lint_rows(rows: Sequence[Row], rules: Sequence[Rule], opt: LintOptions) -> List[Finding]:
    """Lint rows and return findings in input order (deterministic)."""
    findings: List[Finding] = []
    err = lambda code, key, msg, dst: findings.append(Finding("ERR", code, key, msg, dst))  # noqa: E731
    warn = lambda code, key, msg, dst: findings.append(Finding("WARN", code, key, msg, dst))  # noqa: E731
    expected_forms = PLURAL_FORMS.get(opt.locale)
    for row in rows:
        key, src, dst, meta = row.key, row.src, row.dst, row.meta
        if dst.strip() == "":
            if src.strip() != "" or meta.get("kv_map"):
                err("EMPTY", key, "target string is empty", dst)
            continue
        if meta.get("fuzzy"):
            warn("FUZZY", key, "PO entry is marked fuzzy (needs review before shipping)", dst)
        if expected_forms and meta.get("plural_index") == 0 and meta.get("plural_nforms", expected_forms) < expected_forms:
            warn("PLURAL_FORMS", key, f"only {meta.get('plural_nforms')} plural form(s), {opt.locale} needs {expected_forms}", dst)
        if "\ufffd" in dst:
            err("ENCODING", key, "replacement character U+FFFD found (decoding damage)", dst)
        if _MOJIBAKE_RE.search(dst):
            err("ENCODING", key, "mojibake sequence (double-encoded UTF-8 such as 'Ã¼' / 'â€™')", dst)
        if _CONTROL_RE.search(dst):
            err("CONTROL_CHAR", key, "control character inside the string", dst)
        for ch in opt.forbid_chars:
            if ch in dst:
                err("FORBIDDEN_CHAR", key, f"forbidden character {ch!r}", dst)
        if opt.forbid_spaced_hyphen and " - " in dst and not any(sub in dst for sub in opt.allow_spaced_hyphen_substr):
            err("SPACED_HYPHEN", key, "' - ' is forbidden by project rules", dst)
        if src != "":
            for problem in compare_placeholders(
                extract_placeholders(src, opt.placeholder_style, opt.placeholder_regex),
                extract_placeholders(dst, opt.placeholder_style, opt.placeholder_regex),
            ):
                err("PLACEHOLDER", key, problem, dst)
            for problem in compare_tags(extract_tags(src, opt.tag_style), extract_tags(dst, opt.tag_style)):
                err("RICH_TAG", key, problem, dst)
            if opt.strict_whitespace:
                lead_s = len(src) - len(src.lstrip(" \t\u00a0"))
                lead_d = len(dst) - len(dst.lstrip(" \t\u00a0"))
                if lead_s != lead_d:
                    err("LEADING_SPACE", key, f"leading whitespace src={src[:lead_s]!r} vs dst={dst[:lead_d]!r}", dst)
                core_s, core_d = src.rstrip("\r\n"), dst.rstrip("\r\n")
                trail_s = len(core_s) - len(core_s.rstrip(" \t\u00a0"))
                trail_d = len(core_d) - len(core_d.rstrip(" \t\u00a0"))
                if trail_s != trail_d:
                    err("TRAILING_SPACE", key, f"trailing whitespace src={core_s[len(core_s)-trail_s:]!r} vs dst={core_d[len(core_d)-trail_d:]!r}", dst)
                if (len(src) - len(core_s)) != (len(dst) - len(core_d)):
                    err("TRAILING_NEWLINE", key, "trailing newline parity differs from source", dst)
            if opt.check_untranslated and opt.locale != "en" and src.strip() == dst.strip() and re.search(r"[A-Za-z]{3,}", src):
                warn("UNTRANSLATED", key, "target is identical to the source text", dst)
            if opt.glossary:
                for problem in glossary_violations(src, dst, opt.glossary):
                    findings.append(Finding(opt.glossary_severity, "GLOSSARY", key, problem, dst))
        contexts = row_contexts(key, meta)
        ignored = _ignored_rules(meta)
        for rule in rules:
            if not rule_applies(rule, contexts):
                continue
            if rule.id in ignored:
                continue
            if rule.regex.search(dst):
                findings.append(Finding(rule.severity, rule.id, key, rule.message, dst))
    return findings


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

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
        rules: List[Rule] = []
        seen: Dict[str, str] = {}
        for d in extra_dirs:
            paths = [d] if d.is_file() else sorted(d.glob("*.json")) if d.is_dir() else []
            if not paths and not d.exists():
                raise L10nError(f"--rules path does not exist: {d}")
            for f in paths:
                for r in _compile_rule_file(f, locale, variant):
                    if r.id in seen:
                        raise L10nError(f"duplicate rule id '{r.id}' in {f.name} (already defined in {seen[r.id]})")
                    seen[r.id] = f.name
                    rules.append(r)
    else:
        rules = load_rules(locale, variant, extra_dirs)

    glossary: List[GlossaryTerm] = []
    gl_path = pick(args.glossary, cfg, "glossary", None)
    if gl_path:
        glossary = load_glossary(Path(gl_path), locale)

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
