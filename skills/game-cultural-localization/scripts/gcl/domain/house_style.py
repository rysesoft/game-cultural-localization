"""House punctuation rules for README, docs, prompts and generated Markdown reports."""

import re

__layer__ = "domain"
__pattern__ = "Pure Domain Policy"
__owns__ = "house punctuation verification and prose sanitization"

FORBIDDEN_CHARS = (";", "–", "—")
_FENCE_RE = re.compile(r"^(```|~~~).*?^\1[ \t]*$", re.MULTILINE | re.DOTALL)
_INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1", re.DOTALL)
_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_COLON_RE = re.compile(r"(?<=\S):(?=[*_]*(?:\s|$))")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")

_NONLATIN = "Ѐ-ӿ　-ヿ㐀-鿿가-힯＀-￯"
_EXAMPLE_RE = re.compile(
    r"\"[^\"\n]*\"|“[^”\n]*”|„[^“\n]*“|«[^»\n]*»|「[^」\n]*」|『[^』\n]*』"
    r"|(?<![*\w])\*(?![*\s])[^*\n]*?[^*\s]\*(?![*\w])"
    r"|[" + _NONLATIN + r"][" + _NONLATIN + r"\s·・、。]*"
)


def prose_only(markdown: str, exempt_examples: bool = False) -> str:
    """Return markdown with frontmatter, code, URLs and optional examples blanked."""
    def blank(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    text = markdown.replace("\r\n", "\n")
    for rx in (_FRONTMATTER_RE, _FENCE_RE, _INLINE_CODE_RE, _URL_RE):
        text = rx.sub(blank, text)
    if exempt_examples:
        text = _EXAMPLE_RE.sub(blank, text)
    return text


def punctuation_problems(markdown: str, exempt_examples: bool = False) -> list[tuple[int, str]]:
    """Return (line_number, message) pairs for prose violating house punctuation."""
    problems: list[tuple[int, str]] = []
    for n, line in enumerate(prose_only(markdown, exempt_examples).split("\n"), start=1):
        if _TABLE_SEP_RE.match(line):
            continue
        for ch in FORBIDDEN_CHARS:
            if ch in line:
                problems.append((n, f"forbidden character U+{ord(ch):04X}"))
        if _COLON_RE.search(line):
            problems.append((n, "colon inside a sentence"))
    return problems


def sanitize_prose(text: str) -> str:
    """Normalize free prose to house punctuation rules."""
    out = re.sub(r"\s*[;–—]\s*", ", ", text)
    out = re.sub(r"(?<=\S):(?=\s|$)", ",", out)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r",\s*([.!?])", r"\1", out)
    return out.strip(" ,")
