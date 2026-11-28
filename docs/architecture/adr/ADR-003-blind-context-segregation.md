# ADR 003. Blind Context Segregation and Uniform Vendor Replies

## Context

Two real bugs came from weak abstractions. First, `ContextPack` served both writers and blind jurors via a boolean `writer` flag, risking silent source leaks when `.jury` files were missing. Second, `HttpProvider._parse` accepted either a 3 tuple or a 5 tuple, causing `GoogleProvider` to drop cache read tokens silently.

## Decision

Split context access into two unrelated `Protocol` interfaces (`BlindContextView` vs `WriterContextView`) enforced by AST contract tests in `tests/test_architecture_contracts.py`. Require every `VendorTransportAdapter` to return a single uniform `RawVendorReply(text, usage, finish_reason)` value object.

## Consequences

Jury, deliberation and blind picker modules cannot access writer notes or locale appendices at the type or AST import boundary, and every vendor adapter reports cache tokens uniformly.
