"""Google Gemini adapter with cachedContentTokenCount telemetry fix and SSE reassembly."""

import urllib.parse
from typing import Any

from gcl.domain.errors import ProviderError, StreamInterrupted
from gcl.domain.models import RawVendorReply, TokenUsage
from gcl.ports.llm import ProviderCapabilities

from ..http_transport import GOOGLE_MAX_OUTPUT, HttpProvider, sse_events

__layer__ = "infrastructure"
__pattern__ = "Adapter"
__owns__ = "Gemini streamGenerateContent request formatting and full TokenUsage including cache reads"


def assemble_stream(text: str, label: str = "google") -> dict[str, Any]:
    """Reassemble Google streamGenerateContent SSE chunks into one GenerateContentResponse."""
    parts: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    finish: str | None = None
    feedback: dict[str, Any] | None = None
    for event in sse_events(text, label):
        if isinstance(event.get("error"), dict):
            err = event["error"]
            raise StreamInterrupted(f"{label}: the stream sent an error ({err.get('status', err.get('code', 'error'))}: {str(err.get('message', ''))[:200]})")
        if isinstance(event.get("usageMetadata"), dict):
            usage = event["usageMetadata"]
        if isinstance(event.get("promptFeedback"), dict):
            feedback = event["promptFeedback"]
        for cand in (event.get("candidates") or [])[:1]:
            for p in ((cand or {}).get("content") or {}).get("parts") or []:
                if isinstance(p, dict) and str(p.get("text", "")):
                    parts.append({"text": str(p["text"]), **({"thought": True} if p.get("thought") else {})})
            finish = (cand or {}).get("finishReason") or finish
    if finish is None:
        if feedback and feedback.get("blockReason"):
            return {"promptFeedback": feedback, "usageMetadata": usage}
        raise StreamInterrupted(f"{label}: the stream ended without a finishReason")
    return {
        "candidates": [{"content": {"parts": parts, "role": "model"}, "finishReason": finish}],
        "usageMetadata": usage,
        **({"promptFeedback": feedback} if feedback else {}),
    }


class GoogleProvider(HttpProvider):
    """Gemini models through streamGenerateContent?alt=sse."""

    name = "google"
    capabilities = ProviderCapabilities(supports_streaming=True, supports_cache_control=False)

    def _url(self) -> str:
        model = urllib.parse.quote(self.model, safe="-._")
        return f"{self.endpoint}/models/{model}:streamGenerateContent?alt=sse"

    def _decode(self, text: str, headers: dict[str, str]) -> dict[str, Any]:
        return assemble_stream(text, f"{self.name}/{self.model}") if self._is_stream(text, headers) else super()._decode(text, headers)

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._key, "content-type": "application/json"}

    def _body(self, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> dict[str, Any]:
        gen: dict[str, Any] = {
            "temperature": float(temperature),
            "maxOutputTokens": self.max_output(GOOGLE_MAX_OUTPUT),
            "responseMimeType": "application/json" if json_mode else "text/plain",
        }
        effort = self.options.get("effort")
        if isinstance(effort, str) and effort.strip():
            gen["thinkingConfig"] = {"thinkingLevel": effort.strip().upper()}
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen,
        }
        service_tier = self.options.get("service_tier")
        if isinstance(service_tier, str) and service_tier.strip():
            body["serviceTier"] = service_tier.strip().lower()
        return body

    def parse_reply(self, data: dict[str, Any]) -> RawVendorReply:
        cands = data.get("candidates")
        if not isinstance(cands, list) or not cands:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise ProviderError(f"google/{self.model}: empty reply ({reason})")
        parts = ((cands[0] or {}).get("content") or {}).get("parts") or []
        text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict) and not p.get("thought"))
        usage = data.get("usageMetadata") or {}
        tin = usage.get("promptTokenCount")
        tout = usage.get("candidatesTokenCount")
        thoughts = usage.get("thoughtsTokenCount")
        cread = usage.get("cachedContentTokenCount")
        billed_out = (tout if isinstance(tout, int) else 0) + (thoughts if isinstance(thoughts, int) else 0)
        return RawVendorReply(
            text=text,
            usage=TokenUsage(
                input_tokens=tin if isinstance(tin, int) else 0,
                output_tokens=billed_out,
                cache_read_tokens=cread if isinstance(cread, int) else 0,
                thought_tokens=thoughts if isinstance(thoughts, int) else 0,
            ),
            finish_reason=str((cands[0] or {}).get("finishReason") or "STOP"),
        )
