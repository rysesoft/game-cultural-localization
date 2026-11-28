# Codebase Navigation Map

Generated automatically by `scripts/dev/sync_navigation.py`. Never edit manually.

## Architecture Quick Rules

- Read `ARCHITECTURE_MEMORY.md` before changing layer boundaries or design patterns.
- Core logic lives inside `skills/game-cultural-localization/scripts/gcl/`.
- Top level `scripts/*.py` files remain stable CLI and compatibility facades.
- Run `python skills/game-cultural-localization/scripts/dev/verify_architecture.py` after every edit.

## Core Layers (`scripts/gcl/`)

| Layer | Module | Pattern | Lines | Classes | Responsibility |
|---|---|---|---|---|---|
| `domain` | [envelope_codec.py](../../skills/game-cultural-localization/scripts/gcl/domain/envelope_codec.py) | Codec Helper | 67 | - | prompt envelopes, tolerant JSON extraction, prompt hashes and token estimation |
| `domain` | [errors.py](../../skills/game-cultural-localization/scripts/gcl/domain/errors.py) | Domain Exceptions | 39 | `L10nError`, `ProviderError`, `ModelNotFoundError`, `StreamInterrupted`, `BatchJobError` ... | exit codes, version string and core exception hierarchy |
| `domain` | [house_style.py](../../skills/game-cultural-localization/scripts/gcl/domain/house_style.py) | Pure Domain Policy | 61 | - | house punctuation verification and prose sanitization |
| `domain` | [line_state.py](../../skills/game-cultural-localization/scripts/gcl/domain/line_state.py) | State | 71 | `LineState`, `DraftedState`, `SettledPassState`, `FlaggedForRewriteState`, `RewrittenState` ... | line lifecycle states eliminating ambiguous rewrite counters |
| `domain` | [lint_models.py](../../skills/game-cultural-localization/scripts/gcl/domain/lint_models.py) | Value Objects | 41 | `Rule`, `LintOptions` | Rule, LintOptions and context tag constants shared across infrastructure and application |
| `domain` | [locales.py](../../skills/game-cultural-localization/scripts/gcl/domain/locales.py) | Value Object and Registry | 86 | `LocaleSpec` | canonical locales, alias normalization, plural counts and expansion factors |
| `domain` | [models.py](../../skills/game-cultural-localization/scripts/gcl/domain/models.py) | Value Objects | 136 | `Row`, `PlaceholderSet`, `Tag`, `GlossaryTerm`, `Finding` ... | rows, tokens, findings, risks, votes and typed LLM messages |
| `domain` | [specifications.py](../../skills/game-cultural-localization/scripts/gcl/domain/specifications.py) | Specification | 137 | `Specification`, `CriticalVoteSpec`, `MinScoreSpec`, `MaxSpreadSpec`, `TierPassSpec` ... | composable boolean rules for jury agreement, everyday cap and rule scoping |
| `ports` | [context.py](../../skills/game-cultural-localization/scripts/gcl/ports/context.py) | Interface Segregation | 40 | `BlindContextView`, `WriterContextView` | blind juror context port vs writer context port |
| `ports` | [events.py](../../skills/game-cultural-localization/scripts/gcl/ports/events.py) | Observer | 68 | `DomainEvent`, `LLMCallObserved`, `FallbackSwitched`, `StageCompleted`, `EventSubscriber` ... | domain event types and event bus interface |
| `ports` | [formats.py](../../skills/game-cultural-localization/scripts/gcl/ports/formats.py) | Strategy Ports | 90 | `TableLoadOptions`, `ExportResult`, `TableFormatStrategy`, `PlaceholderStrategy`, `TagStrategy` ... | table format, token parser and lint handler protocols |
| `ports` | [llm.py](../../skills/game-cultural-localization/scripts/gcl/ports/llm.py) | Port Interface | 47 | `ProviderCapabilities`, `LLMClient`, `VendorTransportAdapter` | LLM client, vendor transport adapter and capability contracts |
| `ports` | [pipeline.py](../../skills/game-cultural-localization/scripts/gcl/ports/pipeline.py) | Port Interface | 60 | `PromptTemplatePort`, `CritiqueValidatorPort`, `BlindSlicePort`, `FontScannerPort` | prompt, slice, validation, roundtrip, report and font scanner ports |
| `ports` | [storage.py](../../skills/game-cultural-localization/scripts/gcl/ports/storage.py) | Repository Ports | 63 | `TMQuery`, `TMSegment`, `MemoRepository`, `TMReader`, `TMWriter` | memoization repository, TM parameter objects and segregated TM ports |
| `aspects` | [call_chain.py](../../skills/game-cultural-localization/scripts/gcl/aspects/call_chain.py) | Decorator and Interceptor (AOP) | 109 | `CallAspect`, `SecretRedactionAspect`, `OfflineGuardAspect`, `BudgetTelemetryAspect`, `FallbackModelAspect` ... | composable CallAspect pipeline for telemetry, fallback, secret scrub and offline guard |
| `aspects` | [event_bus.py](../../skills/game-cultural-localization/scripts/gcl/aspects/event_bus.py) | Observer EventBus | 81 | `InMemoryEventBus`, `BudgetLog`, `BudgetLogSubscriber` | domain event publishing, budget JSONL persistence and call metrics aggregation |
| `aspects` | [task_chain.py](../../skills/game-cultural-localization/scripts/gcl/aspects/task_chain.py) | Decorator and Interceptor (AOP) | 68 | `TaskAspect`, `MemoizationTaskAspect` | memoization, cache priming and parallel execution around batched tasks |
| `application` | [lint_chain.py](../../skills/game-cultural-localization/scripts/gcl/application/gates/lint_chain.py) | Chain of Responsibility | 197 | `LintRowContext`, `EmptyTargetCheck`, `PoMetadataCheck`, `EncodingCheck`, `PunctuationBanCheck` ... | composable per row LintCheck handlers preserving deterministic finding order |
| `application` | [lint_rules.py](../../skills/game-cultural-localization/scripts/gcl/application/gates/lint_rules.py) | Specification Bridge | 58 | - | deriving row context tags and matching Rules via RuleAppliesSpec |
| `application` | [deliberation.py](../../skills/game-cultural-localization/scripts/gcl/application/jury/deliberation.py) | Domain Service | 196 | - | vendor name anonymization, target only evidence packaging and J3 deliberation voting |
| `application` | [escalation_chain.py](../../skills/game-cultural-localization/scripts/gcl/application/jury/escalation_chain.py) | Chain of Responsibility | 258 | `JuryBatchContext`, `TierHandler`, `J1TierHandler`, `J2TierHandler`, `RoundtripEnricherHandler` ... | tiered mixed family jury voting, budget cap enforcement and deliberation dispatch |
| `application` | [policy.py](../../skills/game-cultural-localization/scripts/gcl/application/jury/policy.py) | Specification Policy | 59 | `EscalationTally` | J1-J3 agreement evaluation, EscalationTally and source free juror_view |
| `application` | [builder.py](../../skills/game-cultural-localization/scripts/gcl/application/pipeline/builder.py) | Builder | 238 | `LocalizationPipelineBuilder` | stepwise Phase 0 to Phase 3 pipeline assembly with clean teardown |
| `application` | [config.py](../../skills/game-cultural-localization/scripts/gcl/application/pipeline/config.py) | Parameter Object and Port Hooks | 92 | `PipelineState`, `JuryPipelineOptions`, `PipelineHooks` | PipelineState, JuryPipelineOptions and injected PipelineHooks dataclasses |
| `application` | [stages.py](../../skills/game-cultural-localization/scripts/gcl/application/pipeline/stages.py) | Stage Helpers | 105 | - | Pass 1 RAG payload assembly, token parity escalation guard and batch artifact writing |
| `application` | [tournament.py](../../skills/game-cultural-localization/scripts/gcl/application/rewrite/tournament.py) | State and Segregated Tournament | 265 | `TournamentOptions`, `Pass2Tournament` | Pass 2 candidate writing, blind J1 candidate selection, validation and J1 confirmation recheck |
| `application` | [base_task.py](../../skills/game-cultural-localization/scripts/gcl/application/tasks/base_task.py) | Template Method | 131 | `KeyedCallSpec`, `KeyedBatchTask` | missing key re-ask loop, binary half split retry and KeyedBatchTask base |
| `application` | [concrete_tasks.py](../../skills/game-cultural-localization/scripts/gcl/application/tasks/concrete_tasks.py) | Concrete Template Methods | 246 | `TranslateTask`, `BacktranslateTask`, `JuryScoreTask`, `PairwiseChoiceTask`, `DeliberateManyTask` ... | pass1, literal, roundtrip, jury, pairwise, revote, pass2 and blind pick task classes |
| `application` | [prompts.py](../../skills/game-cultural-localization/scripts/gcl/application/tasks/prompts.py) | Policy Constants and Chunking | 155 | - | task system prompts, everyday word rules, batch row/char budgets and chunking |
| `application` | [vote_codec.py](../../skills/game-cultural-localization/scripts/gcl/application/tasks/vote_codec.py) | Domain Policy Bridge | 70 | - | raw vote normalization, odd word verification and everyday tier score cap |
| `infrastructure` | [cli_support.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/cli_support.py) | CLI Facade Support | 82 | - | unified argparse options, input resolution, JSON/text emission and error trapping |
| `infrastructure` | [critique_validator.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/critique_validator.py) | Validator and Port Adapter | 173 | `CritiqueValidationContext`, `DefaultCritiqueValidatorAdapter` | critique schema checking, slice loading and CritiqueValidatorPort implementation |
| `infrastructure` | [csv_format.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/csv_format.py) | Strategy | 75 | `CsvTableFormat` | CSV and TSV localization reading and BOM preserving export |
| `infrastructure` | [export_decisions.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/export_decisions.py) | Export Service | 126 | - | final batch loading, developer decision application and parity hold back |
| `infrastructure` | [glossary.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/glossary.py) | Repository Helper | 92 | - | loading wide or long glossary CSVs and validating term consistency |
| `infrastructure` | [io_utils.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/io_utils.py) | IO Helpers | 89 | - | BOM tolerant text reading, JSON parsing, delimiter sniffing and game root detection |
| `infrastructure` | [json_format.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/json_format.py) | Strategy | 92 | `JsonTableFormat` | JSON list and map localization table reading and exporting |
| `infrastructure` | [lint_rules_io.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/lint_rules_io.py) | Rule Loader | 112 | - | parsing, compiling and deduplicating locale LQA JSON rule files |
| `infrastructure` | [po_format.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/po_format.py) | Strategy | 144 | `PoTableFormat` | gettext PO parsing with plurals, fuzzy and msgctxt plus clean export |
| `infrastructure` | [project_config.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/project_config.py) | Configuration Loader | 59 | - | l10n.config.json schema validation and CLI override resolution |
| `infrastructure` | [registry.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/registry.py) | Registry | 75 | `UnityTableFormat`, `TableFormatRegistry` | OCP table format registry for reading and writing localized tables |
| `infrastructure` | [unity_yaml_reader.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/unity_yaml_reader.py) | YAML Asset Reader | 175 | - | Unity StringTable parsing, YAML scalar folding and AssetTable detection |
| `infrastructure` | [unity_yaml_writer.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/formats/unity_yaml_writer.py) | Strategy | 242 | - | strict YAML serialization and minimal diff Unity StringTable rewriting |
| `infrastructure` | [paths.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/paths.py) | Configuration Path Registry | 18 | - | canonical plugin directory and scripts path resolution |
| `infrastructure` | [context_views.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/persistence/context_views.py) | Interface Segregation Adapter | 53 | `BlindContextAdapter`, `WriterContextAdapter` | physically separate blind juror vs writer context adapters |
| `infrastructure` | [memo_store.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/persistence/memo_store.py) | Repository | 60 | `AtomicJsonMemoRepository` | atomic JSON file persistence for batch memoization and resume |
| `infrastructure` | [sqlite_tm.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/persistence/sqlite_tm.py) | Repository | 188 | `SqliteTMRepository` | SQLite translation memory storage and character n-gram neighbor lookup |
| `infrastructure` | [anthropic_adapter.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/adapters/anthropic_adapter.py) | Adapter | 96 | `AnthropicProvider` | Anthropic Claude Messages API request formatting, SSE reassembly and cache telemetry |
| `infrastructure` | [deepseek_adapter.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/adapters/deepseek_adapter.py) | Adapter | 86 | `DeepSeekProvider` | DeepSeek chat/completions formatting, SSE reassembly and cache hit usage |
| `infrastructure` | [fake_adapter.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/adapters/fake_adapter.py) | Mock Adapter | 211 | `FakeScenario`, `FakeProvider` | scenario driven offline FakeScenario and FakeProvider |
| `infrastructure` | [google_adapter.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/adapters/google_adapter.py) | Adapter | 97 | `GoogleProvider` | Gemini streamGenerateContent request formatting and full TokenUsage including cache reads |
| `infrastructure` | [legacy_adapter.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/adapters/legacy_adapter.py) | Adapter | 44 | `LegacyAdapter`, `FromLegacy` | bidirectional adaptation between LLMClient and legacy string callable providers |
| `infrastructure` | [batch_backends.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/batch_backends.py) | Bridge | 238 | `PendingCall`, `AnthropicBatchBackend`, `GoogleBatchBackend` | vendor specific async batch submission, polling, cancellation and result parsing |
| `infrastructure` | [batch_collector.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/batch_collector.py) | Proxy and Coalescing Collector | 140 | `BatchCollector` | concurrent call queueing, linger flushing and background polling for batch APIs |
| `infrastructure` | [config.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/config.py) | Configuration Validator | 211 | `ModelSpec`, `ProvidersConfig` | providers.config.json loading, ModelSpec definitions and schema checks |
| `infrastructure` | [envelope.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/envelope.py) | Facade Re Export | 20 | - | backward compatible re exports of gcl.domain.envelope_codec |
| `infrastructure` | [factory.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/factory.py) | Factory and Proxy with AOP Interceptors | 211 | `Member`, `RoleProvider`, `Router` | RoleProvider, Member and Router wiring VendorRegistry, batching and EventBus telemetry |
| `infrastructure` | [http_transport.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/http_transport.py) | Template HTTP Transport | 238 | `HttpRequestOptions`, `HttpProvider` | urllib GET/POST execution, SSE event assembly and retry loop |
| `infrastructure` | [rate_limiter.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/rate_limiter.py) | Rate Limiter Registry | 102 | `RateLimiter` | RPS throttling, 429 and 5xx backoff schedules, key redaction and model error matching |
| `infrastructure` | [vendor_registry.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/providers/vendor_registry.py) | Registry and Abstract Factory | 109 | `VendorDescriptor`, `VendorRegistry` | pluggable vendor adapter, batch backend and option builder registration |
| `infrastructure` | [parity_adapter.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/tokens/parity_adapter.py) | Port Adapter | 32 | `DefaultTokenParityAdapter` | DefaultTokenParityAdapter bridging domain/application lint & rewrite to token parsers |
| `infrastructure` | [placeholders.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/tokens/placeholders.py) | Strategy and Registry | 158 | `ConfiguredPlaceholderStrategy`, `PlaceholderRegistry` | pluggable placeholder parsing for unity, unreal, godot, icu, printf and python |
| `infrastructure` | [rich_tags.py](../../skills/game-cultural-localization/scripts/gcl/infrastructure/tokens/rich_tags.py) | Strategy and Registry | 185 | `ConfiguredTagStrategy`, `TagRegistry` | TMP, HTML and BBCode rich text tag strategies plus East Asian visual width |
| `composition` | [cli_wiring.py](../../skills/game-cultural-localization/scripts/gcl/composition/cli_wiring.py) | Composition Root | 50 | - | CLI model router construction, batch worker scaling and budget path defaults |
| `composition` | [container.py](../../skills/game-cultural-localization/scripts/gcl/composition/container.py) | Service Container | 53 | `ServiceContainer` | dependency injection wiring for tokens, critique validation, TM, memo and context views |

