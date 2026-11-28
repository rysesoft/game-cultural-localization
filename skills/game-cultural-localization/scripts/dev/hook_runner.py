#!/usr/bin/env python3
"""Antigravity SessionStart and Stop lifecycle hook runner for persistent architecture governance.

Reads hook JSON from stdin and emits hook JSON to stdout (Python 3.15, stdlib only).
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DEV_DIR = Path(__file__).resolve().parent
SCRIPTS_ROOT = DEV_DIR.parent
REPO_ROOT = SCRIPTS_ROOT.parent.parent.parent

if str(DEV_DIR) not in sys.path:
    sys.path.insert(0, str(DEV_DIR))

import verify_architecture as va  # noqa: E402


def _read_stdin() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _changed_files() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", timeout=5,
        )
        if proc.returncode != 0:
            return []
        return [ln[3:].strip() for ln in proc.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.SubprocessError):
        return []


def handle_session_start() -> dict[str, Any]:
    brief = (
        "GCL Architecture Memory Active. Before editing scripts/gcl/ or scripts/*.py read "
        "docs/architecture/NAVIGATION.md, docs/architecture/ARCHITECTURE_MEMORY.md and "
        "skills/game-cultural-localization/scripts/gcl/AGENTS.md. Run sync_navigation.py and "
        "verify_architecture.py before finishing any code edit."
    )
    return {"injectSteps": [{"systemMessage": {"systemMessage": brief}}]}


def handle_stop(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("continuationActive"):
        return {}
    reason = str(payload.get("terminationReason", "NO_TOOL_CALL"))
    if reason not in ("NO_TOOL_CALL", ""):
        return {}
    changed = _changed_files()
    relevant = [p for p in changed if p.endswith(".py") or "docs/architecture/" in p.replace("\\", "/")]
    if not relevant:
        return {}
    errors = va.verify(check_nav=True)
    if not errors:
        return {}
    msg = "Architecture guard blocked completion. Fix these contract issues before stopping:\n- " + "\n- ".join(errors[:12])
    return {
        "terminationBehavior": "force_continue",
        "injectSteps": [{"systemMessage": {"systemMessage": msg}}],
    }


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "stop"
    payload = _read_stdin()
    out = handle_session_start() if mode == "session-start" else handle_stop(payload)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
