"""Persistence adapters and repositories for context views, batch memoization and SQLite TM."""
from __future__ import annotations

from .context_views import BlindContextAdapter, WriterContextAdapter
from .memo_store import AtomicJsonMemoRepository, BatchMemo
from .sqlite_tm import (
    CANDIDATE_POOL, DEFAULT_MIN_SIMILARITY, DEFAULT_TOP, MAX_QUERY_GRAMS, SCHEMA, STATUSES,
    SqliteTMRepository, TranslationMemory, dice, normalize, trigrams,
)

__all__ = [
    "AtomicJsonMemoRepository",
    "BatchMemo",
    "BlindContextAdapter",
    "CANDIDATE_POOL",
    "DEFAULT_MIN_SIMILARITY",
    "DEFAULT_TOP",
    "MAX_QUERY_GRAMS",
    "SCHEMA",
    "STATUSES",
    "SqliteTMRepository",
    "TranslationMemory",
    "WriterContextAdapter",
    "dice",
    "normalize",
    "trigrams",
]
