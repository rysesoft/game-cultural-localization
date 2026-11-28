"""Pure domain prompt compaction removing IDE workflow prose for API mode calls."""
from __future__ import annotations

import re

__layer__ = "domain"
__pattern__ = "Pure Function"
__owns__ = "compacting agent and playbook markdown for API mode without dropping voice or ban rules"

_CLI_FENCE_RE = re.compile(r"```(?:bash|sh|powershell|pwsh)\b.*?```", re.DOTALL | re.IGNORECASE)
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_DROP_AGENT_HEADINGS = ("## Pass 1,", "## Pass 2,", "## Orchestration")
_DROP_AGENT_SUBSECTIONS = ("4. **Verify before you report completion.**",)


def _strip_from_heading(text: str, prefixes: tuple[str, ...]) -> str:
    lines = text.splitlines()
    out = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(p) for p in prefixes):
            skipping = True
            continue
        if skipping and stripped.startswith("## ") and not any(stripped.startswith(p) for p in prefixes):
            skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out)


def _strip_verify_step(text: str) -> str:
    lines = text.splitlines()
    out = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(p) for p in _DROP_AGENT_SUBSECTIONS):
            skipping = True
            continue
        if skipping and (stripped.startswith("#") or re.match(r"^\d+\.\s", stripped)):
            skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out)


def compact_agent_for_api(markdown_text: str) -> str:
    """Strip CLI verification and file workflow instructions from an agent prompt for API calls."""
    cleaned = _CLI_FENCE_RE.sub("", markdown_text)
    cleaned = _strip_verify_step(cleaned)
    cleaned = _strip_from_heading(cleaned, _DROP_AGENT_HEADINGS)
    return _BLANK_LINES_RE.sub("\n\n", cleaned).strip()


def compact_playbook_for_api(markdown_text: str) -> str:
    """Strip regex linter authoring tables from a locale playbook while keeping voice anchors and ban rules."""
    cleaned = _CLI_FENCE_RE.sub("", markdown_text)
    cleaned = _strip_from_heading(cleaned, ("## 12.", "### Suggested linter patterns"))
    return _BLANK_LINES_RE.sub("\n\n", cleaned).strip()


def compact_for_api(markdown_text: str, *, kind: str = "agent") -> str:
    """Compact agent or playbook Markdown depending on prompt kind."""
    return compact_playbook_for_api(markdown_text) if kind == "playbook" else compact_agent_for_api(markdown_text)
