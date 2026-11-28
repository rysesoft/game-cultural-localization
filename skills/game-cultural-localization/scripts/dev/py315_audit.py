"""Python 3.15 AST compliance checker banning legacy Python idioms across scripts and tests."""

import ast
import re

LEGACY_TYPING_NAMES: frozenset[str] = frozenset({
    "Dict", "List", "Tuple", "Set", "FrozenSet", "Type", "Optional", "Union",
    "Callable", "Sequence", "Mapping", "MutableMapping", "Iterable", "Iterator",
    "TypeVar", "Generic", "TypeAlias",
})
_OLD_PY_DOC_RE = re.compile(r"Python 3\.(?:8|9|10|11|12|13|14)\+?")


def _is_dataclass_decorator(dec: ast.expr) -> bool:
    target = dec.func if isinstance(dec, ast.Call) else dec
    return (isinstance(target, ast.Name) and target.id == "dataclass") or (
        isinstance(target, ast.Attribute) and target.attr == "dataclass"
    )


def _has_slots_true(dec: ast.expr) -> bool:
    if not isinstance(dec, ast.Call):
        return False
    return any(
        kw.arg == "slots" and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for kw in dec.keywords
    )


def _is_literal_base(expr: ast.expr) -> bool:
    return (isinstance(expr, ast.Name) and expr.id == "Literal") or (
        isinstance(expr, ast.Attribute) and expr.attr == "Literal"
    )


def _quoted_annotation_lines(node: ast.AST) -> list[int]:
    """Return line numbers of string literal type annotations outside Literal[...] subscripts."""
    lines: list[int] = []

    def walk(cur: ast.AST, in_literal: bool) -> None:
        if isinstance(cur, ast.Subscript):
            walk(cur.value, False)
            walk(cur.slice, in_literal or _is_literal_base(cur.value))
            return
        if isinstance(cur, ast.Constant) and isinstance(cur.value, str) and not in_literal:
            lines.append(cur.lineno)
            return
        for child in ast.iter_child_nodes(cur):
            walk(child, in_literal)

    walk(node, False)
    return lines


def _annotation_roots(tree: ast.AST) -> list[ast.AST]:
    roots: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                if arg.annotation is not None:
                    roots.append(arg.annotation)
            if node.args.vararg and node.args.vararg.annotation is not None:
                roots.append(node.args.vararg.annotation)
            if node.args.kwarg and node.args.kwarg.annotation is not None:
                roots.append(node.args.kwarg.annotation)
            if node.returns is not None:
                roots.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            roots.append(node.annotation)
        elif isinstance(node, ast.TypeAlias):
            roots.append(node.value)
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Subscript):
                    roots.append(base)
    return roots


def check_modern_python(tree: ast.AST, src: str, rel: str, *, is_test: bool = False) -> list[str]:
    """Enforce native Python 3.15 syntax, slotted dataclasses and banned legacy idioms."""
    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "__future__" and any(a.name == "annotations" for a in node.names):
                issues.append(f"{rel}:{node.lineno}: forbidden 'from __future__ import annotations' in Python 3.15")
            elif node.module == "typing":
                bad = sorted(a.name for a in node.names if a.name in LEGACY_TYPING_NAMES)
                if bad:
                    issues.append(f"{rel}:{node.lineno}: forbidden legacy typing import {', '.join(bad)}")
            elif node.module == "os" and any(a.name == "walk" for a in node.names):
                issues.append(f"{rel}:{node.lineno}: forbidden os.walk import, use Path.walk()")
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                if node.value.id == "typing" and node.attr in LEGACY_TYPING_NAMES:
                    issues.append(f"{rel}:{node.lineno}: forbidden typing.{node.attr}")
                elif node.value.id == "os" and node.attr == "walk":
                    issues.append(f"{rel}:{node.lineno}: forbidden os.walk(), use Path.walk()")
        elif isinstance(node, ast.ClassDef):
            for dec in node.decorator_list:
                if _is_dataclass_decorator(dec) and not _has_slots_true(dec):
                    issues.append(f"{rel}:{node.lineno} {node.name}: @dataclass requires slots=True")

    for root in _annotation_roots(tree):
        for ln in _quoted_annotation_lines(root):
            issues.append(f"{rel}:{ln}: forbidden string quoted type annotation (PEP 649 makes quotes unnecessary)")

    if not is_test and isinstance(tree, ast.Module):
        doc = ast.get_docstring(tree) or ""
        m = _OLD_PY_DOC_RE.search(doc)
        if m:
            issues.append(f"{rel}: outdated Python version claim '{m.group(0)}' in module docstring")
    return issues
