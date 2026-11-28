"""Project l10n.config.json loader and CLI precedence helper."""

import os
from pathlib import Path
from typing import Any

from gcl.domain.errors import L10nError

from .io_utils import load_json_data

__layer__ = "infrastructure"
__pattern__ = "Configuration Loader"
__owns__ = "l10n.config.json schema validation and CLI override resolution"

CONFIG_KEYS: dict[str, Any] = {
    "locales": list, "src_field": str, "dst_field": str, "key_field": str,
    "placeholder_style": str, "tag_style": str, "placeholder_regex": str,
    "rules_dir": str, "glossary": str, "glossary_severity": str,
    "max_width": (int, float, dict), "expansion": dict, "cjk_cell_width": (int, float),
    "fail_on_warn": bool, "variant": str, "delimiter": str, "ambiguous_wide": bool,
    "forbid_chars": str, "forbid_spaced_hyphen": bool, "strict_whitespace": bool,
    "context_map": str,
}


def load_config(path: Path | None) -> dict[str, Any]:
    """Load and validate l10n.config.json resolving relative paths against config folder."""
    if path is None:
        return {}
    data = load_json_data(path)
    if not isinstance(data, dict):
        raise L10nError(f"{path}: config must be a JSON object")
    for k, v in data.items():
        if k.startswith("_"):
            continue
        if k not in CONFIG_KEYS:
            raise L10nError(f"{path}: unknown config key '{k}'; known keys: {', '.join(sorted(CONFIG_KEYS))}")
        if not isinstance(v, CONFIG_KEYS[k]) or isinstance(v, bool) and CONFIG_KEYS[k] is not bool:
            raise L10nError(f"{path}: config key '{k}' has wrong type {type(v).__name__}")
    for k in ("rules_dir", "glossary", "context_map"):
        if k in data and not os.path.isabs(data[k]):
            data[k] = str((path.parent / data[k]).resolve())
    return data


def pick(cli_value: Any, config: dict[str, Any], key: str, default: Any) -> Any:
    """Resolve option priority: CLI explicit value > config > default."""
    if cli_value is not None:
        return cli_value
    return config[key] if key in config else default


def apply_config(args: Any, defaults: dict[str, Any]) -> dict[str, Any]:
    """Populate None attributes on args from --config or defaults."""
    cfg = load_config(Path(args.config)) if getattr(args, "config", None) else {}
    for key, default in defaults.items():
        setattr(args, key, pick(getattr(args, key, None), cfg, key, default))
    return cfg
