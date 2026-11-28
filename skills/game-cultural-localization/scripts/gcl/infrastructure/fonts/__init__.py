"""Font parsing, Unity TMP fallback chains and in process FontScannerPort adapter."""

from .font_chain import (
    CJK_LOCALES, FULL_WIDTH_EM, ChainEntry, ChainFont, ChainResult, FontChain, block_name, collect_target_chars,
    resolve_chars,
)
from .scanner_adapter import DefaultFontScannerAdapter, FontScanOptions, FontScanRun, format_font_report, scan_font_coverage
from .sfnt_parser import FontInfo, FontParseError, SfntFace, SfntFont, cmap_glyph_id, load_font_file, parse_cmap_table, parse_font_file
from .tmp_asset import TmpAssetData, find_assets_dir, guid_index, parse_tmp_asset, read_tmp_asset

__all__ = [
    "CJK_LOCALES",
    "ChainEntry",
    "ChainFont",
    "ChainResult",
    "DefaultFontScannerAdapter",
    "FULL_WIDTH_EM",
    "FontChain",
    "FontInfo",
    "FontParseError",
    "FontScanOptions",
    "FontScanRun",
    "SfntFace",
    "SfntFont",
    "TmpAssetData",
    "block_name",
    "cmap_glyph_id",
    "collect_target_chars",
    "find_assets_dir",
    "format_font_report",
    "guid_index",
    "load_font_file",
    "parse_cmap_table",
    "parse_font_file",
    "parse_tmp_asset",
    "read_tmp_asset",
    "resolve_chars",
    "scan_font_coverage",
]
