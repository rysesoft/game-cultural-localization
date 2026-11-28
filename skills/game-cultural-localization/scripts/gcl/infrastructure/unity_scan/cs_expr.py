"""C# bracket navigation, member chain operands and string concatenation shape extraction."""

import bisect
import re
from collections.abc import Iterator

from .cs_lexer import THIS, _CsFile, _Str, _clip, _collapse, _unescape

__layer__ = "infrastructure"
__pattern__ = "Expression Analyzer"
__owns__ = "C# bracket matching, operand chains, concatenation shapes and Format extraction"


def _match_fwd(m: str, k: int, limit: int = 4000) -> int | None:
    depth = 0
    for j in range(k, min(len(m), k + limit)):
        c = m[j]
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
            if depth == 0:
                return j
    return None


def _match_back(m: str, k: int, limit: int = 4000) -> int | None:
    depth = 0
    for j in range(k, max(-1, k - limit), -1):
        c = m[j]
        if c in ")]":
            depth += 1
        elif c in "([":
            depth -= 1
            if depth == 0:
                return j
    return None


def _stmt_start(f: _CsFile, pos: int, floor: int = 0) -> int:
    m = f.masked
    return max(floor, max(m.rfind(";", floor, pos), m.rfind("{", floor, pos), m.rfind("}", floor, pos)) + 1)


def _header(f: _CsFile, o: int) -> tuple[int, str]:
    """Start and text of the header of the block opened at o."""
    hs = _stmt_start(f, o)
    return hs, _collapse(re.sub(r"(?m)^[ \t]*#.*$", "", f.nocomment[hs:o]))


def _enclosing(f: _CsFile, pos: int) -> Iterator[tuple[int, int]]:
    """Blocks around pos, innermost first."""
    for i in range(bisect.bisect_left(f.opens, pos) - 1, -1, -1):
        o, c = f.blocks[i]
        if c > pos:
            yield o, c


def _word_char(c: str) -> bool:
    return c.isalnum() or c == "_"


def _operand(f: _CsFile, a: int, b: int) -> tuple[int, int]:
    """Grow a name at [a, b) to its member chain (Class.NAME, this.NAME, NAME.Method(), NAME[i])."""
    m, n = f.masked, len(f.masked)
    while True:
        k = a - 1
        while k >= 0 and m[k].isspace():
            k -= 1
        if k < 0 or m[k] != ".":
            break
        j = k - 1
        if j >= 0 and m[j] == "?":
            j -= 1
        while j >= 0 and m[j].isspace():
            j -= 1
        if j >= 0 and m[j] in ")]":
            o = _match_back(m, j)
            if o is None:
                break
            j = o - 1
        e = j
        while j >= 0 and _word_char(m[j]):
            j -= 1
        if j == e:
            break
        a = j + 1
    while True:
        k = b
        while k < n and m[k].isspace():
            k += 1
        if k + 1 < n and m[k] == "?" and m[k + 1] == ".":
            k += 1
        if k < n and m[k] == ".":
            j = k + 1
            while j < n and m[j].isspace():
                j += 1
            e = j
            while e < n and _word_char(m[e]):
                e += 1
            if e == j:
                break
            b = e
            continue
        if k < n and m[k] in "([" and k == b:
            e = _match_fwd(m, k)
            if e is None:
                break
            b = e + 1
            continue
        break
    return a, b


def _bounds(f: _CsFile, a: int, b: int) -> tuple[int, int]:
    """Expression span around [a, b) at same bracket depth up to delimiter or assignment."""
    m, n = f.masked, len(f.masked)
    depth, k = 0, a - 1
    while k >= 0:
        if k in f.str_end:
            k = f.str_end[k].start - 1
            continue
        c = m[k]
        if c in ")]":
            depth += 1
        elif c in "([":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and (c in ",;{}:&|=" or (c == "?" and m[k + 1:k + 2] != ".") or (c == ">" and k and m[k - 1] == "=")):
            break
        k -= 1
    lo = k + 1
    depth, k = 0, b
    while k < n:
        if k in f.str_start:
            k = f.str_start[k].end
            continue
        c = m[k]
        if c in "([":
            depth += 1
        elif c in ")]":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and (c in ",;{}:&|=" or (c == "?" and m[k + 1:k + 2] != ".") or (c in "!<>" and m[k + 1:k + 2] == "=")):
            break
        k += 1
    return lo, k


