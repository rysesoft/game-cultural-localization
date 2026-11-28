"""Persistence ports for memoization and translation memory repositories."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from gcl.domain.verdict_models import LineVerdict

__layer__ = "ports"
__pattern__ = "Repository Ports"
__owns__ = "memoization repository, TM parameter objects and segregated TM ports"


@dataclass(frozen=True, slots=True)
class TMQuery:
    """Parameter object encapsulating translation memory lookup criteria."""
    locale: str
    text: str
    on: str = "src"
    category: str = ""
    speaker: str = ""
    k: int = 5
    min_similarity: float = 0.3
    exclude_key: str | None = None
    statuses: tuple[str, ...] = ("approved",)


@dataclass(frozen=True, slots=True)
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

    def get(self, key: str) -> Any | None: ...

    def put(self, key: str, value: Any) -> None: ...


@runtime_checkable
class TMReader(Protocol):
    """Read only neighbor lookup port for Pass 1 RAG and jury evidence."""

    def query_neighbors(self, query: TMQuery) -> list[dict[str, Any]]: ...


@runtime_checkable
class TMWriter(Protocol):
    """Write port for storing approved or candidate segments."""

    def store_segment(self, segment: TMSegment) -> str: ...


@runtime_checkable
class VerdictRepository(Protocol):
    """Persistence port for saving and hydrating jury batch verdict documents."""

    def save_batch(self, path: Path, doc: dict[str, Any]) -> dict[str, Any]: ...

    def load_batch(self, path: Path) -> tuple[dict[str, Any], list[LineVerdict]]: ...
