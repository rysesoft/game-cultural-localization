"""Application pipeline service ports decoupling orchestration from infrastructure tools."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

__layer__ = "ports"
__pattern__ = "Port Interface"
__owns__ = "prompt, slice, validation, roundtrip, report and font scanner ports"


@runtime_checkable
class PromptTemplatePort(Protocol):
    """Render critic, pass2 or literal prompt templates."""

    def render(self, name: str, locale: str, *, warmup: str = "", contrastive: str = "") -> str: ...

    def sample_warmup(self, pack_dir: Path, registers: Sequence[str], count: int, seed: int) -> str: ...

    def sample_contrastive(self, pack_dir: Path, count: int, seed: int) -> str: ...

    def langpack_version(self, pack_dir: Path) -> Optional[str]: ...


@runtime_checkable
class CritiqueValidatorPort(Protocol):
    """Validate candidate text against source placeholders, rich tags and schema."""

    def validate_single(
        self,
        *,
        locale: str,
        source_file: str,
        entry: Dict[str, Any],
        target_by_key: Dict[str, str],
        sources_by_key: Dict[str, str],
        ph_style: str,
        tag_style: str,
    ) -> List[str]: ...


@runtime_checkable
class BlindSlicePort(Protocol):
    """Build, verify and persist source free blind slices."""

    def create_and_save(
        self,
        source_table_path: Path,
        out_path: Path,
        locale: str,
        src_field: str,
        context_cols: Sequence[str],
    ) -> Tuple[List[Dict[str, Any]], str]: ...


@runtime_checkable
class FontScannerPort(Protocol):
    """Run external glyph scan for Phase 0 and Phase 3 gates."""

    def scan(self, table_path: Path, dst_field: str, locale: Optional[str], fonts: Sequence[Path]) -> Dict[str, Any]: ...
