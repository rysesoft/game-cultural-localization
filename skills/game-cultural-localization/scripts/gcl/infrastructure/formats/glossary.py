"""Termbase CSV glossary compilation and violation checking."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Sequence

from gcl.domain.errors import L10nError
from gcl.domain.locales import normalize_locale
from gcl.domain.models import GlossaryTerm

from .io_utils import as_str, read_text_bom, sniff_delimiter

__layer__ = "infrastructure"
__pattern__ = "Repository Helper"
__owns__ = "loading wide or long glossary CSVs and validating term consistency"

_FORBIDDEN_NOTE_RE = re.compile(r"forbidden\s*:\s*([^|]+)", re.IGNORECASE)


def _make_term(src: str, tgt: str, forbidden: str) -> GlossaryTerm:
    rx = re.compile(r"(?<!\w)" + re.escape(src) + r"(?!\w)", re.IGNORECASE)
    forb = tuple(x.strip() for x in re.split(r"[;|]", forbidden) if x.strip())
    return GlossaryTerm(src, tuple(t.strip() for t in tgt.split("|") if t.strip()), forb, rx)


def _load_long_glossary(reader: csv.DictReader, lower: Dict[str, str], locale: str) -> List[GlossaryTerm]:
    src_col, tgt_col = lower["source"], lower["target"]
    loc_col, forb_col = lower.get("locale"), lower.get("forbidden")
    terms: List[GlossaryTerm] = []
    for row in reader:
        src, tgt = as_str(row.get(src_col)).strip(), as_str(row.get(tgt_col)).strip()
        if not src or not tgt:
            continue
        if loc_col:
            loc = as_str(row.get(loc_col)).strip()
            if loc and normalize_locale(loc)[0] != locale:
                continue
        terms.append(_make_term(src, tgt, as_str(row.get(forb_col)).strip() if forb_col else ""))
    return terms


def _find_locale_column(fields: Sequence[str], locale: str, path: Path) -> str:
    for f in fields:
        try:
            if f.lower() not in ("term_en", "notes") and normalize_locale(f)[0] == locale:
                return f
        except L10nError:
            continue
    raise L10nError(f"{path}: glossary has no column for locale '{locale}' (columns: {list(fields)})")


def load_glossary(path: Path, locale: str) -> List[GlossaryTerm]:
    """Load wide or long termbase CSV definitions for locale."""
    raw = read_text_bom(path)
    if raw.strip() == "":
        raise L10nError(f"{path}: glossary is empty")
    reader = csv.DictReader(raw.splitlines(keepends=True), delimiter=sniff_delimiter(raw, path.suffix.lower()))
    fields = [f.strip() for f in (reader.fieldnames or [])]
    reader.fieldnames = fields
    lower = {f.lower(): f for f in fields}
    if "source" in lower and "target" in lower:
        return _load_long_glossary(reader, lower, locale)
    if "term_en" not in lower:
        raise L10nError(f"{path}: glossary header must be 'term_en,<locale>,...,notes' or 'source,target[,locale]'; got {fields}")
    loc_col = _find_locale_column(fields, locale, path)
    src_col, notes_col = lower["term_en"], lower.get("notes")
    terms: List[GlossaryTerm] = []
    for row in reader:
        src, tgt = as_str(row.get(src_col)).strip(), as_str(row.get(loc_col)).strip()
        if not src or not tgt:
            continue
        m = _FORBIDDEN_NOTE_RE.search(as_str(row.get(notes_col))) if notes_col else None
        terms.append(_make_term(src, tgt, m.group(1) if m else ""))
    return terms


def glossary_violations(src: str, dst: str, terms: Sequence[GlossaryTerm]) -> List[str]:
    """Return violations when source contains locked term missing or forbidden in target."""
    out: List[str] = []
    low = dst.lower()
    for t in terms:
        if not t.regex.search(src):
            continue
        ok = any((re.search(alt[3:], dst, re.IGNORECASE) if alt.startswith("re:") else alt.lower() in low) for alt in t.targets)
        if not ok:
            out.append(f"'{t.source}' must be rendered as {' | '.join(t.targets)}")
        for bad in t.forbidden:
            if bad.lower() in low:
                out.append(f"'{t.source}': forbidden rendering '{bad}' found")
    return out
