# Changelog

All notable changes to this plugin are documented here. The version number lives in `plugin.json` only.

## [2.2.0] (in progress)

R&D release. Multi-family LLM jury, language packs and measured nativeness, see the work packages P1 to P15.

### Added
- `scripts/providers/` package with urllib adapters for Anthropic, Google Gemini and DeepSeek, a deterministic fake provider for tests and `--dry-run`, retry with exponential backoff for 429 and 5xx, a per provider rate limit, a model fallback on "not found" and a `budget.jsonl` line for every call (P1).
- `scripts/providers.config.json` with the verified model ids, prices, roles and the three jury tiers. Two members of one family in one tier is rejected (P1).
- `scripts/providers_check.py` validates the provider config and the API key environment variables and pings every model (P1).
- `scripts/build_language_pack.py` and `langpack/sources.manifest.json` build `langpack/<locale>/` (warm-up corpus, trust card, licenses, round-trip threshold) from licensed game and UI corpora and the studio reference translation, with a five-layer filter whose statistics land in `manifest.json`. Local class lines stay in the gitignored `local/` folder (P2).
- `scripts/llm_tasks.py` shared batched model tasks (translate, back-translate, jury scoring, pairwise choice) with one retry for missing keys (P2).
- `scripts/warmup_loader.py` seeded, register filtered and source balanced warm-up sample (30 to 50 lines) from a language pack, as a prompt block or JSON lines (P3).

## [2.1.0] — 2026-11-26

Audit-driven release (see `audit/00-OZET.md` for the finding numbers referenced below).

### Added
- `scripts/make_blind_slice.py`: deterministic blind-slice generator (key + context + target only, no source column) so the native-ear critique is actually blind (A2, E1).
- `scripts/validate_critique.py` and a fixed critique JSON schema (`critique_<locale>_<batch>.json`: naturalness `score` 1–5 + `issue_type` + `reason` + `suggested` + optional `needs_source_check`) (B18, C41).
- `scripts/CLI_REFERENCE.md` with every flag and the unified exit codes `0` clean / `1` findings / `2` usage or input error (B8, B9, C39).
- Five project-independent voice archetypes A1–A5 documented in `SKILL.md`; Golden Voice Anchors in all playbooks are tagged with them (B28, E9).
- Twelve-section playbook template shared by all 15 locales (plurals/ICU, UI glossary, placeholder grammar traps, typography, expansion, ratings) (A6, B26, B27, C34).
- Glossary/termbase format (`glossary.csv`: `term_en,<locale>…,notes`) enforced by `lqa_linter.py --glossary`; TM, string freeze, delta localization, regression, in-context LQA, pseudo-localization, and versioning/rollback sections in the methodology (04 §10).
- Transcreation ledger schema (CSV/JSON columns, example rows) and the duct-tape idiom table completed for all 15 locales (C37).
- `tests/` with stdlib `unittest` fixtures, `.gitignore`, `LICENSE` (MIT), this changelog (B20).
- README: Quick Start, official `agy plugin validate/install` commands, usage examples, CLI summary, input schema, engine support matrix, "Using outside Antigravity", Turkish quick-start (B21).

### Changed
- `agents/game-culturalizer.md`: tool list now includes `invoke_subagent`, `ask_question`, `search_web`, `read_url_content`; `skills:` binding; explicit Pass 1 / Pass 2 input and output contracts; consumes the fixed critique schema (A1, B18, C40).
- `agents/native-ear-critic.md`: read-only reviewer (`view_file` + a single `write_to_file` for the critique file, `commandExecutionPolicy: off`, `model: pro`); the "unless checking a factual bug" exception is gone — suspected factual issues are flagged with `needs_source_check` instead; two-axis rubric (A2, B17, C41).
- Canonical phase numbering everywhere: Phase 0 pre-flight, 1 clean-room Pass 1, 2 blind critique + Pass 2, 3 automated gate; the workflow template (renamed `localization_pipeline_template.workflow.py`) and the new API-independent `orchestrator_stub.py` use the same names and include Phase 0 and the LQA gate; bible file is `<LOCALE>_BIBLE.md` (B15, B19).
- Methodology runbook: per-phase inputs/outputs and measurable gate criteria; blind slice step with a concrete command; `--fail-on-error` / `--fail-on-high` / `--json` in every gate command; engine-independent wording with Unity/Unreal/Godot notes separated (A5, 04 §6).
- `rules/AGENTS.md`: current script names, mandatory blind slice, exit-code semantics.
- `plugin.json`: `$schema`, `license`, `keywords`, description shortened to 157 characters, version 2.1.0 (C40).
- `SKILL.md`: progressive-disclosure map lists the new scripts; the Unity claim now reads "Unity Localization StringTable `.asset` string extraction" and matches the linter (B16); 8 Laws aligned with the blind-slice/critique schema and exit codes.
- All project-specific names (characters, items, class names) removed from agent prompts, methodology, and ledger examples; generic roles and items are used instead (B28, 02 §3.6).

### Fixed
- Linter and checker crashes / silent passes addressed in `scripts/` (UTF-8 console output, BOM-tolerant input, unknown locale → exit 2, CJK word-boundary regexes, printf false positives, rich-text tag set, per-locale expansion ratios, `.ttc` fonts) — see `audit/01-scripts.md` for the full list (A3–A5, B7–B14, C38, C42).

## [2.0.0] — 2026-11-25

- Initial public structure: 15 locale playbooks with Golden Voice Anchors, `game-culturalizer` and `native-ear-critic` agents, `lqa_linter.py`, `ui_expansion_checker.py`, `font_glyph_scanner.py`, `run_workflow` pipeline template.
