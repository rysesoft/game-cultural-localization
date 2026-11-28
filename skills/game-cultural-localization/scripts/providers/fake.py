"""Facade delegating providers.fake symbols to gcl.infrastructure.providers.adapters.fake_adapter."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcl.infrastructure.providers.adapters.fake_adapter import LITERAL_MARK, FakeProvider, FakeScenario  # noqa: E402

__all__ = ["FakeProvider", "FakeScenario", "LITERAL_MARK"]
