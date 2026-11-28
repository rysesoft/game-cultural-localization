"""Ports for table formats, placeholder strategies, tag strategies and lint handlers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

from gcl.domain.models import Finding, PlaceholderSet, Row, Tag

__layer__ = "ports"
__pattern__ = "Strategy Ports"
__owns__ = "table format, token parser and lint handler protocols"


@dataclass(frozen=True)
class TableLoadOptions:
    """Explicit table loading options without hidden format branching."""
    src_field: str = "en"
    dst_field: str = "dst"
    key_field: str = "key"
    target_only: bool = False
    delimiter: Optional[str] = None
    src_input: Optional[Path] = None
    shared_table: Optional[Path] = None


@dataclass(frozen=True)
class ExportResult:
    """Summary returned by writing localized texts back into a game table format."""
    files: Tuple[str, ...]
    placed: int
    keys: Tuple[str, ...]
    unchanged: int = 0
    not_placed: Tuple[str, ...] = ()


@runtime_checkable
class TableFormatStrategy(Protocol):
    """Strategy handling one localization file suffix."""
    suffixes: Tuple[str, ...]

    def read_rows(self, path: Path, options: TableLoadOptions) -> List[Row]: ...

    def write_export(
        self,
        final_texts: Dict[str, str],
        template: Path,
        out_dir: Path,
        *,
        dst_field: str,
        key_field: str,
    ) -> ExportResult: ...


@runtime_checkable
class PlaceholderStrategy(Protocol):
    """Strategy extracting placeholders for a single game engine style."""
    style: str

    def extract(self, text: str) -> PlaceholderSet: ...


@runtime_checkable
class TagStrategy(Protocol):
    """Strategy extracting and stripping rich text tags for one engine markup style."""
    style: str

    def extract(self, text: str) -> List[Tag]: ...

    def strip(self, text: str) -> str: ...


@runtime_checkable
class LintCheck(Protocol):
    """One deterministic check in the LQA Chain of Responsibility."""

    def check_row(self, row: Row, context: Any) -> List[Finding]: ...


@runtime_checkable
class TokenParityPort(Protocol):
    """Application facing port checking placeholder, rich tag and glossary parity."""

    def placeholder_problems(self, src: str, dst: str, style: str = "auto", extra_regex: Any = None) -> List[str]: ...

    def tag_problems(self, src: str, dst: str, style: str = "auto") -> List[str]: ...

    def glossary_problems(self, src: str, dst: str, glossary: Sequence[Any]) -> List[str]: ...

    def parity_problems(self, src: str, dst: str, ph_style: str = "auto", tag_style: str = "auto") -> List[str]: ...
