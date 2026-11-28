"""Batched LLM task execution built on Template Method and AOP TaskAspect."""

from .base_task import KeyedBatchTask, KeyedCallSpec, call_keyed
from .concrete_tasks import (
    BacktranslateTask, BlindPickTask, DeliberateManyTask, JuryScoreTask, PairwiseChoiceTask, Pass2CandidateTask,
    TranslateTask, backtranslate_rows, pass2_candidates, pairwise_choices, pick_candidates, revote, revote_many,
    score_entries, translate_rows,
)
from .prompts import (
    BATCH_CHARS, BATCH_ROWS, BATCH_WORKERS, DEFAULT_SYSTEM, EVERYDAY_CAP, EVERYDAY_CHECK, EVERYDAY_MIN_JURORS,
    INSTRUCTIONS, ISSUE_TYPES, KEYED_ATTEMPTS, REGISTERS, SPLIT_DEPTH, chunked, chunked_budget, ordered_unique,
    primes, system_for, word_count,
)
from .vote_codec import everyday_check, everyday_rule, normalize_vote

__all__ = [
    "BATCH_CHARS", "BATCH_ROWS", "BATCH_WORKERS", "BacktranslateTask", "BlindPickTask", "DEFAULT_SYSTEM",
    "DeliberateManyTask", "EVERYDAY_CAP", "EVERYDAY_CHECK", "EVERYDAY_MIN_JURORS", "INSTRUCTIONS", "ISSUE_TYPES",
    "JuryScoreTask", "KEYED_ATTEMPTS", "KeyedBatchTask", "KeyedCallSpec", "PairwiseChoiceTask", "Pass2CandidateTask",
    "REGISTERS", "SPLIT_DEPTH", "TranslateTask", "backtranslate_rows", "call_keyed", "chunked", "chunked_budget",
    "everyday_check", "everyday_rule", "normalize_vote", "ordered_unique", "pass2_candidates", "pairwise_choices",
    "pick_candidates", "primes", "revote", "revote_many", "score_entries", "system_for", "translate_rows",
    "word_count",
]
