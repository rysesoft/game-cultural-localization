"""Pure domain prompt envelope codec, tolerant JSON extraction, hashes and token estimates."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from .errors import L10nError

__layer__ = "domain"
__pattern__ = "Codec Helper"
__owns__ = "prompt envelopes, tolerant JSON extraction, prompt hashes and token estimation"

PAYLOAD_SEP = "\n---\n"
JSON_ONLY_HINT = "Reply with one JSON object only. No Markdown fences, no prose outside the JSON."
_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)


def envelope(instruction: str, payload: Dict[str, Any]) -> str:
    """Build a user prompt combining instruction, separator and JSON payload."""
    return instruction.rstrip() + PAYLOAD_SEP + json.dumps(payload, ensure_ascii=False)


def split_envelope(user: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Inverse of envelope() returning (instruction, payload_or_None)."""
    if PAYLOAD_SEP not in user:
        return user, None
    head, tail = user.split(PAYLOAD_SEP, 1)
    try:
        data = json.loads(tail)
    except json.JSONDecodeError:
        return user, None
    return head, data if isinstance(data, dict) else None


def extract_json(text: str) -> Any:
    """Parse first JSON object or array from model output tolerating fences."""
    cleaned = _FENCE_RE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    if not starts:
        raise L10nError("model reply contains no JSON object")
    start = min(starts)
    closer = "}" if cleaned[start] == "{" else "]"
    end = cleaned.rfind(closer)
    if end <= start:
        raise L10nError("model reply contains no complete JSON object")
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise L10nError(f"model reply is not valid JSON: {exc.msg}")


def prompt_hash(system: str, user: str) -> str:
    """Deterministic 16 hex digit hash of a prompt pair."""
    return hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()[:16]


def salvage_keyed_items(text: str, reply_field: str) -> List[Dict[str, Any]]:
    """Recover complete JSON object items from a truncated keyed list response."""
    cleaned = _FENCE_RE.sub("", text.strip())
    m = re.search(rf'"{re.escape(reply_field)}"\s*:\s*\[', cleaned)
    if not m:
        return []
    decoder = json.JSONDecoder()
    pos, n = m.end(), len(cleaned)
    items: List[Dict[str, Any]] = []
    while pos < n:
        while pos < n and cleaned[pos] in " \t\r\n,":
            pos += 1
        if pos >= n or cleaned[pos] == "]" or cleaned[pos] != "{":
            break
        try:
            obj, end = decoder.raw_decode(cleaned, pos)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            items.append(obj)
        pos = end
    return items


def estimate_tokens(text: str) -> int:
    """Estimate tokens when usage metadata is absent."""
    wide = sum(1 for ch in text if unicodedata.east_asian_width(ch) in ("W", "F"))
    return wide + (len(text) - wide + 3) // 4