## CLI and Compatibility Facades (`scripts/`)

| Script | Lines | Role |
|---|---|---|
| [budget_report.py](../../skills/game-cultural-localization/scripts/budget_report.py) | 242 | Token, call, latency and cost report from budget.jsonl, with a projection to a full project. |
| [build_context_map.py](../../skills/game-cultural-localization/scripts/build_context_map.py) | 1909 | Context map facts. Where every localization key of a game project is used. |
| [build_contrastive_set.py](../../skills/game-cultural-localization/scripts/build_contrastive_set.py) | 165 | Build the contrastive set (native, robot, unknown) of a language pack from a professional reference table. |
| [build_language_pack.py](../../skills/game-cultural-localization/scripts/build_language_pack.py) | 818 | Build a language asset pack langpack/<locale>/ from licensed corpora with a five-layer trust filter. |
| [deliberate.py](../../skills/game-cultural-localization/scripts/deliberate.py) | 115 | J3 deliberation round CLI facade delegating to gcl.application.jury.deliberation. |
| [eval_critic.py](../../skills/game-cultural-localization/scripts/eval_critic.py) | 379 | Calibrate the jury members against the contrastive set (native vs robot lines). |
| [export_translations.py](../../skills/game-cultural-localization/scripts/export_translations.py) | 148 | Final translations exporter CLI Facade delegating to TableFormatRegistry and export services. |
| [font_glyph_scanner.py](../../skills/game-cultural-localization/scripts/font_glyph_scanner.py) | 841 | Font missing-glyph ('tofu' box) and full width fallback scanner for localized string tables. |
| [jury.py](../../skills/game-cultural-localization/scripts/jury.py) | 249 | Tiered mixed-family jury CLI facade delegating to gcl.application.jury. |
| [l10n_common.py](../../skills/game-cultural-localization/scripts/l10n_common.py) | 64 | Backward compatible Facade over gcl.domain and gcl.infrastructure format/token modules. |
| [llm_tasks.py](../../skills/game-cultural-localization/scripts/llm_tasks.py) | 156 | Facade delegating batched LLM tasks and model routing helpers to gcl layers. |
| [lqa_linter.py](../../skills/game-cultural-localization/scripts/lqa_linter.py) | 154 | Multi-language LQA linter CLI facade delegating to gcl.application.gates and gcl.infrastructure. |
| [make_blind_slice.py](../../skills/game-cultural-localization/scripts/make_blind_slice.py) | 171 | Create a target-only "blind slice" for the native-ear critic. |
| [orchestrator_stub.py](../../skills/game-cultural-localization/scripts/orchestrator_stub.py) | 451 | API-independent orchestration CLI facade delegating to gcl.application.pipeline & gcl.composition. |
| [pass2_rewrite.py](../../skills/game-cultural-localization/scripts/pass2_rewrite.py) | 176 | Pass 2 candidate tournament CLI facade delegating to gcl.application.rewrite. |
| [prompt_templates.py](../../skills/game-cultural-localization/scripts/prompt_templates.py) | 100 | Load and render the prompt templates in prompts/ (not a CLI). |
| [providers_check.py](../../skills/game-cultural-localization/scripts/providers_check.py) | 98 | Validate providers.config.json, the API key environment variables and (optionally) ping every model. |
| [report_changes.py](../../skills/game-cultural-localization/scripts/report_changes.py) | 311 | Developer report of a jury + Pass 2 batch. what changes, why, on what evidence, how sure (B3.8). |
| [roundtrip_check.py](../../skills/game-cultural-localization/scripts/roundtrip_check.py) | 232 | Back-translation sniff test. does a translated dialogue line still carry the English skeleton? |
| [text_style.py](../../skills/game-cultural-localization/scripts/text_style.py) | 12 | House punctuation style facade delegating to gcl.domain.house_style (not a CLI). |
| [tm.py](../../skills/game-cultural-localization/scripts/tm.py) | 166 | SQLite translation memory CLI facade delegating storage to gcl.infrastructure.persistence.sqlite_tm. |
| [ui_expansion_checker.py](../../skills/game-cultural-localization/scripts/ui_expansion_checker.py) | 237 | UI button / tab / badge text-expansion overflow detector. |
| [validate_critique.py](../../skills/game-cultural-localization/scripts/validate_critique.py) | 64 | Critique schema validation CLI facade delegating to gcl.infrastructure.formats.critique_validator. |
| [warmup_loader.py](../../skills/game-cultural-localization/scripts/warmup_loader.py) | 189 | Deterministic warm-up ("ear warming") sampler for a language pack. |

## Developer and Governance Scripts (`scripts/dev/`)

- `sync_navigation.py` regenerates this map from module AST headers and checks drift with `--check`.
- `verify_architecture.py` enforces layer imports, cycle freedom, blindness lock, OCP locks, Clean Code bounds and house style.
- `hook_runner.py` integrates `SessionStart` memory briefings and `Stop` verification with Antigravity `.agents/hooks.json`.
