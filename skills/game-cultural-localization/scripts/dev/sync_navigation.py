#!/usr/bin/env python3
"""Generate or check docs/architecture/NAVIGATION.md from module AST and metadata headers.

Python 3.15, standard library only.
"""
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS_ROOT.parent.parent.parent
GCL_ROOT = SCRIPTS_ROOT / "gcl"
NAV_PATH = REPO_ROOT / "docs" / "architecture" / "NAVIGATION.md"
LAYER_ORDER = ("domain", "ports", "aspects", "application", "infrastructure", "composition")


@dataclass(frozen=True)
class ModuleInfo:
    module: str
    rel_path: str
    layer: str
    pattern: str
    owns: str
    lines: int
    classes: Tuple[str, ...]


@dataclass(frozen=True)
class FacadeInfo:
    script: str
    lines: int
    summary: str


def _string_attr(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value.strip()
    return ""


def _public_classes(tree: ast.Module) -> Tuple[str, ...]:
    return tuple(n.name for n in tree.body if isinstance(n, ast.ClassDef) and not n.name.startswith("_"))


def _clean_cell(text: str) -> str:
    return text.replace(":", ".").replace(";", ",").replace("—", "-").replace("–", "-").replace("|", "/").strip()


def scan_gcl_modules(gcl_root: Path = GCL_ROOT) -> List[ModuleInfo]:
    if not gcl_root.is_dir():
        return []
    out: List[ModuleInfo] = []
    for path in sorted(gcl_root.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        rel_gcl = path.relative_to(gcl_root)
        layer_guess = rel_gcl.parts[0] if len(rel_gcl.parts) > 1 else rel_gcl.stem
        src = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(src, filename=str(path))
        mod = "gcl." + ".".join(rel_gcl.with_suffix("").parts)
        rel_repo = path.relative_to(REPO_ROOT).as_posix()
        layer = _string_attr(tree, "__layer__") or layer_guess
        pattern = _clean_cell(_string_attr(tree, "__pattern__") or "Module")
        owns = _clean_cell(_string_attr(tree, "__owns__") or ast.get_docstring(tree) or "")
        if "\n" in owns:
            owns = owns.splitlines()[0].strip()
        out.append(ModuleInfo(mod, rel_repo, layer, pattern, owns, len(src.splitlines()), _public_classes(tree)))
    rank = {name: i for i, name in enumerate(LAYER_ORDER)}
    out.sort(key=lambda m: (rank.get(m.layer, 99), m.module))
    return out


def scan_facades(scripts_root: Path = SCRIPTS_ROOT) -> List[FacadeInfo]:
    out: List[FacadeInfo] = []
    for path in sorted(scripts_root.glob("*.py")):
        if path.name.endswith(".workflow.py") or path.name == "__init__.py":
            continue
        src = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(src, filename=str(path))
        doc = (ast.get_docstring(tree) or "").splitlines()[0] if ast.get_docstring(tree) else ""
        out.append(FacadeInfo(path.name, len(src.splitlines()), _clean_cell(doc)))
    return out


def render_navigation(modules: Sequence[ModuleInfo], facades: Sequence[FacadeInfo]) -> str:
    lines: List[str] = [
        "# Codebase Navigation Map",
        "",
        "Generated automatically by `scripts/dev/sync_navigation.py`. Never edit manually.",
        "",
        "## Architecture Quick Rules",
        "",
        "- Read `ARCHITECTURE_MEMORY.md` before changing layer boundaries or design patterns.",
        "- Core logic lives inside `skills/game-cultural-localization/scripts/gcl/`.",
        "- Top level `scripts/*.py` files remain stable CLI and compatibility facades.",
        "- Run `python skills/game-cultural-localization/scripts/dev/verify_architecture.py` after every edit.",
        "",
        "## Core Layers (`scripts/gcl/`)",
        "",
    ]
    if not modules:
        lines += ["No `gcl/` modules created yet. Faz R1 populates `domain`, `ports` and `infrastructure`.", ""]
    else:
        lines += ["| Layer | Module | Pattern | Lines | Classes | Responsibility |", "|---|---|---|---|---|---|"]
        for m in modules:
            cls = ", ".join(f"`{c}`" for c in m.classes[:5]) + (" ..." if len(m.classes) > 5 else "")
            if not cls:
                cls = "-"
            lines.append(f"| `{m.layer}` | [{Path(m.rel_path).name}](../../{m.rel_path}) | {m.pattern} | {m.lines} | {cls} | {m.owns} |")
        lines.append("")
    lines += ["## CLI and Compatibility Facades (`scripts/`)", "", "| Script | Lines | Role |", "|---|---|---|"]
    for f in facades:
        lines.append(f"| [{f.script}](../../skills/game-cultural-localization/scripts/{f.script}) | {f.lines} | {f.summary} |")
    lines += [
        "",
        "## Developer and Governance Scripts (`scripts/dev/`)",
        "",
        "- `sync_navigation.py` regenerates this map from module AST headers and checks drift with `--check`.",
        "- `verify_architecture.py` enforces layer imports, cycle freedom, blindness lock, OCP locks, Clean Code bounds and house style.",
        "- `hook_runner.py` integrates `SessionStart` memory briefings and `Stop` verification with Antigravity `.agents/hooks.json`.",
        "",
    ]
    return "\n".join(lines)


def sync(check: bool = False, nav_path: Path = NAV_PATH) -> int:
    content = render_navigation(scan_gcl_modules(), scan_facades())
    if check:
        if not nav_path.is_file():
            print(f"navigation missing -> {nav_path}", file=sys.stderr)
            return 1
        existing = nav_path.read_text(encoding="utf-8")
        if existing != content:
            print(f"navigation stale -> run sync_navigation.py to update {nav_path}", file=sys.stderr)
            return 1
        print(f"navigation OK ({nav_path.relative_to(REPO_ROOT).as_posix()})")
        return 0
    nav_path.parent.mkdir(parents=True, exist_ok=True)
    nav_path.write_text(content, encoding="utf-8")
    print(f"navigation written -> {nav_path.relative_to(REPO_ROOT).as_posix()}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Generate or verify docs/architecture/NAVIGATION.md")
    ap.add_argument("--check", action="store_true", help="Exit 1 when NAVIGATION.md is stale or missing")
    args = ap.parse_args(argv)
    return sync(check=args.check)


if __name__ == "__main__":
    sys.exit(main())
