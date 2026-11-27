"""Google Gemini generateContent adapter (urllib, no SDK).

POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
headers x-goog-api-key
body {systemInstruction: {parts: [{text}]}, contents: [{role: "user", parts: [{text}]}],
      generationConfig: {temperature, maxOutputTokens, responseMimeType}}

The key travels in the x-goog-api-key header, as in Google's own examples. That works for the classic
project keys and for the auth keys AI Studio creates since May 2026, and keeps the key out of URLs.
Gemini 4 models think before they answer and the thoughts count against maxOutputTokens, so every request
asks for the model's own output maximum (GOOGLE_MAX_OUTPUT unless the config names one). Gemini 4 accepts any
value and caps it itself, checked live up to 10000000. Thought parts are skipped when the reply is read.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Dict, Optional, Tuple

from .base import GOOGLE_MAX_OUTPUT, HttpProvider, ProviderError


class GoogleProvider(HttpProvider):
    """Gemini models through generateContent."""

    name = "google"

    def _url(self) -> str:
        model = urllib.parse.quote(self.model, safe="-._")
        return f"{self.endpoint}/models/{model}:generateContent"

    def _headers(self) -> Dict[str, str]:
        return {"x-goog-api-key": self._key, "content-type": "application/json"}

    def _body(self, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> Dict[str, Any]:
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": float(temperature), "maxOutputTokens": self.max_output(GOOGLE_MAX_OUTPUT),
                                 "responseMimeType": "application/json" if json_mode else "text/plain"},
        }

    def _parse(self, data: Dict[str, Any]) -> Tuple[str, Optional[int], Optional[int]]:
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
        if isinstance(tout, int) and isinstance(thoughts, int):
            tout += thoughts  # thinking tokens are billed as output
        return text, tin if isinstance(tin, int) else None, tout if isinstance(tout, int) else None
