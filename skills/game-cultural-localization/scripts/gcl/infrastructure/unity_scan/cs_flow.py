"""C# control flow context, ternary conditions, assignment flows and read guards."""

import re
from collections.abc import Sequence

from .cs_expr import _enclosing, _header, _match_fwd, _split_top, _stmt_start, _word_char
from .cs_lexer import _KEYWORDS, _CsFile, _clip, _collapse

__layer__ = "infrastructure"
__pattern__ = "Control Flow Analyzer"
__owns__ = "enclosing conditions, method headers, ternary branches and assignment flow detection"

_MODS = r"(?:(?:public|private|protected|internal|static|virtual|override|abstract|sealed|async|extern|unsafe|new|partial|readonly)\s+)"
_TYPE = r"[A-Za-z_][\w.]*(?:\s*<[^(){};=]*>)?(?:\s*\[\s*\])*\??"
_METHOD_HDR = re.compile(r"(?P<mods>" + _MODS + r"*)(?P<type>" + _TYPE + r"\s+)?(?:[\w.]+\.)?(?P<name>[A-Za-z_]\w*)\s*(?:<[^()]*>)?\s*\(")
_PROP_HDR = re.compile(_MODS + r"*(?P<type>" + _TYPE + r")\s+(?P<name>[A-Za-z_]\w*)$")
_EXPR_BODY = re.compile(r"\s*(?:\[[^\]]*\]\s*)*" + _MODS + r"*(" + _TYPE + r")\s+([A-Za-z_]\w*)\s*(\([^()]*\))?\s*=>")
_ASSIGN = re.compile(r"\s*((?:var|string)\s+)?(?:this\s*\.\s*)?([A-Za-z_]\w*)\s*(\+?=)(?![=>])")
_TYPE_BEFORE = re.compile(r"(" + _TYPE + r")\s+$")
_PREFIX = re.compile(r"(if|while|foreach|for|using|lock|fixed)\s*\(")
_LABEL = re.compile(r"(?:case\b[^:;{}]*?|default\s*):(?!:)")
_DEBUG = re.compile(r"\b(?:Debug\s*\.\s*(?:Log|Assert)\w*|Console\s*\.\s*Write\w*|print)\s*\(")


def _prefixes(f: _CsFile, s: int, pos: int) -> tuple[list[str], int]:
    """Braceless if, else, loop and case prefixes of statement starting at s, and where they end."""
    m = f.masked
    conds: list[str] = []
    k = s
    while True:
        while k < pos and m[k].isspace():
            k += 1
        if m.startswith("else", k) and not _word_char(m[k + 4:k + 5] or " "):
            conds.append("else" + _else_of(f, s))
            k += 4
            continue
        pm = _PREFIX.match(m, k, pos)
        if pm:
            close = _match_fwd(m, pm.end() - 1)
            if close is None or close >= pos:
                break
            if pm.group(1) in ("if", "while"):
                conds.append(_clip(pm.group(1) + " (" + f.nocomment[pm.end():close] + ")"))
            k = close + 1
            continue
        lm = _LABEL.match(m, k, pos)
        if lm:
            k = lm.end()
            continue
        break
    return conds, k


def _else_of(f: _CsFile, s: int) -> str:
    """Return ' of if (...)' for an else starting at s when matching if is found."""
    m = f.masked
    k = s - 1
    while k >= 0 and m[k].isspace():
        k -= 1
    if k >= 0 and m[k] == "}" and k in f.open_of:
        o = f.open_of[k]
        hm = re.search(r"(?:else\s+)?(?:if|while)\s*\(.*$", _header(f, o)[1])
        return " of " + _clip(hm.group()) if hm else ""
    if k >= 0 and m[k] == ";":
        conds, _ = _prefixes(f, _stmt_start(f, k), k)
        if conds and conds[-1].startswith("if"):
            return " of " + conds[-1]
    return ""


