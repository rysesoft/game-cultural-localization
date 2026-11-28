"""Anthropic Messages API adapter with prompt cache_control and SSE stream assembly."""
from __future__ import annotations

from typing import Any, Dict, Optional

from gcl.domain.errors import ProviderError, StreamInterrupted
from gcl.domain.models import RawVendorReply, TokenUsage
from gcl.ports.llm import ProviderCapabilities

from ..http_transport import ANTHROPIC_MAX_OUTPUT, HttpProvider, sse_events

__layer__ = "infrastructure"
__pattern__ = "Adapter"
__owns__ = "Anthropic Claude Messages API request formatting, SSE reassembly and cache telemetry"

JSON_ONLY_HINT = "Reply with one JSON object only. No Markdown fences, no prose outside the JSON."
ANTHROPIC_VERSION = "2023-06-01"


def _int_or_none(v: Any) -> Optional[int]:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def assemble_stream(text: str, label: str = "anthropic") -> Dict[str, Any]:
    """Reassemble Anthropic Messages SSE events into one message payload."""
    message: Dict[str, Any] = {}
    blocks: Dict[int, Dict[str, Any]] = {}
    usage: Dict[str, Any] = {}
    finished = False
    for event in sse_events(text, label):
        kind = event.get("type")
        if kind == "message_start":
            start = event.get("message") or {}
            message.update({k: v for k, v in start.items() if k not in ("content", "usage")})
            usage.update(start.get("usage") or {})
        elif kind == "content_block_start":
            blocks[int(event.get("index", len(blocks)))] = dict(event.get("content_block") or {})
        elif kind == "content_block_delta":
            delta = event.get("delta") or {}
            block = blocks.setdefault(int(event.get("index", 0)), {"type": "text", "text": ""})
            if delta.get("type") == "text_delta":
                block["text"] = str(block.get("text", "")) + str(delta.get("text", ""))
        elif kind == "message_delta":
            usage.update({k: v for k, v in (event.get("usage") or {}).items() if v is not None})
            if (event.get("delta") or {}).get("stop_reason"):
                message["stop_reason"] = event["delta"]["stop_reason"]
        elif kind == "message_stop":
            finished = True
        elif kind == "error":
            err = event.get("error") or {}
            raise StreamInterrupted(f"{label}: the stream sent an error ({err.get('type', 'error')}: {str(err.get('message', ''))[:200]})")
    if not finished:
        raise StreamInterrupted(f"{label}: the stream ended before message_stop")
    message["content"] = [blocks[i] for i in sorted(blocks)]
    message["usage"] = usage
    return message


class AnthropicProvider(HttpProvider):
    """Claude models through Anthropic Messages API."""

    name = "anthropic"
    capabilities = ProviderCapabilities(supports_streaming=True, supports_cache_control=True)

    def _headers(self) -> Dict[str, str]:
        return {"x-api-key": self._key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}

    def _body(self, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> Dict[str, Any]:
        sys_text = system + ("\n\n" + JSON_ONLY_HINT if json_mode else "")
        body: Dict[str, Any] = {
            "model": self.model,
            "system": [{"type": "text", "text": sys_text, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
            "max_tokens": self.max_output(ANTHROPIC_MAX_OUTPUT),
            "stream": True,
        }
        effort = self.options.get("effort")
        if isinstance(effort, str) and effort.strip():
            body["thinking"] = {"type": "adaptive"}
            body["output_config"] = {"effort": effort.strip().lower()}
        return body

    def _decode(self, text: str, headers: Dict[str, str]) -> Dict[str, Any]:
        return assemble_stream(text, f"{self.name}/{self.model}") if self._is_stream(text, headers) else super()._decode(text, headers)

    def parse_reply(self, data: Dict[str, Any]) -> RawVendorReply:
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise ProviderError(f"anthropic/{self.model}: response has no 'content' list")
        text = "".join(str(b.get("text", "")) for b in blocks if isinstance(b, dict) and b.get("type") == "text")
        usage = data.get("usage") or {}
        uncached = _int_or_none(usage.get("input_tokens"))
        read = _int_or_none(usage.get("cache_read_input_tokens")) or 0
        write = _int_or_none(usage.get("cache_creation_input_tokens")) or 0
        tout = _int_or_none(usage.get("output_tokens"))
        total_in = 0 if uncached is None else uncached + read + write
        return RawVendorReply(
            text=text,
            usage=TokenUsage(input_tokens=total_in, output_tokens=tout or 0, cache_read_tokens=read, cache_write_tokens=write),
            finish_reason=str(data.get("stop_reason") or "stop"),
        )
