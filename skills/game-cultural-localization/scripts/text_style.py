#!/usr/bin/env python3
"""House punctuation style facade delegating to gcl.domain.house_style (not a CLI)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcl.domain.house_style import FORBIDDEN_CHARS, prose_only, punctuation_problems, sanitize_prose  # noqa: E402,F401

__all__ = ["FORBIDDEN_CHARS", "prose_only", "punctuation_problems", "sanitize_prose"]