def _split_top(f: _CsFile, lo: int, hi: int, sep: str) -> list[tuple[int, int]]:
    """Spans of [lo, hi) split at sep on bracket depth 0, trimmed."""
    m = f.masked
    parts, depth, start, k = [], 0, lo, lo
    while k < hi:
        if k in f.str_start:
            k = f.str_start[k].end
            continue
        c = m[k]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == sep and depth == 0 and not (sep == "+" and (m[k - 1:k] == "+" or m[k + 1:k + 2] in ("+", "="))):
            parts.append((start, k))
            start = k + 1
        k += 1
    parts.append((start, hi))
    out: list[tuple[int, int]] = []
    for p, q in parts:
        while p < q and m[p].isspace():
            p += 1
        while q > p and m[q - 1].isspace():
            q -= 1
        if q > p:
            out.append((p, q))
    return out


def _render(f: _CsFile, s: _Str, this: tuple[int, int] | None = None) -> str:
    """Text of a literal with holes rendered as {expression} or {THIS}."""
    out: list[str] = []
    for kind, p, q in s.parts:
        if kind == "lit":
            out.append(_unescape(f.text[p:q], s.verbatim, s.interp))
        elif this is not None and p <= this[0] and this[1] <= q:
            out.append(THIS)
        else:
            out.append("{" + _clip(f.nocomment[p:q], 40) + "}")
    return "".join(out)


def _format_shape(f: _CsFile, j: int, a: int, b: int, inner: str) -> str:
    """Shape of a string.Format call taking the operand as pattern or argument."""
    m = f.masked
    op = j
    if m[j] == ",":
        depth, k = 0, j - 1
        while k >= 0:
            c = m[k]
            if c in ")]":
                depth += 1
            elif c in "([":
                if depth == 0:
                    break
                depth -= 1
            elif c in ";{}" and depth == 0:
                return ""
            k -= 1
        if k < 0 or m[k] != "(":
            return ""
        op = k
    nm = re.search(r"([\w.]+)\s*$", m[max(0, op - 80):op])
    close = _match_fwd(m, op)
    if not nm or not nm.group(1).endswith("Format") or close is None:
        return ""
    args = _split_top(f, op + 1, close, ",")
    idx = next((i for i, (p, q) in enumerate(args) if p <= a and b <= q), None)
    if idx is None:
        return ""
    texts = [_clip(f.nocomment[p:q], 40) for p, q in args]
    if idx == 0:
        return nm.group(1) + "(" + inner + "".join(", {" + t + "}" for t in texts[1:]) + ")"
    lit = f.str_start.get(args[0][0])
    if lit is None or lit.end != args[0][1]:
        return ""

    def sub(mm: re.Match[str]) -> str:
        i = int(mm.group(1)) + 1
        return inner if i == idx else ("{" + texts[i] + "}" if i < len(texts) else mm.group())

    return re.sub(r"\{(\d+)(?:[:,][^}]*)?\}", sub, _render(f, lit))


def _expr(f: _CsFile, a: int, b: int) -> tuple[int, int, str]:
    """Return (start, end, shape) of expression carrying operand [a, b)."""
    m = f.masked
    inner = THIS
    i = bisect.bisect_left(f.str_starts, a) - 1
    while i >= 0:
        s = f.strings[i]
        if s.end >= b:
            if s.interp and any(k == "hole" and p <= a and b <= q for k, p, q in s.parts):
                inner = _render(f, s, (a, b))
                a, b = _operand(f, s.start, s.end)
            break
        i -= 1
    lo, hi = _bounds(f, a, b)
    km = re.match(r"\s*(?:return|await|throw|yield\s+return)\b", m[lo:hi])
    if km:
        lo += km.end()
    parts = _split_top(f, lo, hi, "+")
    if len(parts) > 1:
        out: list[str] = []
        for p, q in parts:
            lit = f.str_start.get(p)
            if p <= a and b <= q:
                out.append(inner)
            elif lit is not None and lit.end == q:
                out.append(_render(f, lit))
            else:
                out.append("{" + _clip(f.nocomment[p:q], 40) + "}")
        shape = "".join(out)
    else:
        shape = inner
    j = lo - 1
    while j >= 0 and m[j].isspace():
        j -= 1
    if j >= 1 and m[j] == "=" and m[j - 1] == "+":
        target = _collapse(f.nocomment[_stmt_start(f, j - 1):j - 1])
        tm = re.search(r"[\w.\[\]]+$", target)
        shape = "{" + (tm.group() if tm else target)[-40:] + "}" + shape
    elif j >= 0 and m[j] in "(,":
        shape = _format_shape(f, j, a, b, inner) or shape
    return lo, hi, ("" if shape == THIS else shape)