def _ternary_back(f: _CsFile, k: int, stop: str) -> int:
    m = f.masked
    depth = 0
    while k >= 0:
        if k in f.str_end:
            k = f.str_end[k].start - 1
            continue
        c = m[k]
        if c in ")]":
            depth += 1
        elif c in "([":
            if depth == 0:
                return -1 if stop != "cond" else k
            depth -= 1
        elif depth == 0:
            if stop == "?" and c in ",;{}":
                return -1
            if stop == "?" and c == "?" and m[k + 1:k + 2] not in (".", "?") and m[k - 1:k] != "?":
                return k
            if stop == "cond" and (c in ",;{}?:" or (c == "=" and m[k + 1:k + 2] != "=" and m[k - 1:k] not in ("=", "!", "<", ">"))):
                return k
        k -= 1
    return -1 if stop != "cond" else k


def _ternary(f: _CsFile, lo: int) -> str:
    """Return 'when (cond)' or 'when not (cond)' when lo starts a conditional operator branch."""
    m = f.masked
    j = lo - 1
    while j >= 0 and m[j].isspace():
        j -= 1
    if j < 1 or m[j] not in "?:" or (m[j] == "?" and (m[j + 1:j + 2] in (".", "?") or m[j - 1] == "?")):
        return ""
    neg = m[j] == ":"
    if neg:
        j = _ternary_back(f, j - 1, "?")
        if j < 0:
            return ""
    k = _ternary_back(f, j - 1, "cond")
    cond = re.sub(r"^(?:return|await)\s+", "", _collapse(f.nocomment[k + 1:j]))
    return _clip(("when not (" if neg else "when (") + cond + ")") if cond else ""


def _classify_header(hdr: str) -> tuple[str, str]:
    h = re.sub(r"^(?:\[[^\]]*\]\s*)+", "", hdr).strip()
    h = re.sub(r"^(?:(?:case\b[^:]*?|default\s*):(?!:)\s*)+", "", h).strip()
    if not h:
        return "", ""
    if re.match(r"(?:else\s+)?(?:if|while)\s*\(", h):
        return "if", h
    if h == "else":
        return "else", h
    if re.match(r"switch\s*\(", h):
        return "switch", h
    if re.match(r"catch\b", h):
        return "catch", h
    eb = _EXPR_BODY.match(h)
    if eb and eb.group(1).split("<")[0] not in _KEYWORDS:
        return "method", eb.group(2)
    if h.endswith("=>") or re.match(r"(?:for|foreach|do|try|finally|using|lock|fixed|unsafe|checked|unchecked|delegate)\b", h):
        return "other", h
    tm = re.search(r"\b(?:class|struct|interface|enum|record|namespace)\s+([\w.]+)", h)
    if tm and "(" not in h[:tm.start()]:
        return "type", tm.group(1)
    if h in ("get", "set", "init", "add", "remove"):
        return "accessor", h
    tt = re.match(r"(" + _MODS + r"*)\([^()]*\)\??\s+(?=[A-Za-z_])", h)
    mm = _METHOD_HDR.match(tt.group(1) + "T " + h[tt.end():] if tt else h)
    if mm and (mm.group("type") or mm.group("mods").strip() not in ("", "new")) and mm.group("name") not in _KEYWORDS:
        tp = (mm.group("type") or "").split()
        hh = mm.string
        close = _match_fwd(hh, mm.end() - 1)
        tail = hh[close + 1:].strip() if close is not None else "?"
        if (not tp or tp[0] not in _KEYWORDS) and (not tail or tail.startswith((":", "where"))):
            return "method", mm.group("name")
    pm = _PROP_HDR.match(h)
    if pm and pm.group("type").split("<")[0] not in _KEYWORDS and pm.group("name") not in _KEYWORDS:
        return "property", pm.group("name")
    return "other", h


def _context(f: _CsFile, pos: int, s: int) -> tuple[str, list[str]]:
    """Return (method, enclosing conditions innermost first) around pos."""
    conds, _ = _prefixes(f, s, pos)
    conds.reverse()
    method = ""
    for o, _c in _enclosing(f, pos):
        hs, hdr = _header(f, o)
        kind, text = _classify_header(hdr)
        if kind == "if":
            conds.append(_clip(text))
        elif kind == "else":
            conds.append("else" + _else_of(f, hs))
        elif kind == "switch":
            labels = list(_LABEL.finditer(f.masked, o + 1, pos))
            lab = _collapse(f.nocomment[labels[-1].start():labels[-1].end() - 1]) + " of " if labels else ""
            conds.append(_clip(lab + text))
        elif kind == "catch":
            conds.append(_clip(text))
        elif kind in ("method", "property"):
            method = text
            break
        elif kind == "type":
            break
    if not method:
        em = _EXPR_BODY.match(f.masked, s, pos)
        if em and em.group(1).split("<")[0] not in _KEYWORDS:
            method = em.group(2)
    return method, conds[:3]


