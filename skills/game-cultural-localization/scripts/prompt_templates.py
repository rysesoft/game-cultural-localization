#!/usr/bin/env python3
"""Load and render the prompt templates in prompts/ (not a CLI).

prompts/<name>.<locale>.md  native prompt written in the target language (critic, pass2)
prompts/<name>.generic.md   English fallback for locales without a native prompt
prompts/<name>.md           locale independent prompt (literal)

A template starts with a small frontmatter block (name, locale, language,
empty_warmup, empty_contrastive) and uses {{SLOT}} placeholders.
Known slots: LOCALE, WARMUP, CONTRASTIVE, plus any extra slot a caller passes.
Python 3.15, standard library only.
"""

import random
import re
import sys
from pathlib import Path
from collections.abc import Sequence
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import SCRIPTS_DIR, L10nError, read_text_bom  # noqa: E402

PROMPTS_DIR = SCRIPTS_DIR.parent / "prompts"
SLOT_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


class PromptTemplate(NamedTuple):
    """A parsed template file."""
    name: str
    path: Path
    native: bool              # True when the file is written for this exact locale
    meta: dict[str, str]
    body: str


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split '---\\nkey: value\\n---\\n' frontmatter from the body (flat string values only)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        raise L10nError("prompt frontmatter is not closed with '---'")
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise L10nError(f"bad frontmatter line {line!r}")
        meta[key.strip()] = value.strip().strip('"')
    return meta, text[end + 5:].lstrip("\n")


def find_prompt(name: str, locale: str, prompts_dir: Path | None = None) -> PromptTemplate:
    """Locale file first, then <name>.generic.md, then <name>.md."""
    base = Path(prompts_dir) if prompts_dir else PROMPTS_DIR
    for candidate, native in ((base / f"{name}.{locale}.md", True), (base / f"{name}.generic.md", False), (base / f"{name}.md", False)):
        if candidate.is_file():
            meta, body = parse_frontmatter(read_text_bom(candidate).replace("\r\n", "\n"))
            return PromptTemplate(name, candidate, native, meta, body)
    raise L10nError(f"no prompt template '{name}' for {locale} in {base}")


def render_prompt(name: str, locale: str, *, warmup: str = "", contrastive: str = "", extra: dict[str, str] | None = None,
                  prompts_dir: Path | None = None) -> str:
    """Fill the slots of a template; empty warm-up / contrastive blocks get the template's own 'none' sentence."""
    tpl = find_prompt(name, locale, prompts_dir)
    values: dict[str, str] = {
        "LOCALE": locale,
        "WARMUP": warmup.strip() or tpl.meta.get("empty_warmup", "-"),
        "CONTRASTIVE": contrastive.strip() or tpl.meta.get("empty_contrastive", "-"),
    }
    values.update(extra or {})
    missing = sorted({m.group(1) for m in SLOT_RE.finditer(tpl.body)} - set(values))
    if missing:
        raise L10nError(f"{tpl.path.name}: no value for slot(s) {', '.join(missing)}")
    return SLOT_RE.sub(lambda m: values[m.group(1)], tpl.body)


def render_contrastive(pairs: Sequence[dict[str, Any]], count: int = 8, seed: int = 1234) -> str:
    """Few-shot block of native / robot pairs ('✓ native' then '✗ robot'), seeded and stable."""
    usable = [p for p in pairs if str(p.get("native", "")).strip() and str(p.get("robot", "")).strip()
              and str(p["native"]).strip() != str(p["robot"]).strip()]
    usable.sort(key=lambda p: str(p.get("key", "")))
    if not usable:
        return ""
    picked = sorted(random.Random(seed).sample(range(len(usable)), min(count, len(usable))))
    lines = []
    for n, i in enumerate(picked, start=1):
        p = usable[i]
        lines.append(f"{n}. ✓ {_one_line(p['native'])}")
        lines.append(f"   ✗ {_one_line(p['robot'])}")
    return "\n".join(lines)


def _one_line(text: Any) -> str:
    return " / ".join(l.strip() for l in str(text).splitlines() if l.strip())
