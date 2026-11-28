"""Adapter implementing TokenParityPort using engine placeholder, tag and glossary helpers."""
from __future__ import annotations

from typing import Any, List, Sequence

from gcl.infrastructure.formats.glossary import glossary_violations

from .placeholders import compare_placeholders, extract_placeholders
from .rich_tags import compare_tags, extract_tags, parity_problems

__layer__ = "infrastructure"
__pattern__ = "Port Adapter"
__owns__ = "DefaultTokenParityAdapter bridging domain/application lint & rewrite to token parsers"


class DefaultTokenParityAdapter:
    """Implements TokenParityPort using PlaceholderRegistry, TagRegistry and glossary rules."""

    def placeholder_problems(self, src: str, dst: str, style: str = "auto", extra_regex: Any = None) -> List[str]:
        return compare_placeholders(
            extract_placeholders(src, style, extra_regex),
            extract_placeholders(dst, style, extra_regex),
        )

    def tag_problems(self, src: str, dst: str, style: str = "auto") -> List[str]:
        return compare_tags(extract_tags(src, style), extract_tags(dst, style))

    def glossary_problems(self, src: str, dst: str, glossary: Sequence[Any]) -> List[str]:
        return glossary_violations(src, dst, glossary)

    def parity_problems(self, src: str, dst: str, ph_style: str = "auto", tag_style: str = "auto") -> List[str]:
        return parity_problems(src, dst, ph_style, tag_style)
