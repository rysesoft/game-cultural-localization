"""Facade delegating providers.anthropic symbols to gcl.infrastructure.providers.adapters.anthropic_adapter."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcl.infrastructure.providers.adapters.anthropic_adapter import (  # noqa: E402
    ANTHROPIC_VERSION, AnthropicProvider, _int_or_none, assemble_stream,
)

__all__ = ["ANTHROPIC_VERSION", "AnthropicProvider", "_int_or_none", "assemble_stream"]
