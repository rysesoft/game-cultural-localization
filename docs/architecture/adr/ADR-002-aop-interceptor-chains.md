# ADR 002. Zero Dependency AOP Interceptor Chains

## Context

Retry loops, rate limiting, secret redaction, model fallback, budget telemetry, cache priming, batch memoization and binary split recovery were duplicated or scattered across `providers/base.py`, `providers/__init__.py` and `llm_tasks.py`.

## Decision

Model cross cutting concerns as composable Python interceptor chains without third party libraries. `CallAspect` wraps `VendorTransportAdapter` calls inside `AspectClient` (logging, fallback, batch coalescing, rate limiting, retry, secret redaction, offline guard). `TaskAspect` wraps `KeyedBatchTask` batch runs (`MemoizationTaskAspect`, `CachePrimingTaskAspect`, `BinarySplitRecoveryAspect`).

## Consequences

New cross cutting features (such as per role thinking effort or item level memoization in v3.2) attach as isolated aspect classes with zero edits to jury, rewrite or adapter business logic.
