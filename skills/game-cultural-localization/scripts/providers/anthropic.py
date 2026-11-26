"""Anthropic Messages API adapter (urllib, no SDK).

POST https://api.anthropic.com/v1/messages
headers  x-api-key, anthropic-version: 2023-06-01
body     {model, system, messages: [{role: "user", content}], max_tokens, temperature}
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .base import JSON_ONLY_HINT, HttpProvider, ProviderError

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(HttpProvider):
    """Claude models through the Messages API."""

    name = "anthropic"

    def _headers(self) -> Dict[str, str]:
        return {"x-api-key": self._key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}

    def _body(self, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> Dict[str, Any]:
        sys_text = system + ("\n\n" + JSON_ONLY_HINT if json_mode else "")
        return {"model": self.model, "system": sys_text, "messages": [{"role": "user", "content": user}],
                "max_tokens": int(max_tokens), "temperature": float(temperature)}

    def _parse(self, data: Dict[str, Any]) -> Tuple[str, Optional[int], Optional[int]]:
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise ProviderError(f"anthropic/{self.model}: response has no 'content' list")
        text = "".join(str(b.get("text", "")) for b in blocks if isinstance(b, dict) and b.get("type") == "text")
        usage = data.get("usage") or {}
        return text, _int_or_none(usage.get("input_tokens")), _int_or_none(usage.get("output_tokens"))


def _int_or_none(v: Any) -> Optional[int]:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
