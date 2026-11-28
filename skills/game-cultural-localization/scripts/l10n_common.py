#!/usr/bin/env python3
"""Backward compatible Facade over gcl.domain and gcl.infrastructure format/token modules."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from gcl.domain.errors import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, L10nError, __version__  # noqa: E402,F401
from gcl.domain.locales import CANONICAL_LOCALES, PLURAL_FORMS, normalize_locale  # noqa: E402,F401
from gcl.domain.models import Finding, GlossaryTerm, PlaceholderSet, Risk, Row, Tag  # noqa: E402,F401
from gcl.infrastructure.formats.cli_support import (  # noqa: E402,F401
    add_common_args, add_input_argument, emit_report, resolve_input, run_main,
)
from gcl.infrastructure.formats.glossary import glossary_violations, load_glossary  # noqa: E402,F401
from gcl.infrastructure.formats.io_utils import (  # noqa: E402,F401
    ensure_utf8_stdio, load_json_data, read_text_bom, sniff_delimiter,
)
from gcl.infrastructure.formats.po_format import parse_po  # noqa: E402,F401
from gcl.infrastructure.formats.project_config import CONFIG_KEYS, apply_config, load_config, pick  # noqa: E402,F401
from gcl.infrastructure.formats.registry import (  # noqa: E402,F401
    DEFAULT_FORMAT_REGISTRY, SUPPORTED_INPUT_SUFFIXES, load_table_options, load_target_rows,
)
from gcl.infrastructure.formats.unity_yaml_reader import (  # noqa: E402,F401
    UNITY_ASSET_TABLE_SCRIPT, _fold_flow, _quote_end, _yaml_scalar, is_unity_asset_table, parse_unity_yaml,
)
from gcl.infrastructure.paths import DEFAULT_RULES_DIR, SCRIPTS_DIR  # noqa: E402,F401
from gcl.infrastructure.tokens.placeholders import (  # noqa: E402,F401
    BACKTICK, PLACEHOLDER_STYLES, PRINTF_PH_RE, compare_placeholders, extract_placeholders,
)
from gcl.infrastructure.tokens.rich_tags import (  # noqa: E402,F401
    ANGLE_TAG_RE, BBCODE_TAGS, BB_TAG_RE, HEX_COLOR_TAG_RE, HTML_EXTRA_TAGS, TAG_STYLES, TMP_COLOR_NAMES, TMP_TAGS,
    VOID_TAGS, char_width, compare_tags, extract_tags, line_count, norm_tag, parity_problems, strip_tags,
    tag_structure_error, visual_width,
)
from gcl.ports.formats import TableLoadOptions  # noqa: E402


def load_table(
    path: Path,
    src_field: str = "en",
    dst_field: str = "dst",
    key_field: str = "key",
    *,
    target_only: bool = False,
    delimiter: Optional[str] = None,
    src_input: Optional[Path] = None,
    shared_table: Optional[Path] = None,
) -> List[Row]:
    """Load rows from any supported localization table via TableFormatRegistry."""
    opts = TableLoadOptions(
        src_field=src_field, dst_field=dst_field, key_field=key_field,
        target_only=target_only, delimiter=delimiter, src_input=src_input, shared_table=shared_table,
    )
    return load_table_options(path, opts, DEFAULT_FORMAT_REGISTRY)


def load_pairs(input_path: Path, src_field: str = "en", dst_field: str = "dst", key_field: str = "key", **kw: Any) -> List[Row]:
    """Backward compatible alias of load_table()."""
    return load_table(input_path, src_field, dst_field, key_field, **kw)
