"""Unity project scanner, C# heuristic use tracer and scout slice adapters."""

from .cs_expr import _render
from .cs_lexer import _HOLE, THIS, _CsFile, _Str, _mask_cs, read_text
from .cs_tracer import TRACE_NOTE, trace_uses
from .slice_ops import UNASSIGNED, build_slices, check_slices, load_slice_spec, locale_tables, table_texts
from .unity_assets import (
    ASSET_EXTS,
    CODE_LINES_PER_FIELD,
    USE_SITES_PER_KEY,
    find_unity_root,
    load_tables,
    object_paths,
    scan_unity,
    script_classes,
)

__all__ = [
    "ASSET_EXTS",
    "CODE_LINES_PER_FIELD",
    "THIS",
    "TRACE_NOTE",
    "UNASSIGNED",
    "USE_SITES_PER_KEY",
    "_CsFile",
    "_HOLE",
    "_Str",
    "_mask_cs",
    "_render",
    "build_slices",
    "check_slices",
    "find_unity_root",
    "load_slice_spec",
    "load_tables",
    "locale_tables",
    "object_paths",
    "read_text",
    "scan_unity",
    "script_classes",
    "table_texts",
    "trace_uses",
]
