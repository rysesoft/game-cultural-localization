"""Persistence ports for memoization and translation memory repositories."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

__layer__ = "ports"
__pattern__ = "Repository Ports"
__owns__ = "memoization repository, TM parameter objects and segregated TM ports"


@dataclass(frozen=True)
class TMQuery:
    """Parameter object encapsulating translation memory lookup criteria."""
    locale: str
    text: str
    on: str = "src"
    category: str = ""
    speaker: str = ""
    k: int = 5
    min_similarity: float = 0.3
    exclude_key: Optional[str] = None
    statuses: Tuple[str, ...] = ("approved",)


@dataclass(frozen=True)
class TMSegment:
    """Parameter object representing one translation memory segment to persist."""
    locale: str
    key: str
    src: str
    dst: str
    category: str = ""
    speaker: str = ""
    register: str = ""
    status: str = "candidate"
    origin: str = ""


@runtime_checkable
class MemoRepository(Protocol):
    """Atomic cache store keyed by stable request hashes."""
    hits: int

    def make_key(self, *parts: Any) -> str: ...

    def get(self, key: str) -> Optional[Any]: ...

    def put(self, key: str, value: Any) -> None: ...


@runtime_checkable
class TMReader(Protocol):
    """Read only neighbor lookup port for Pass 1 RAG and jury evidence."""

    def query_neighbors(self, query: TMQuery) -> List[Dict[str, Any]]: ...


@runtime_checkable
class TMWriter(Protocol):
    """Write port for storing approved or candidate segments."""

    def store_segment(self, segment: TMSegment) -> str: ...
