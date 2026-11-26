#!/usr/bin/env python3
"""House punctuation style for README, docs, prompts and generated Markdown reports (not a CLI).

Prose must not contain semicolons, en or em dashes, or a colon inside a sentence.
Code (fenced blocks, inline code spans), YAML frontmatter, URLs and table separator
rows are exempt, so JSON examples and placeholders stay untouched.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import re
from typing import List, Tuple

FORBIDDEN_CHARS = (";", "–", "—")  # semicolon, en dash, em dash
_FENCE_RE = re.compile(r"^(```|~~~).*?^\1[ \t]*$", re.MULTILINE | re.DOTALL)
_INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1", re.DOTALL)
_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_COLON_RE = re.compile(r"(?<=\S):(?=\s|$)")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def prose_only(markdown: str) -> str:
    """Markdown with frontmatter, code blocks, inline code and URLs blanked (line count preserved)."""
    def blank(m: "re.Match[str]") -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    text = markdown.replace("\r\n", "\n")
    for rx in (_FRONTMATTER_RE, _FENCE_RE, _INLINE_CODE_RE, _URL_RE):
        text = rx.sub(blank, text)
    return text


def punctuation_problems(markdown: str) -> List[Tuple[int, str]]:
    """(line number, message) for every prose line that breaks the house style."""
    problems: List[Tuple[int, str]] = []
    for n, line in enumerate(prose_only(markdown).split("\n"), start=1):
        if _TABLE_SEP_RE.match(line):
            continue
        for ch in FORBIDDEN_CHARS:
            if ch in line:
                problems.append((n, f"forbidden character U+{ord(ch):04X}"))
        if _COLON_RE.search(line):
            problems.append((n, "colon inside a sentence"))
    return problems


def sanitize_prose(text: str) -> str:
    """Rewrite free text (model reasons, notes) to the house style: ';', dashes and sentence colons become commas."""
    out = re.sub(r"\s*[;–—]\s*", ", ", text)
    out = re.sub(r"(?<=\S):(?=\s|$)", ",", out)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r",\s*([.!?])", r"\1", out)
    return out.strip(" ,")
