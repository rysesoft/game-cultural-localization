"""DeepSeek OpenAI compatible adapter with thinking toggle and SSE stream assembly."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from gcl.domain.errors import ProviderError, StreamInterrupted
from gcl.domain.models import RawVendorReply, TokenUsage
from gcl.ports.llm import ProviderCapabilities

from ..http_transport import DEEPSEEK_MAX_OUTPUT, HttpProvider, sse_events

__layer__ = "infrastructure"
__pattern__ = "Adapter"
__owns__ = "DeepSeek chat/completions formatting, SSE reassembly and cache hit usage"


def assemble_stream(text: str, label: str = "deepseek") -> Dict[str, Any]:
    """Reassemble DeepSeek OpenAI compatible SSE chunks into one completion payload."""
    content: List[str] = []
    usage: Optional[Dict[str, Any]] = None
    finish: Optional[str] = None
    done = False
    for event in sse_events(text, label):
        if event.get("__done__"):
            done = True
            continue
        if isinstance(event.get("error"), dict):
            err = event["error"]
            raise StreamInterrupted(f"{label}: the stream sent an error ({err.get('type', err.get('code', 'error'))}: {str(err.get('message', ''))[:200]})")
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        for ch in (event.get("choices") or [])[:1]:
            delta = (ch or {}).get("delta") or {}
            if delta.get("content"):
                content.append(str(delta["content"]))
            finish = (ch or {}).get("finish_reason") or finish
    if finish is None or not done:
        raise StreamInterrupted(f"{label}: the stream ended before " + ("finish_reason" if finish is None else "[DONE]"))
    return {"choices": [{"message": {"role": "assistant", "content": "".join(content)}, "finish_reason": finish}], "usage": usage or {}}


class DeepSeekProvider(HttpProvider):
    """DeepSeek models via OpenAI compatible chat/completions endpoint."""

    name = "deepseek"
    capabilities = ProviderCapabilities(supports_streaming=True, supports_cache_control=False)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "content-type": "application/json"}

    def _body(self, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": float(temperature),
            "max_tokens": self.max_output(DEEPSEEK_MAX_OUTPUT),
            "response_format": {"type": "json_object" if json_mode else "text"},
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        thinking = self.options.get("thinking")
        if thinking is not None:
            body["thinking"] = {"type": "enabled" if thinking else "disabled"}
        return body

    def _decode(self, text: str, headers: Dict[str, str]) -> Dict[str, Any]:
        return assemble_stream(text, f"{self.name}/{self.model}") if self._is_stream(text, headers) else super()._decode(text, headers)

    def parse_reply(self, data: Dict[str, Any]) -> RawVendorReply:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(f"deepseek/{self.model}: response has no choices")
        msg = (choices[0] or {}).get("message") or {}
        usage = data.get("usage") or {}
        tin = usage.get("prompt_tokens")
        tout = usage.get("completion_tokens")
        hit = usage.get("prompt_cache_hit_tokens")
        details = usage.get("completion_tokens_details") or {}
        thoughts = details.get("reasoning_tokens") if isinstance(details, dict) else None
        return RawVendorReply(
            text=str(msg.get("content") or ""),
            usage=TokenUsage(
                input_tokens=tin if isinstance(tin, int) else 0,
                output_tokens=tout if isinstance(tout, int) else 0,
                cache_read_tokens=hit if isinstance(hit, int) else 0,
                thought_tokens=thoughts if isinstance(thoughts, int) else 0,
            ),
            finish_reason=str((choices[0] or {}).get("finish_reason") or "stop"),
        )
