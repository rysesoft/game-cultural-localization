"""Facade delegating providers.google symbols to gcl.infrastructure.providers.adapters.google_adapter."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcl.infrastructure.providers.adapters.google_adapter import GoogleProvider, assemble_stream  # noqa: E402

__all__ = ["GoogleProvider", "assemble_stream"]
