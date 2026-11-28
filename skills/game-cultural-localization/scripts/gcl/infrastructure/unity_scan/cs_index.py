"""Indexed lookup over Unity project C# script files, classes, base families and fields."""

import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from .cs_expr import _enclosing, _header
from .cs_flow import _TYPE, _classify_header
from .cs_lexer import _IDENT, _KEYWORDS, _CsFile, read_text

__layer__ = "infrastructure"
__pattern__ = "Index Repository"
__owns__ = "C# identifier inverted index, class hierarchy lookup and field declaration queries"


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root.parent).as_posix()
    except ValueError:
        return path.name


class CsCodebaseIndex:
    """Cached token inverted index and class hierarchy navigator over C# scripts."""

    def __init__(self, root: Path) -> None:
        self.files: list[_CsFile] = []
        self.by_rel: dict[str, _CsFile] = {}
        for p in sorted(root.rglob("*.cs")):
            if p.is_file():
                cf = _CsFile(_rel(p, root), read_text(p))
                self.files.append(cf)
                self.by_rel[cf.rel] = cf
        self._index: dict[str, set[int]] | None = None
        self._class_cache: dict[str, list[_CsFile]] = {}

    def with_token(self, tok: str) -> set[int]:
        """Indices of files containing identifier tok."""
        if self._index is None:
            idx: dict[str, set[int]] = defaultdict(set)
            for i, cf in enumerate(self.files):
                for t in set(_IDENT.findall(cf.text)):
                    idx[t].add(i)
            self._index = idx
        return self._index.get(tok, set())

    def class_files(self, cls: str) -> list[_CsFile]:
        """Files declaring cls (partial classes included)."""
        if cls not in self._class_cache:
            rx = re.compile(r"\b(?:class|struct)\s+" + re.escape(cls) + r"\b")
            self._class_cache[cls] = [self.files[i] for i in sorted(self.with_token(cls)) if rx.search(self.files[i].text)]
        return self._class_cache[cls]

    def family(self, cls: str, first: _CsFile | None = None) -> list[_CsFile]:
        """Class files plus up to four levels of base classes."""
        out: list[_CsFile] = [first] if first is not None else []
        name = cls
        for _ in range(5):
            files = self.class_files(name)
            out += [cf for cf in files if cf not in out]
            base = None
            for cf in files:
                bm = re.search(r"\b(?:class|struct)\s+" + re.escape(name) + r"\s*(?:<[^>{]*>)?\s*:\s*([\w.]+)", cf.text)
                if bm:
                    base = bm.group(1).split(".")[-1]
                    break
            if not base or base in ("MonoBehaviour", "ScriptableObject", "Object"):
                break
            name = base
        return out

    def derived(self, cls: str) -> list[_CsFile]:
        rx = re.compile(r"\bclass\s+\w+\s*(?:<[^>{]*>)?\s*:\s*(?:[\w.]+\.)?" + re.escape(cls) + r"\b")
        return [self.files[i] for i in sorted(self.with_token(cls)) if rx.search(self.files[i].text)]

    def member_decl(self, files: Sequence[_CsFile], name: str) -> tuple[_CsFile, bool, bool, str] | None:
        """Return (file, static, shared, declaring class) for field or property name."""
        rx = re.compile(
            r"(?m)^[ \t]*(?:\[[^\]\n]*\][ \t]*)*((?:(?:public|private|protected|internal|static|readonly|const|new|"
            r"volatile|override|virtual|abstract)[ \t]+)*)(" + _TYPE + r")[ \t]+" + re.escape(name) + r"[ \t]*(?:=|;|\{|=>|,)"
        )
        for cf in files:
            cf.prepare()
            for dm in rx.finditer(cf.nocomment):
                if dm.group(2).split("<")[0] in _KEYWORDS:
                    continue
                kind, cls = self._type_at(cf, dm.start(2))
                if kind != "type":
                    continue
                mods = dm.group(1).split()
                return cf, "static" in mods or "const" in mods, any(x in mods for x in ("public", "internal", "protected")), cls
        return None

    @staticmethod
    def _type_at(cf: _CsFile, pos: int) -> tuple[str, str]:
        for o, _c in _enclosing(cf, pos):
            return _classify_header(_header(cf, o)[1])
        return "", ""

    def method_block(self, cf: _CsFile, pos: int) -> tuple[int, int] | None:
        for o, c in _enclosing(cf, pos):
            if _classify_header(_header(cf, o)[1])[0] in ("method", "property", "accessor"):
                return o, c
        return None

    def class_at(self, cf: _CsFile, pos: int) -> str:
        """Class name enclosing pos."""
        for o, _c in _enclosing(cf.prepare(), pos):
            kind, name = _classify_header(_header(cf, o)[1])
            if kind == "type":
                return name.split(".")[-1]
        return ""
