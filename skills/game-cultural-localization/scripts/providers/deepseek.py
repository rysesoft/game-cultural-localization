"""Facade delegating providers.deepseek symbols to gcl.infrastructure.providers.adapters.deepseek_adapter."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcl.infrastructure.providers.adapters.deepseek_adapter import DeepSeekProvider, assemble_stream  # noqa: E402

__all__ = ["DeepSeekProvider", "assemble_stream"]
