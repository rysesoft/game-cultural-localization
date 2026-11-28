"""Re export facade for domain envelope codec kept for infrastructure provider callers."""

from gcl.domain.envelope_codec import (
    JSON_ONLY_HINT, PAYLOAD_SEP, envelope, estimate_tokens, extract_json, prompt_hash, salvage_keyed_items, split_envelope,
)

__layer__ = "infrastructure"
__pattern__ = "Facade Re Export"
__owns__ = "backward compatible re exports of gcl.domain.envelope_codec"

__all__ = [
    "JSON_ONLY_HINT",
    "PAYLOAD_SEP",
    "envelope",
    "estimate_tokens",
    "extract_json",
    "prompt_hash",
    "salvage_keyed_items",
    "split_envelope",
]
