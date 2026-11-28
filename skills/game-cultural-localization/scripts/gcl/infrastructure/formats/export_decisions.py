"""Export final translation loading, decision application and parity hold back workflow."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from gcl.domain.errors import L10nError
from gcl.infrastructure.tokens.rich_tags import parity_problems
from gcl.ports.formats import TableLoadOptions

from .io_utils import load_json_data
from .registry import TableFormatRegistry, DEFAULT_FORMAT_REGISTRY

__layer__ = "infrastructure"
__pattern__ = "Export Service"
__owns__ = "final batch loading, developer decision application and parity hold back"

DECISIONS = ("accept", "reject", "")


def collect_inputs(inp: Path, locale: str, changes: Sequence[str]) -> Tuple[List[Path], List[Path]]:
    """Collect final_batch_*.json files and corresponding change report JSONs."""
    if inp.is_dir():
        finals = sorted(inp.glob("final_batch_*.json"))
        if not finals:
            raise L10nError(f"{inp}: no final_batch_*.json in this folder")
        reports = [Path(c) for c in changes] if changes else sorted(inp.glob(f"changes_{locale}_*.json"))
    elif inp.is_file():
        finals, reports = [inp], [Path(c) for c in changes]
    else:
        raise L10nError(f"input not found: {inp}")
    for r in reports:
        if not r.is_file():
            raise L10nError(f"--changes file not found: {r}")
    return finals, reports


def load_finals(
    paths: Sequence[Path],
    locale: str,
    dst_field: Optional[str],
    key_field: str,
    sources: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Merge key -> target texts across final files while collecting optional source lines."""
    out: Dict[str, str] = {}
    for p in paths:
        rows = None
        for col in ([dst_field] if dst_field else [locale, "dst", "target"]):
            try:
                rows = DEFAULT_FORMAT_REGISTRY.get(p).read_rows(p, TableLoadOptions(src_field="en", dst_field=col, key_field=key_field, target_only=True))
                break
            except L10nError:
                continue
        if rows is None:
            raise L10nError(f"{p}: no target column (tried {dst_field or ', '.join((locale, 'dst', 'target'))}), pass --dst-field")
        for r in rows:
            if r.key in out and out[r.key] != r.dst:
                raise L10nError(f"{p}: key '{r.key}' has two different final texts")
            out[r.key] = r.dst
            src = r.src or str((r.meta or {}).get("en") or "")
            if sources is not None and src.strip():
                sources[r.key] = src
    return out


def apply_decisions(final: Dict[str, str], reports: Sequence[Path]) -> Dict[str, Any]:
    """Apply developer accept/reject decisions to final (mutating final for caller compatibility)."""
    stats: Dict[str, Any] = {"accepted": 0, "rejected": 0, "undecided": [], "unknown": []}
    for path in reports:
        rep = load_json_data(path)
        lines = rep.get("lines") if isinstance(rep, dict) else None
        if not isinstance(lines, list):
            raise L10nError(f"{path}: not a change report of report_changes.py (no 'lines' list)")
        for line in lines:
            key = str(line.get("key", ""))
            decision = str(line.get("decision") or "").strip().lower()
            if decision not in DECISIONS:
                raise L10nError(f"{path}: line '{key}' has the decision '{decision}', use accept, reject or leave it empty")
            if key not in final:
                stats["unknown"].append(key)
                continue
            old, new = str(line.get("old", "")), str(line.get("new", ""))
            if decision == "accept":
                final[key] = new
                stats["accepted"] += 1
            elif decision == "reject":
                final[key] = old
                stats["rejected"] += 1
            elif new != old:
                final[key] = old
                stats["undecided"].append(key)
    return stats


def hold_back_broken(final: Dict[str, str], sources: Dict[str, str], ph_style: str, tag_style: str) -> Dict[str, List[str]]:
    """Remove keys whose target placeholders or tags differ from source and return reasons."""
    held: Dict[str, List[str]] = {}
    for key in list(final):
        problems = parity_problems(sources.get(key, ""), final[key], ph_style, tag_style)
        if problems:
            held[key] = problems
            del final[key]
    return held


def dispatch_non_unity_export(
    registry: TableFormatRegistry,
    templates: Sequence[Path],
    final: Dict[str, str],
    out_dir: Path,
    *,
    dst_field: str,
    key_field: str,
) -> Tuple[List[str], int, set]:
    """Export all non-Unity templates through the Strategy Registry."""
    files: List[str] = []
    placed = 0
    placed_keys: set = set()
    for t in templates:
        if t.suffix.lower() in (".asset", ".yaml", ".yml"):
            continue
        res = registry.get(t).write_export(final, t, out_dir, dst_field=dst_field, key_field=key_field)
        files.extend(res.files)
        placed += res.placed
        placed_keys.update(res.keys)
    return files, placed, placed_keys
