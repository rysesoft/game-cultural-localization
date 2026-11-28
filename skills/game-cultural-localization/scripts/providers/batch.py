"""Facade delegating providers.batch symbols to gcl.infrastructure.providers.batch_* modules."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcl.domain.errors import BatchJobError  # noqa: E402
from gcl.infrastructure.providers.batch_backends import (  # noqa: E402
    BACKENDS, GOOGLE_BATCH_MAX_OUTPUT, AnthropicBatchBackend, GoogleBatchBackend, _Backend, _Pending, _google_inlined,
    _google_state,
)
from gcl.infrastructure.providers.batch_collector import (  # noqa: E402
    BATCH_PRICE_FACTOR, DEFAULT_LINGER_S, DEFAULT_POLL_S, DEFAULT_TIMEOUT_JOB_S, BatchCollector,
)

__all__ = [
    "AnthropicBatchBackend", "BACKENDS", "BATCH_PRICE_FACTOR", "BatchCollector", "BatchJobError",
    "DEFAULT_LINGER_S", "DEFAULT_POLL_S", "DEFAULT_TIMEOUT_JOB_S", "GOOGLE_BATCH_MAX_OUTPUT",
    "GoogleBatchBackend", "_Backend", "_Pending", "_google_inlined", "_google_state",
]
