"""Segregated context view ports enforcing source blindness at the interface boundary."""
from __future__ import annotations

from typing import Dict, Protocol, Sequence, Any, runtime_checkable

__layer__ = "ports"
__pattern__ = "Interface Segregation"
__owns__ = "blind juror context port vs writer context port"


@runtime_checkable
class BlindContextView(Protocol):
    """Read only neutral English context view allowed for jurors and blind pickers."""

    @property
    def source_name(self) -> str: ...

    @property
    def map_text(self) -> str: ...

    @property
    def has_jury_view(self) -> bool: ...

    def build_system(self, base: str) -> str: ...

    def line_fields(self, key: str) -> Dict[str, str]: ...

    def enrich_entries(self, items: Sequence[Dict[str, Any]], key_field: str = "key") -> int: ...


@runtime_checkable
class WriterContextView(Protocol):
    """Full context view including locale appendix and scout notes for Pass 1 and Pass 2 writers."""

    @property
    def source_name(self) -> str: ...

    @property
    def has_appendix(self) -> bool: ...

    def build_system(self, base: str) -> str: ...

    def line_fields(self, key: str) -> Dict[str, str]: ...
