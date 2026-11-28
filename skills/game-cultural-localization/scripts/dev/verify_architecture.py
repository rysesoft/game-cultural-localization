#!/usr/bin/env python3
"""AST architecture, SOLID, Clean Code and house punctuation fitness verifier.

Python 3.15, standard library only. Exit 0 clean, Exit 1 contract violations found.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

DEV_DIR = Path(__file__).resolve().parent
SCRIPTS_ROOT = DEV_DIR.parent
REPO_ROOT = SCRIPTS_ROOT.parent.parent.parent
GCL_ROOT = SCRIPTS_ROOT / "gcl"
DOCS_ARCH = REPO_ROOT / "docs" / "architecture"

if str(DEV_DIR) not in sys.path:
    sys.path.insert(0, str(DEV_DIR))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import sync_navigation as nav  # type: ignore # noqa: E402

ALLOWED_IMPORTS: Dict[str, Set[str]] = {
    "domain": {"domain"},
    "ports": {"domain", "ports"},
    "aspects": {"domain", "ports", "aspects"},
    "application": {"domain", "ports", "aspects", "application"},
    "infrastructure": {"domain", "ports", "aspects", "infrastructure"},
    "composition": {"domain", "ports", "aspects", "application", "infrastructure", "composition"},
}
OUTER_SCRIPTS = {
    "l10n_common", "text_style", "providers", "llm_tasks", "jury", "deliberate", "pass2_rewrite",
    "orchestrator_stub", "lqa_linter", "ui_expansion_checker", "font_glyph_scanner", "export_translations",
    "build_context_map", "build_language_pack", "roundtrip_check", "eval_critic", "budget_report", "tm",
    "prompt_templates", "warmup_loader", "build_contrastive_set", "make_blind_slice", "validate_critique",
    "report_changes", "providers_check",
}
BLIND_RESTRICTED_SYMBOLS = {"WriterContextView", "WriterContextAdapter", "WriterContext"}
HARDCODED_VENDORS = {"anthropic", "google", "deepseek"}
MAX_FILE_LINES = 350
MAX_FUNC_LINES = 65
MAX_PARAMS = 7

_FORBIDDEN_CHARS = (";", "–", "—")
_FENCE_RE = re.compile(r"^(```|~~~).*?^\1[ \t]*$", re.MULTILINE | re.DOTALL)
_INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1", re.DOTALL)
_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)
_COLON_RE = re.compile(r"(?<=\S):(?=[*_]*(?:\s|$))")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _prose_punctuation_problems(markdown: str) -> List[str]:
    try:
        import text_style
        return [f"line {n}: {msg}" for n, msg in text_style.punctuation_problems(markdown)]
    except ImportError:
        text = markdown.replace("\r\n", "\n")
        for rx in (_FENCE_RE, _INLINE_CODE_RE, _URL_RE):
            text = rx.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
        probs: List[str] = []
        for idx, ln in enumerate(text.split("\n"), start=1):
            if _TABLE_SEP_RE.match(ln):
                continue
            for ch in _FORBIDDEN_CHARS:
                if ch in ln:
                    probs.append(f"line {idx}: forbidden U+{ord(ch):04X}")
            if _COLON_RE.search(ln):
                probs.append(f"line {idx}: colon inside sentence")
        return probs


def _resolve_module(current_mod: str, is_pkg: bool, level: int, target: Optional[str]) -> str:
    if level == 0:
        return target or ""
    parts = current_mod.split(".")
    base = parts if is_pkg else parts[:-1]
    drop = level - 1
    prefix = base[: len(base) - drop] if drop <= len(base) else []
    if target:
        prefix = prefix + target.split(".")
    return ".".join(prefix)


def _layer_of(mod: str) -> Optional[str]:
    parts = mod.split(".")
    if len(parts) >= 2 and parts[0] == "gcl" and parts[1] in ALLOWED_IMPORTS:
        return parts[1]
    return None


def _string_attr(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value.strip()
    return ""


def _imported_targets(tree: ast.AST, mod: str, is_pkg: bool) -> List[Tuple[str, Tuple[str, ...]]]:
    out: List[Tuple[str, Tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, ()))
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_module(mod, is_pkg, node.level, node.module)
            names = tuple(a.name for a in node.names)
            out.append((resolved, names))
    return out


def _check_clean_code(tree: ast.AST, rel: str, line_count: int) -> List[str]:
    issues: List[str] = []
    if line_count > MAX_FILE_LINES:
        issues.append(f"{rel}: {line_count} lines exceeds limit {MAX_FILE_LINES}")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = (getattr(node, "end_lineno", node.lineno) - node.lineno) + 1
            if span > MAX_FUNC_LINES:
                issues.append(f"{rel}:{node.lineno} {node.name}: {span} lines > {MAX_FUNC_LINES}")
            params = [a.arg for a in (node.args.posonlyargs + node.args.args + node.args.kwonlyargs) if a.arg not in ("self", "cls")]
            if len(params) > MAX_PARAMS:
                issues.append(f"{rel}:{node.lineno} {node.name}: {len(params)} parameters > {MAX_PARAMS}")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
            if node.attr == "insert" and node.value.attr == "path" and isinstance(node.value.value, ast.Name) and node.value.value.id == "sys":
                issues.append(f"{rel}:{node.lineno}: forbidden sys.path.insert inside gcl/")
    return issues


def _find_cycles(edges: Dict[str, Set[str]]) -> List[str]:
    state: Dict[str, int] = {}
    stack: List[str] = []
    cycles: List[str] = []

    def dfs(u: str) -> None:
        state[u] = 1
        stack.append(u)
        for v in sorted(edges.get(u, ())):
            if v not in edges:
                continue
            if state.get(v, 0) == 0:
                dfs(v)
            elif state.get(v) == 1:
                idx = stack.index(v)
                cycles.append(" -> ".join(stack[idx:] + [v]))
        stack.pop()
        state[u] = 2

    for node in sorted(edges):
        if state.get(node, 0) == 0:
            dfs(node)
    return cycles


def verify(check_nav: bool = True) -> List[str]:
    errors: List[str] = []
    edges: Dict[str, Set[str]] = {}
    if GCL_ROOT.is_dir():
        for path in sorted(GCL_ROOT.rglob("*.py")):
            rel_gcl = path.relative_to(GCL_ROOT)
            is_pkg = path.name == "__init__.py"
            mod_parts = list(rel_gcl.parent.parts) if is_pkg else list(rel_gcl.with_suffix("").parts)
            mod = ".".join(["gcl"] + mod_parts)
            rel = path.relative_to(REPO_ROOT).as_posix()
            src = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(src, filename=str(path))
            expected_layer = mod_parts[0] if mod_parts and mod_parts[0] in ALLOWED_IMPORTS else None
            if not is_pkg:
                for hdr in ("__layer__", "__pattern__", "__owns__"):
                    if not _string_attr(tree, hdr):
                        errors.append(f"{rel}: missing non-empty {hdr}")
                declared = _string_attr(tree, "__layer__")
                if expected_layer and declared and declared != expected_layer:
                    errors.append(f"{rel}: __layer__ {declared!r} does not match package {expected_layer!r}")
                errors.extend(_check_clean_code(tree, rel, len(src.splitlines())))
            layer = _layer_of(mod) or expected_layer
            edges.setdefault(mod, set())
            for target_mod, names in _imported_targets(tree, mod, is_pkg):
                top = target_mod.split(".")[0] if target_mod else ""
                if top in OUTER_SCRIPTS:
                    errors.append(f"{rel}: imports legacy outer script {target_mod!r}")
                tlayer = _layer_of(target_mod)
                if tlayer:
                    edges[mod].add(target_mod)
                    if layer and tlayer not in ALLOWED_IMPORTS.get(layer, set()):
                        errors.append(f"{rel}: layer violation ({layer} cannot import {target_mod})")
                if "application/jury" in rel or "application/tasks" in rel:
                    hit = [n for n in names if n in BLIND_RESTRICTED_SYMBOLS]
                    if hit or ("context_views" in target_mod and any("Writer" in n for n in names)):
                        errors.append(f"{rel}: blindness lock violation importing {names}")
            if path.name == "factory.py" and "providers" in rel:
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in HARDCODED_VENDORS:
                        errors.append(f"{rel}:{node.lineno}: hardcoded vendor literal {node.value!r} breaks OCP")
        for cyc in _find_cycles(edges):
            errors.append(f"cyclic import detected: {cyc}")
    doc_files: List[Path] = []
    if DOCS_ARCH.is_dir():
        doc_files.extend(sorted(DOCS_ARCH.rglob("*.md")))
    gcl_agents = GCL_ROOT / "AGENTS.md"
    if gcl_agents.is_file():
        doc_files.append(gcl_agents)
    for doc in doc_files:
        for p in _prose_punctuation_problems(doc.read_text(encoding="utf-8-sig")):
            errors.append(f"{doc.relative_to(REPO_ROOT).as_posix()} {p}")
    if check_nav:
        expected_nav = nav.render_navigation(nav.scan_gcl_modules(), nav.scan_facades())
        if not nav.NAV_PATH.is_file() or nav.NAV_PATH.read_text(encoding="utf-8") != expected_nav:
            errors.append(f"{nav.NAV_PATH.relative_to(REPO_ROOT).as_posix()}: stale navigation map (run sync_navigation.py)")
    return errors


def main(argv: Optional[Sequence[str]] = None) -> int:
    errs = verify(check_nav=("--no-nav" not in (argv or sys.argv[1:])))
    if errs:
        for e in errs:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print("Architecture verification OK (layers, cycles, blindness, OCP, Clean Code, navigation, docs style)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
