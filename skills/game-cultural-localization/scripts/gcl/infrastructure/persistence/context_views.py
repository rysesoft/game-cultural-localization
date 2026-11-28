"""Segregated Adapter views exposing either BlindContextView or WriterContextView."""
from __future__ import annotations

from typing import Any, Dict, Sequence

__layer__ = "infrastructure"
__pattern__ = "Interface Segregation Adapter"
__owns__ = "physically separate blind juror vs writer context adapters"


class BlindContextAdapter:
    """Implements BlindContextView exposing only neutral English map and line fields."""

    def __init__(self, pack: Any) -> None:
        self._pack = pack

    @property
    def source_name(self) -> str:
        return str(getattr(self._pack, "source", ""))

    @property
    def map_text(self) -> str:
        return str(getattr(self._pack, "jury_text", "") or getattr(self._pack, "text", ""))

    def build_system(self, base: str) -> str:
        return str(self._pack.system(base, writer=False))

    def line_fields(self, key: str) -> Dict[str, str]:
        return dict(self._pack.line(key, writer=False))

    def enrich_entries(self, items: Sequence[Dict[str, Any]], key_field: str = "key") -> int:
        return int(self._pack.enrich(items, key_field=key_field, writer=False))


class WriterContextAdapter:
    """Implements WriterContextView exposing locale appendix and full scout notes."""

    def __init__(self, pack: Any) -> None:
        self._pack = pack

    @property
    def source_name(self) -> str:
        return str(getattr(self._pack, "source", ""))

    @property
    def has_appendix(self) -> bool:
        return bool(getattr(self._pack, "appendix", ""))

    def build_system(self, base: str) -> str:
        return str(self._pack.system(base, writer=True))

    def line_fields(self, key: str) -> Dict[str, str]:
        return dict(self._pack.line(key, writer=True))