def _helpers(f: _CsFile, conds: Sequence[str]) -> dict[str, str]:
    """One-line bool helper bodies called inside conds within the same file."""
    out: dict[str, str] = {}
    for cond in conds:
        for nm in re.finditer(r"\b([A-Za-z_]\w*)\b(\s*\(\s*\))?", cond):
            name = nm.group(1)
            label = name + ("()" if nm.group(2) else "")
            if name in _KEYWORDS or label in out or len(out) >= 3:
                continue
            rxs = (
                [r"\bbool\s+%s\s*\(\s*\)\s*=>\s*([^;{}]+);", r"\bbool\s+%s\s*\(\s*\)\s*\{\s*return\s+([^;{}]+);\s*\}"]
                if nm.group(2)
                else [r"\bbool\s+%s\s*=>\s*([^;{}]+);", r"\bbool\s+%s\s*\{\s*get\s*(?:=>\s*([^;{}]+);|\{\s*return\s+([^;{}]+);\s*\})"]
            )
            for rx in rxs:
                dm = re.search(rx % re.escape(name), f.nocomment)
                if dm:
                    out[label] = _clip(next(g for g in dm.groups() if g), 120)
                    break
    return out


def _initializer(f: _CsFile, s: int, lo: int) -> str | None:
    """Return 'Type.Member' when [s, lo) sits inside an object initializer."""
    if s == 0 or f.masked[s - 1] != "{":
        return None
    hdr = _header(f, s - 1)[1]
    nm = re.search(r"\bnew\b\s*([\w.]*)(?:\s*<[^()]*>)?\s*(?:\([^()]*\)|\[\s*\])?\s*$", hdr)
    if not nm and not hdr.endswith("="):
        return None
    parts = _split_top(f, s, lo, ",")
    am = _ASSIGN.match(f.masked, parts[-1][0], lo) if parts else None
    member = am.group(2) if am else ""
    typ = nm.group(1) if nm else ""
    return ".".join(x for x in (typ, member) if x) or "initializer"


def _flow(f: _CsFile, lo: int, hi: int, floor: int = 0) -> tuple[str, str, bool]:
    """Classify where expression [lo, hi) flows."""
    s = _stmt_start(f, lo, floor)
    init = _initializer(f, s, lo)
    if init is not None:
        return "init", init, False
    _conds, k = _prefixes(f, s, lo)
    head = f.masked[k:lo]
    eb = _EXPR_BODY.match(head)
    if eb and eb.group(1).split("<")[0] not in _KEYWORDS:
        am = _ASSIGN.match(head[eb.end():])
        if am:
            return "load", am.group(2), bool(am.group(1))
        return ("return", eb.group(2), False) if eb.group(1) == "string" else ("direct", "", False)
    am = _ASSIGN.match(head)
    if am:
        return "load", am.group(2), bool(am.group(1))
    if re.match(r"\s*return\b", head):
        return "return", "", False
    return "direct", "", False


def _is_debug(f: _CsFile, a: int) -> bool:
    return "/Editor/" in "/" + f.rel or bool(_DEBUG.search(f.masked, _stmt_start(f, a), a))


def _is_read(f: _CsFile, a: int, b: int) -> bool:
    """False for declarations, writes, out arguments and nameof."""
    m = f.masked
    if re.match(r"\s*(?:=(?![=>])|\+=|-=|\?\?=)", m[b:b + 6]):
        return False
    before = m[max(0, a - 160):a]
    if re.search(r"(?:\bnameof\s*\(|\bout\s)\s*$", before):
        return False
    tm = _TYPE_BEFORE.search(before)
    if tm and not before[:tm.start()].rstrip().endswith("."):
        first = re.split(r"[\s.<\[?]", tm.group(1))[0]
        if first not in _KEYWORDS:
            return False
    return True
