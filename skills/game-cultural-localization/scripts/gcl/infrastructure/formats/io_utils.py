"""Low level UTF-8 file reading, JSON loading, CSV delimiter sniffing and game root guard."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from gcl.domain.errors import L10nError

__layer__ = "infrastructure"
__pattern__ = "IO Helpers"
__owns__ = "BOM tolerant text reading, JSON parsing, delimiter sniffing and game root detection"


def ensure_utf8_stdio() -> None:
    """Force UTF-8 on stdout and stderr while keeping terminal output alive."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass


def read_text_bom(path: Path) -> str:
    """Read a UTF-8 file tolerating a BOM or raise L10nError."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise L10nError(f"input file not found: {path}")
    except IsADirectoryError:
        raise L10nError(f"input path is a directory, expected a file: {path}")
    except PermissionError:
        raise L10nError(f"input file is not readable: {path}")
    except UnicodeDecodeError as exc:
        raise L10nError(f"{path} is not valid UTF-8 ({exc.reason} at byte {exc.start}); re-save as UTF-8")


def as_str(v: Any) -> str:
    return "" if v is None else str(v)


def sniff_delimiter(sample: str, suffix: str) -> str:
    """Pick CSV delimiter from header line or default to tab for TSV."""
    if suffix == ".tsv":
        return "\t"
    header = sample.splitlines()[0] if sample else ""
    counts = {d: header.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


def check_columns(available: Iterable[str], required: Dict[str, str], path: Path) -> None:
    avail = set(available)
    missing = [f"{role} column '{name}'" for role, name in required.items() if name not in avail]
    if missing:
        raise L10nError(
            f"{path}: missing " + ", ".join(missing) + f"; available columns: {sorted(avail)}"
            " (use --src-field/--dst-field/--key-field or --target-only)"
        )


def load_json_data(path: Path) -> Any:
    """Load JSON tolerating BOM and reporting line numbers on failure."""
    raw = read_text_bom(path)
    if raw.strip() == "":
        raise L10nError(f"{path}: file is empty")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise L10nError(f"{path}: invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}")


def game_root(path: Path) -> Optional[Path]:
    """Return Unity, Godot or Unreal root directory containing path, else None."""
    p = Path(path).resolve()
    for d in [p] + list(p.parents):
        if (d / "ProjectSettings").is_dir() and (d / "Assets").is_dir():
            return d
        if (d / "project.godot").is_file():
            return d
        try:
            if d.is_dir() and any(d.glob("*.uproject")):
                return d
        except OSError:
            continue
    return None
