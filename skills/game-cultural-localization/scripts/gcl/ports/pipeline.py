"""Application pipeline service ports decoupling orchestration from infrastructure tools."""

from pathlib import Path
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

__layer__ = "ports"
__pattern__ = "Port Interface"
__owns__ = "prompt, slice, validation, roundtrip, report and font scanner ports"


@runtime_checkable
class PromptTemplatePort(Protocol):
    """Render critic, pass2 or literal prompt templates."""

    def render(self, name: str, locale: str, *, warmup: str = "", contrastive: str = "") -> str: ...

    def sample_warmup(self, pack_dir: Path, registers: Sequence[str], count: int, seed: int) -> str: ...

    def sample_contrastive(self, pack_dir: Path, count: int, seed: int) -> str: ...

    def langpack_version(self, pack_dir: Path) -> str | None: ...


@runtime_checkable
class CritiqueValidatorPort(Protocol):
    """Validate candidate text against source placeholders, rich tags and schema."""

    def validate_single(
        self,
        *,
        locale: str,
        source_file: str,
        entry: dict[str, Any],
        target_by_key: dict[str, str],
        sources_by_key: dict[str, str],
        ph_style: str,
        tag_style: str,
    ) -> list[str]: ...


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
    ) -> tuple[list[dict[str, Any]], str]: ...


@runtime_checkable
class FontScannerPort(Protocol):
    """Run external glyph scan for Phase 0 and Phase 3 gates."""

    def scan(self, table_path: Path, dst_field: str, locale: str | None, fonts: Sequence[Path]) -> dict[str, Any]: ...
