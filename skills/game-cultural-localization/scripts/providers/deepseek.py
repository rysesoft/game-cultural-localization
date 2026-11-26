"""DeepSeek adapter, OpenAI compatible chat/completions (urllib, no SDK).

POST https://api.deepseek.com/chat/completions
header Authorization: Bearer <key>
body   {model, messages: [{role: "system"}, {role: "user"}], temperature, max_tokens, response_format}

Thinking mode is on by default at the API. The router passes options["thinking"]:
None leaves the API default, True / False send {"thinking": {"type": "enabled" | "disabled"}}.
With thinking on, the reasoning counts against max_tokens, so every request asks for at least
MIN_MAX_TOKENS. A 4096 limit was used up by thinking alone in the first live run.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .base import MIN_MAX_TOKENS, HttpProvider, ProviderError


class DeepSeekProvider(HttpProvider):
    """DeepSeek models through the OpenAI compatible endpoint."""

    name = "deepseek"

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "content-type": "application/json"}

    def _body(self, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": float(temperature),
            "max_tokens": max(int(max_tokens), MIN_MAX_TOKENS),
            "response_format": {"type": "json_object" if json_mode else "text"},
        }
        thinking = self.options.get("thinking")
        if thinking is not None:
            body["thinking"] = {"type": "enabled" if thinking else "disabled"}
        return body

    def _parse(self, data: Dict[str, Any]) -> Tuple[str, Optional[int], Optional[int]]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(f"deepseek/{self.model}: response has no choices")
        msg = (choices[0] or {}).get("message") or {}
        usage = data.get("usage") or {}
        tin = usage.get("prompt_tokens")
        tout = usage.get("completion_tokens")
        return str(msg.get("content") or ""), tin if isinstance(tin, int) else None, tout if isinstance(tout, int) else None
