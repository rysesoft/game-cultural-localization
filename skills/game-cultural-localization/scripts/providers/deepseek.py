"""DeepSeek adapter, OpenAI compatible chat/completions (urllib, no SDK).

POST https://api.deepseek.com/chat/completions
header Authorization: Bearer <key>
body   {model, messages: [{role: "system"}, {role: "user"}], temperature, max_tokens, response_format}

Thinking mode is on by default at the API. The router passes options["thinking"]:
None leaves the API default, True / False send {"thinking": {"type": "enabled" | "disabled"}}.
With thinking on, the reasoning counts against max_tokens, so every request asks for the model's own
output maximum (DEEPSEEK_MAX_OUTPUT, 393216 as the API states it, unless the config names one). A 4096
limit was used up by thinking alone in the first live run, and deepseek-v4-pro filled 16000 later.

Every request is streamed ("stream": true with "stream_options": {"include_usage": true}), so a reply that
thinks for minutes keeps sending chunks and never reaches the read timeout. Checked live, every chunk holds a
delta with content or reasoning_content, the last one carries finish_reason and the usage, then "data: [DONE]".
The content pieces are put back together into one reply, the reasoning is skipped. A stream that ends without
finish_reason and [DONE], or sends an error, is retried.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import DEEPSEEK_MAX_OUTPUT, HttpProvider, ProviderError, StreamInterrupted, sse_events


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
        if self._is_stream(text, headers):
            return assemble_stream(text, f"{self.name}/{self.model}")
        return super()._decode(text, headers)

    def _parse(self, data: Dict[str, Any]) -> Tuple[Any, ...]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(f"deepseek/{self.model}: response has no choices")
        msg = (choices[0] or {}).get("message") or {}
        usage = data.get("usage") or {}
        tin = usage.get("prompt_tokens")
        tout = usage.get("completion_tokens")
        # DeepSeek caches prompt prefixes on its own (checked live), the hit share is billed at the cache price
        hit = usage.get("prompt_cache_hit_tokens")
        return (str(msg.get("content") or ""), tin if isinstance(tin, int) else None, tout if isinstance(tout, int) else None,
                hit if isinstance(hit, int) else 0, 0)


def assemble_stream(text: str, label: str = "deepseek") -> Dict[str, Any]:
    """Put the chunks of a streamed chat completion back together into one completion."""
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
