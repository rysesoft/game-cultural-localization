"""Shared helpers for the test-suite (stdlib unittest only)."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
SCRIPTS = ROOT / "skills" / "game-cultural-localization" / "scripts"
REFS = ROOT / "skills" / "game-cultural-localization" / "references"
FIXTURES = TESTS_DIR / "fixtures"
PY = sys.executable

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def run_cli(script: str, *args: str, utf8: bool = True, env_extra: dict[str, str] | None = None, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a script in a fresh interpreter with stdout/stderr captured as a pipe (no console)."""
    cmd = [PY]
    if utf8:
        cmd.append("-X")
        cmd.append("utf8")
    cmd += [str(SCRIPTS / script), *args]
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    env.pop("PYTHONUTF8", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(cmd, capture_output=True, env=env, cwd=str(cwd or ROOT))
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def write_json(path: Path, data: Any, bom: bool = False) -> Path:
    text = json.dumps(data, ensure_ascii=False, indent=1)
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
    return path


def write_text(path: Path, text: str, bom: bool = False, newline: str = "\n") -> Path:
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.replace("\n", newline).encode("utf-8"))
    return path


class TempDir:
    """Context manager creating a temp dir under the OS temp folder (never inside the repo).

    Uses a plain os.mkdir instead of tempfile.mkdtemp: some sandboxed hosts give
    mkdtemp directories a DACL the test process cannot write into.
    """

    def __enter__(self) -> Path:
        import shutil
        import uuid
        self._path = Path(tempfile.gettempdir()) / f"gcl-tests-{uuid.uuid4().hex[:10]}"
        self._path.mkdir(parents=True, exist_ok=False)
        self._rmtree = shutil.rmtree
        return self._path

    def __exit__(self, *exc: Any) -> None:
        self._rmtree(self._path, ignore_errors=True)
