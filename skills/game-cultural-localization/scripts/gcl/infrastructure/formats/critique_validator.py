"""Critique schema validator and CritiqueValidatorPort adapter."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from gcl.domain.errors import L10nError
from gcl.domain.locales import normalize_locale
from gcl.infrastructure.tokens.placeholders import compare_placeholders, extract_placeholders
from gcl.infrastructure.tokens.rich_tags import compare_tags, extract_tags, parity_problems
from gcl.ports.formats import TableLoadOptions

from .io_utils import load_json_data
from .registry import load_table_options

__layer__ = "infrastructure"
__pattern__ = "Validator and Port Adapter"
__owns__ = "critique schema checking, slice loading and CritiqueValidatorPort implementation"

ISSUE_TYPES: Tuple[str, ...] = (
    "translationese", "register", "tense", "regional_leak", "gender_leak",
    "ui_verb", "placeholder_grammar", "terminology", "other",
)


@dataclass(frozen=True)
class CritiqueValidationContext:
    """Context passed to entry and summary validators."""

    slice_targets: Optional[Dict[str, str]]
    ph_style: str
    tag_style: str
    sources: Optional[Dict[str, str]] = None


def load_slice_targets(path: Path) -> Dict[str, str]:
    """Load key -> target from a blind slice JSON or table."""
    if path.suffix.lower() == ".json":
        data = load_json_data(path)
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return {str(e["key"]): str(e.get("target", "")) for e in data["entries"] if isinstance(e, dict) and "key" in e}
    rows = load_table_options(path, TableLoadOptions("en", "target", "key", target_only=True))
    return {r.key: r.dst for r in rows}


def _check_entry_tokens(key: str, it: Any, suggested: str, where: str, ctx: CritiqueValidationContext) -> List[str]:
    assert ctx.slice_targets is not None
    problems: List[str] = []
    original = ctx.slice_targets[key]
    source = (ctx.sources or {}).get(key) or ""
    if source.strip():
        problems.extend(f"{where}: suggested text breaks parity with the source line: {p}"
                        for p in parity_problems(source, suggested, ctx.ph_style, ctx.tag_style))
    else:
        for p in compare_placeholders(extract_placeholders(original, ctx.ph_style), extract_placeholders(suggested, ctx.ph_style)):
            if it != "placeholder_grammar":
                problems.append(f"{where}: suggested text breaks placeholder parity: {p}")
        for p in compare_tags(extract_tags(original, ctx.tag_style), extract_tags(suggested, ctx.tag_style)):
            problems.append(f"{where}: suggested text breaks tag parity: {p}")
    if suggested.strip() == original.strip():
        problems.append(f"{where}: suggested text is identical to the current target")
    return problems


def _validate_entry(e: Any, idx: int, seen: Set[str], ctx: CritiqueValidationContext) -> Tuple[List[str], int, int]:
    where = f"entries[{idx}]"
    if not isinstance(e, dict):
        return [f"{where}: must be an object"], 0, 0
    key = e.get("key")
    if not isinstance(key, str) or not key:
        return [f"{where}: 'key' must be a non-empty string"], 0, 0
    where = f"entries[{idx}] ({key})"
    probs: List[str] = [f"{where}: duplicate key"] if key in seen else []
    seen.add(key)
    flagged, critical = 0, 0
    score = e.get("score")
    if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
        probs.append(f"{where}: 'score' must be an integer 1-5")
    elif score == 5:
        probs.append(f"{where}: score 5 entries must not be listed (only score < 5)")
    else:
        flagged, critical = 1, (1 if score <= 2 else 0)
    it = e.get("issue_type")
    if it not in ISSUE_TYPES:
        probs.append(f"{where}: 'issue_type' {it!r} not in {ISSUE_TYPES}")
    if not isinstance(e.get("reason"), str) or not e.get("reason", "").strip():
        probs.append(f"{where}: 'reason' must be a non-empty string")
    suggested = e.get("suggested")
    if not isinstance(suggested, str):
        probs.append(f"{where}: 'suggested' must be a string")
        suggested = None
    if ctx.slice_targets is not None:
        if key not in ctx.slice_targets:
            probs.append(f"{where}: key not present in the blind slice")
        elif suggested is not None and suggested.strip():
            probs.extend(_check_entry_tokens(key, it, suggested, where, ctx))
    return probs, flagged, critical


def _validate_summary(summary: Any, flagged: int, critical: int, slice_targets: Optional[Dict[str, str]]) -> List[str]:
    if not isinstance(summary, dict):
        return ["'summary' must be an object"]
    probs: List[str] = []
    for k in ("total", "flagged", "critical"):
        v = summary.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            probs.append(f"summary.{k} must be a non-negative integer")
    if isinstance(summary.get("flagged"), int) and summary["flagged"] != flagged:
        probs.append(f"summary.flagged={summary['flagged']} but {flagged} entries are listed")
    if isinstance(summary.get("critical"), int) and summary["critical"] != critical:
        probs.append(f"summary.critical={summary['critical']} but {critical} entries have score <= 2")
    if isinstance(summary.get("total"), int) and isinstance(summary.get("flagged"), int) and summary["total"] < summary["flagged"]:
        probs.append("summary.total is smaller than summary.flagged")
    if slice_targets is not None and isinstance(summary.get("total"), int) and summary["total"] != len(slice_targets):
        probs.append(f"summary.total={summary['total']} but the blind slice has {len(slice_targets)} entries")
    return probs


def validate(
    data: Any,
    slice_targets: Optional[Dict[str, str]],
    ph_style: str,
    tag_style: str,
    locale_expected: Optional[str],
    sources: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Validate critique document against schema and optional slice/source token parity."""
    if not isinstance(data, dict):
        return ["top level must be a JSON object"]
    problems = [f"missing top-level field '{req}'" for req in ("locale", "source_file", "entries", "summary") if req not in data]
    if problems:
        return problems
    try:
        loc = normalize_locale(str(data["locale"]))[0]
        if locale_expected and loc != locale_expected:
            problems.append(f"locale '{data['locale']}' does not match expected '{locale_expected}'")
    except L10nError as exc:
        problems.append(str(exc))
    entries = data["entries"]
    if not isinstance(entries, list):
        return problems + ["'entries' must be a list"]
    ctx = CritiqueValidationContext(slice_targets, ph_style, tag_style, sources)
    seen: Set[str] = set()
    flagged, critical = 0, 0
    for idx, e in enumerate(entries):
        ep, fl, cr = _validate_entry(e, idx, seen, ctx)
        problems.extend(ep)
        flagged += fl
        critical += cr
    problems.extend(_validate_summary(data["summary"], flagged, critical, slice_targets))
    return problems


class DefaultCritiqueValidatorAdapter:
    """Implements CritiqueValidatorPort using canonical validate()."""

    def validate_single(
        self,
        *,
        locale: str,
        source_file: str,
        entry: Dict[str, Any],
        target_by_key: Dict[str, str],
        sources_by_key: Dict[str, str],
        ph_style: str,
        tag_style: str,
    ) -> List[str]:
        doc = {
            "locale": locale, "source_file": source_file, "entries": [entry],
            "summary": {"total": 1, "flagged": 1, "critical": 1 if entry["score"] <= 2 else 0},
        }
        return validate(doc, target_by_key, ph_style, tag_style, locale, sources=sources_by_key)
