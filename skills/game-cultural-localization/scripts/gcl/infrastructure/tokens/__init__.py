"""Token parsing strategies for placeholders, rich text tags and visual width."""

from .parity_adapter import DefaultTokenParityAdapter
from .placeholders import (
    DEFAULT_PLACEHOLDER_REGISTRY, PLACEHOLDER_STYLES, ConfiguredPlaceholderStrategy, PlaceholderRegistry,
    compare_placeholders, extract_placeholders,
)
from .rich_tags import (
    DEFAULT_TAG_REGISTRY, TAG_STYLES, ConfiguredTagStrategy, TagRegistry, char_width, compare_tags, extract_tags,
    line_count, norm_tag, parity_problems, strip_tags, tag_structure_error, visual_width,
)

__all__ = [
    "ConfiguredPlaceholderStrategy",
    "ConfiguredTagStrategy",
    "DEFAULT_PLACEHOLDER_REGISTRY",
    "DEFAULT_TAG_REGISTRY",
    "DefaultTokenParityAdapter",
    "PLACEHOLDER_STYLES",
    "PlaceholderRegistry",
    "TAG_STYLES",
    "TagRegistry",
    "char_width",
    "compare_placeholders",
    "compare_tags",
    "extract_placeholders",
    "extract_tags",
    "line_count",
    "norm_tag",
    "parity_problems",
    "strip_tags",
    "tag_structure_error",
    "visual_width",
]
