"""JSON locale LQA rule compilation and directory loading."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from gcl.domain.errors import L10nError
from gcl.domain.lint_models import ROW_CONTEXTS, RULE_CONTEXTS, Rule
from gcl.domain.locales import normalize_locale
from gcl.infrastructure.paths import DEFAULT_RULES_DIR

from .io_utils import load_json_data

__layer__ = "infrastructure"
__pattern__ = "Rule Loader"
__owns__ = "parsing, compiling and deduplicating locale LQA JSON rule files"

_FLAG_MAP: Dict[str, int] = {"i": re.IGNORECASE, "m": re.MULTILINE, "x": re.VERBOSE, "s": re.DOTALL}


def _compile_rule_entry(raw: Any, idx: int, path: Path, variant: Optional[str]) -> Optional[Rule]:
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
        return None
    skip_ctx = raw.get("skip_contexts", []) or []
    if not isinstance(skip_ctx, list) or any(str(c) not in ROW_CONTEXTS for c in skip_ctx):
        raise L10nError(f"{path}: rule {raw['id']} has invalid skip_contexts {skip_ctx!r} (list of {'|'.join(ROW_CONTEXTS)})")
    vsev = raw.get("variant_severity") or {}
    if not isinstance(vsev, dict):
        raise L10nError(f"{path}: rule {raw['id']}: 'variant_severity' must be an object like {{\"hk\": \"WARN\"}}")
    if variant and variant.lower() in {k.lower(): v for k, v in vsev.items()}:
        sev = str({k.lower(): v for k, v in vsev.items()}[variant.lower()]).upper()
        if sev not in ("ERR", "WARN"):
            raise L10nError(f"{path}: rule {raw['id']} variant_severity has invalid severity {sev!r}")
    return Rule(str(raw["id"]), sev, rx, str(raw["message"]), ctx, skip, path.name, tuple(str(c) for c in skip_ctx))


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
    out: List[Rule] = []
    for idx, raw in enumerate(data["rules"]):
        compiled = _compile_rule_entry(raw, idx, path, variant)
        if compiled is not None:
            out.append(compiled)
    return out


def compile_rule_files(files: Sequence[Path], locale: str, variant: Optional[str]) -> List[Rule]:
    rules: List[Rule] = []
    seen: Dict[str, str] = {}
    for f in files:
        for r in _compile_rule_file(f, locale, variant):
            if r.id in seen:
                raise L10nError(f"duplicate rule id '{r.id}' in {f.name} (already defined in {seen[r.id]})")
            seen[r.id] = f.name
            rules.append(r)
    return rules


def load_rules(
    locale: str,
    variant: Optional[str] = None,
    extra_dirs: Sequence[Path] = (),
    builtin_dir: Path = DEFAULT_RULES_DIR,
) -> List[Rule]:
    """Load built in rules/<locale>.json, rules/custom/*.json and extra directories."""
    builtin = builtin_dir / f"{locale}.json"
    if not builtin.is_file():
        raise L10nError(f"no built-in rule file for locale '{locale}' (expected {builtin})")
    files: List[Path] = [builtin]
    custom_dir = builtin_dir / "custom"
    if custom_dir.is_dir():
        files.extend(sorted(p for p in custom_dir.glob("*.json") if p.name != "rules.schema.json"))
    for d in extra_dirs:
        p = Path(d)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(x for x in p.glob("*.json") if x.name != "rules.schema.json"))
        else:
            raise L10nError(f"--rules path does not exist: {p}")
    return compile_rule_files(files, locale, variant)
