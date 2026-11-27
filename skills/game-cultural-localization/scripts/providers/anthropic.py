"""Anthropic Messages API adapter (urllib, no SDK).

POST https://api.anthropic.com/v1/messages
headers  x-api-key, anthropic-version: 2023-06-01
body     {model, system: [{type: "text", text, cache_control}], messages: [{role: "user", content}], max_tokens}

Current Claude models reject sampling parameters (a 'temperature' returns HTTP 400), so none is sent.
They also think before they answer (Opus 5.5 always, Sonnet and Haiku 5.5 adaptively) and the thinking
counts against max_tokens, so every request asks for at least MIN_MAX_TOKENS. Only generated tokens are
billed, the higher ceiling costs nothing by itself. Thinking blocks are skipped, only text blocks are read.

Prompt caching is opt-in at Anthropic (checked live, no marker means no cache). The system prompt (critic or
Pass 2 prompt with warm-up and few-shots, about 4300 tokens) is the same for every batch of a run, so it goes
as one text block with cache_control ephemeral (5 minute TTL). The first call writes it (1.25x input price),
the following calls read it (0.1x on Haiku 5.5, 0.05x on Sonnet and Opus 5.5). Prompts under the model
minimum (512 tokens on the 5.5 models) are simply not cached, without an error.
input_tokens of the result is the whole prompt (uncached + written + read), the cache parts are reported apart.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .base import JSON_ONLY_HINT, MIN_MAX_TOKENS, HttpProvider, ProviderError

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(HttpProvider):
    """Claude models through the Messages API."""

    name = "anthropic"

    def _headers(self) -> Dict[str, str]:
        return {"x-api-key": self._key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}

    def _body(self, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> Dict[str, Any]:
        sys_text = system + ("\n\n" + JSON_ONLY_HINT if json_mode else "")
        return {"model": self.model, "system": [{"type": "text", "text": sys_text, "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": user}], "max_tokens": max(int(max_tokens), MIN_MAX_TOKENS)}

    def _parse(self, data: Dict[str, Any]) -> Tuple[Any, ...]:
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise ProviderError(f"anthropic/{self.model}: response has no 'content' list")
        text = "".join(str(b.get("text", "")) for b in blocks if isinstance(b, dict) and b.get("type") == "text")
        usage = data.get("usage") or {}
        uncached = _int_or_none(usage.get("input_tokens"))
        read = _int_or_none(usage.get("cache_read_input_tokens")) or 0
        write = _int_or_none(usage.get("cache_creation_input_tokens")) or 0
        total_in = None if uncached is None else uncached + read + write  # Anthropic reports the uncached remainder only
        return text, total_in, _int_or_none(usage.get("output_tokens")), read, write


def _int_or_none(v: Any) -> Optional[int]:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
