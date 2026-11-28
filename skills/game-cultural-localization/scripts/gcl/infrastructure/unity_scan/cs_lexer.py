"""Long path file reader and C# lexer that masks comments and literal bodies cleanly."""

import bisect
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__layer__ = "infrastructure"
__pattern__ = "Lexer and Value Object"
__owns__ = "Windows long path text reading, C# literal masking, unescaping and block span indexing"

THIS = "{THIS}"
_HOLE = "\x01"
_IDENT = re.compile(r"[A-Za-z_]\w*")
_CODE_TOKEN = re.compile(r'//|/\*|\$@"|@\$"|\$"|@"|"|\'|[{}]')
_STR_STOP = {
    (False, False): re.compile(r'[\\"\n]'),
    (True, False): re.compile(r'[\\"\n{}]'),
    (False, True): re.compile(r'"'),
    (True, True): re.compile(r'["{}]'),
}
_KEYWORDS = frozenset((
    "return else new case throw await yield out ref in is as goto using if for foreach while switch catch lock "
    "fixed do try finally nameof typeof sizeof default checked unchecked delegate operator params this base "
    "null true false select where"
).split())
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"', "'": "'", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def read_text(path: Path) -> str:
    """Read UTF-8 text of a project file, supporting paths longer than the Windows limit."""
    p = str(path.resolve())
    if os.name == "nt" and not p.startswith("\\\\?\\"):
        p = "\\\\?\\" + p
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _collapse(s: str) -> str:
    return " ".join(s.split())


def _clip(s: str, n: int = 120) -> str:
    s = _collapse(s)
    return s if len(s) <= n else s[: n - 3] + "..."


@dataclass(slots=True)
class _Str:
    """A C# string literal with lit and hole spans relative to file offsets."""

    start: int
    interp: bool
    verbatim: bool
    parts: list[list[Any]] = field(default_factory=list)
    end: int = -1


def _blank(arr: list[str], a: int, b: int, limit: int) -> None:
    for k in range(a, min(b, limit)):
        if arr[k] != "\n":
            arr[k] = " "


def _step_str(text: str, i: int, top: _Str, mk: list[str], stack: list[Any], strings: list[_Str]) -> int:
    n = len(text)
    rx = _STR_STOP[(top.interp, top.verbatim)]
    k = i
    while True:
        m = rx.search(text, k)
        if not m:
            k = n
            break
        k = m.start()
        c = text[k]
        if c == "\\":
            k += 2
            continue
        if (c == '"' and top.verbatim and text[k + 1:k + 2] == '"') or (c in "{}" and text[k + 1:k + 2] == c):
            k += 2
            continue
        if c == "}":
            k += 1
            continue
        break
    _blank(mk, i, k, n)
    top.parts.append(["lit", i, min(k, n)])
    if k < n and text[k] == "{":
        top.parts.append(["hole", k + 1, -1])
        mk[k] = _HOLE
        stack.append([top, 0])
        return k + 1
    top.end = min(k + 1, n)
    strings.append(top)
    stack.pop()
    return top.end


def _step_code(text: str, j: int, tok: str, nc: list[str], mk: list[str], stack: list[Any]) -> int:
    n = len(text)
    top = stack[-1]
    if tok == "//":
        e = text.find("\n", j)
        e = n if e < 0 else e
        _blank(nc, j, e, n)
        _blank(mk, j, e, n)
        return e
    if tok == "/*":
        e = text.find("*/", j + 2)
        e = n if e < 0 else e + 2
        _blank(nc, j, e, n)
        _blank(mk, j, e, n)
        return e
    if tok == "'":
        e = text.find("'", j + (3 if text[j + 1:j + 2] == "\\" else 2), j + 12)
        if e < 0:
            return j + 1
        _blank(mk, j + 1, e, n)
        return e + 1
    if tok == "{":
        top[1] += 1
        return j + 1
    if tok == "}":
        if top[0] is not None and top[1] == 0:
            top[0].parts[-1][2] = j
            mk[j] = _HOLE
            stack.pop()
            return j + 1
        top[1] -= 1
        return j + 1
    stack.append(_Str(j, "$" in tok, "@" in tok))
    return j + len(tok)


def _mask_cs(text: str) -> tuple[str, str, list[_Str]]:
    """Return (no-comment text, no-comment-or-literal text, parsed string literals)."""
    n = len(text)
    nc, mk = list(text), list(text)
    strings: list[_Str] = []
    stack: list[Any] = [[None, 0]]
    i = 0
    while i < n:
        top = stack[-1]
        if isinstance(top, _Str):
            i = _step_str(text, i, top, mk, stack, strings)
            continue
        m = _CODE_TOKEN.search(text, i)
        if not m:
            break
        i = _step_code(text, m.start(), m.group(), nc, mk, stack)
    complete = [s for s in strings if all(p[2] >= 0 for p in s.parts)]
    return "".join(nc), "".join(mk), sorted(complete, key=lambda s: s.start)


def _blocks(masked: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    stack: list[int] = []
    for m in re.finditer(r"[{}]", masked):
        if m.group() == "{":
            stack.append(m.start())
        elif stack:
            out.append((stack.pop(), m.start()))
    out.sort()
    return out


def _unescape(s: str, verbatim: bool, interp: bool) -> str:
    if interp:
        s = s.replace("{{", "{").replace("}}", "}")
    if verbatim:
        return s.replace('""', '"')

    def esc(m: re.Match[str]) -> str:
        body = m.group(1)
        if body[0] in "ux" and len(body) > 1:
            try:
                return chr(int(body[1:], 16))
            except ValueError:
                return m.group()
        return _ESCAPES.get(body, m.group())

    return re.sub(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{1,4}|.)", esc, s)


class _CsFile:
    """Lazy indexed view of a single C# source file."""

    def __init__(self, rel: str, text: str) -> None:
        self.rel, self.text = rel, text
        self.ready = False
        self.nocomment = ""
        self.masked = ""
        self.strings: list[_Str] = []
        self.starts: list[int] = []
        self.blocks: list[tuple[int, int]] = []
        self.opens: list[int] = []
        self.open_of: dict[int, int] = {}
        self.close_of: dict[int, int] = {}
        self.str_start: dict[int, _Str] = {}
        self.str_starts: list[int] = []
        self.str_end: dict[int, _Str] = {}

    def prepare(self) -> _CsFile:
        if not self.ready:
            self.nocomment, self.masked, self.strings = _mask_cs(self.text)
            self.starts = [0] + [m.end() for m in re.finditer(r"\n", self.text)]
            self.blocks = _blocks(self.masked)
            self.opens = [o for o, _c in self.blocks]
            self.open_of = {c: o for o, c in self.blocks}
            self.close_of = {o: c for o, c in self.blocks}
            self.str_start = {s.start: s for s in self.strings}
            self.str_starts = [s.start for s in self.strings]
            self.str_end = {s.end - 1: s for s in self.strings}
            self.ready = True
        return self

    def line(self, pos: int) -> int:
        return bisect.bisect_right(self.starts, pos)

    def line_text(self, pos: int) -> str:
        s = self.starts[self.line(pos) - 1]
        e = self.text.find("\n", s)
        return self.text[s: e if e >= 0 else len(self.text)].strip()[:240]
