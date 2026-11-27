# Changelog

All notable changes to this plugin are documented here. The version number lives in `plugin.json` and `scripts/l10n_common.py`.

## [Unreleased]

### Added
- Prompt caching for Claude. Anthropic caches only on request (checked live, no marker meant no cache), so `providers/anthropic.py` sends the system prompt as one block with `cache_control`. Live through the plugin the second jury call of a run read 4178 of 4396 prompt tokens from the cache and its cost fell from $0.00066 to $0.00017. DeepSeek caches on its own (3072 of 3321 tokens on the second call), Gemini 4 showed no hits in twelve live calls even at 7700 tokens. `ChatResult`, the budget log and `budget_report.py` carry the cache read and write tokens, priced with the new `price_cache_read` and `price_cache_write` fields of `providers.config.json`.
- Native critic and Pass 2 prompts for the remaining 13 locales (`en`, `fr`, `es-ES`, `it-IT`, `pt-BR`, `pt-PT`, `pl-PL`, `lt-LT`, `ru-RU`, `ja-JP`, `ko-KR`, `zh-CN`, `zh-Hant`), each written in its own language with a local player or writer persona, so every locale now has `prompts/critic.<locale>.md` and `prompts/pass2.<locale>.md`. The English generic prompts stay as a fallback for locales a project adds.
- The KDE source of `langpack/sources.manifest.json` lists the Turkish and German translations of five KDE games (KPatience, KMines, KNavalBattle, KSudoku, KBounce), pinned to a Subversion revision.
- `text_style.punctuation_problems(..., exempt_examples=True)` checks explanations while quoted, italic and non-Latin target-language examples keep their own punctuation.

- `lqa_linter` rules take `skip_contexts`, and rows have a new `formal` context (formal register, in-world news, codex lore, from the category or a `Codex`, `Lore` or `News` key segment).
- `langpack/tr-TR/contrastive.json`, 1084 live contrastive pairs built from the Rysesoft reference. Each pair holds the English source, the studio's Turkish line (native), a deliberately literal `deepseek-flash` line (robot) and a raw `claude-sonnet-5-5` translation (unknown). 456 rows were left out because the literal line equals the studio line.
- `README_TR.md`, the full Turkish README. Both READMEs link each other and `test_docs_style.py` checks that their sections and code blocks stay in step.
- `langpack/tr-TR/` is built with the studio's professional reference (`loc_work/reference/tr.csv`, kept out of git), so its warm-up lines include about 1400 lines of the studio's own human translation.

### Changed
- The jury flow runs its model calls in parallel. `jury.py`, `pass2_rewrite.py` and `orchestrator_stub.py` take `--workers` (default 4). The three members of a tier, the disputed lines of the deliberation round and the three Pass 2 pickers run side by side, and every batched step sends several batches at once. Tests check that one and four workers give the same verdicts, rewrites and files. Measured sequential, Pass 1 alone took 14 minutes for 1540 lines and the jury would have taken about an hour per language.
- `scripts/eval_critic.py` calibrates the jury members in parallel. `--workers` (default 4) sets the batches in flight per model, and every distinct model runs in its own thread. The report is identical for every worker count. A live 60 pair J1 trial took 13 minutes one call at a time. The batched tasks in `llm_tasks.py` take the same `workers` argument, default 1. The calibration result in `trust_card.json` and the `source_ref` of `contrastive.json` name their source file without a local path.
- The 15 playbooks, the transcreation ledger guide, both agents and `rules/AGENTS.md` follow the house punctuation style in their explanations. Target-language examples are unchanged.
- README opens with the problem (typical LLM output next to native text), then the three layers that fix it, the jury with its agreement rules, budget caps and trust levels, and the Turkish language pack. The short Turkish summary moved into `README_TR.md`.
- `scripts/build_language_pack.py` keeps reference lines that fail the length ratio or hit a ban list rule, the professional translation wins over the heuristics. These lines are listed in `manifest.json` under `layer2_mechanical.reference_exempt` and counted in the report.
- `tr-TR` rules follow the studio reference. `TR-PRONOUN-SPAM` (sentence-initial "Sen/Senin") checks UI text only, an emphatic "Sen" stays free in dialogue and letters. `TR-MAKTADIR` and `TR-SAHIP-OLMAK` skip formal text, news and codex lore, where report style is the native voice.
- The register names `dialogue_casual` and `dialogue_formal` count as dialogue for rule contexts, so jury evidence and the pack filter see dialogue rows as dialogue.

### Fixed
- The first full live calibration was stopped after `deepseek-v4-pro` sent one reply without choices, which would have ended the run and lost every finished model. Batched tasks now re-ask up to three times in total and count such a reply as a failed attempt. `eval_critic.py --cache FILE` keeps every finished model, a failing model no longer throws away the others, and the same command resumes with the missing models only. Gemini and DeepSeek ask for at least 32000 output tokens, since `gemini-4-carbon` and `deepseek-v4-pro` hit the 16000 ceiling on 40 line batches.
- Every provider adapter asks for at least 16000 output tokens (`providers/base.py` `MIN_MAX_TOKENS`), because current models of all three families think first and the thinking counts against the limit. In the first live run DeepSeek used a 4096 limit for thinking alone and returned no text. The HTTP timeout is 600 seconds instead of 120 so long answers are not cut off. `providers.config.json` turns DeepSeek thinking off for the mechanical `literal` and `roundtrip` roles, jurors keep it.
- `providers/google.py` sends the key in the `x-goog-api-key` header instead of the `?key=` query, as in Google's own examples. This covers the auth keys AI Studio creates since May 2026 and keeps the key out of URLs and logs. `gemini-4-hydrogen` answered live, and the model list of the API confirms `gemini-4-neon` and `gemini-4-carbon`.
- `providers/anthropic.py` no longer sends `temperature`, which current Claude models reject with HTTP 400, and asks for at least 16000 `max_tokens` so adaptive thinking leaves room for the answer. Thinking blocks are skipped when the reply is read. Checked live against `claude-haiku-5-5`, `claude-sonnet-5-5` and `claude-opus-5-5`.
- The layer 1 report of `build_language_pack.py` counts the reference among the sources it read ("10 kept of 10" instead of "10 kept of 9").

## [2.2.0] 2026-11-26


R&D release. A multi-family LLM jury, language packs and measured nativeness, built in the work packages P1 to P15. Every model call can run offline with `--dry-run` (deterministic fake provider), the test suite never calls a real API.

### Added
- `scripts/providers/` package with urllib adapters for Anthropic, Google Gemini and DeepSeek, a deterministic fake provider for tests and `--dry-run`, retry with exponential backoff for 429 and 5xx, a per provider rate limit, a model fallback on "not found" and a `budget.jsonl` line for every call (P1).
- `scripts/providers.config.json` with the verified model ids, prices, roles and the three jury tiers. Two members of one family in one tier is rejected (P1).
- `scripts/providers_check.py` validates the provider config and the API key environment variables and pings every model (P1).
- `scripts/build_language_pack.py` and `langpack/sources.manifest.json` build `langpack/<locale>/` (warm-up corpus, trust card, licenses, round-trip threshold) from licensed game and UI corpora and the studio reference translation, with a five-layer filter whose statistics land in `manifest.json`. Local class lines stay in the gitignored `local/` folder (P2).
- `scripts/llm_tasks.py` shared batched model tasks (translate, back-translate, jury scoring, pairwise choice, deliberation re-vote, Pass 2 candidates, blind pick) with one retry for missing keys (P2).
- `scripts/warmup_loader.py` seeded, register filtered and source balanced warm-up sample (30 to 50 lines) from a language pack, as a prompt block or JSON lines (P3).
- `prompts/critic.tr-TR.md` and `prompts/critic.de-DE.md`, native critic prompts written in the target language with a player persona, warm-up and contrastive slots, rubric, task order and the vote schema. `prompts/literal.md` for robot lines and an English `prompts/critic.generic.md` fallback. `scripts/prompt_templates.py` renders them, `scripts/text_style.py` checks the house punctuation style (P4).
- `scripts/build_contrastive_set.py` writes `contrastive.json` (native, robot and unknown lines per reference row, B3.5). Robot lines come from the `literal` model with `prompts/literal.md`, unknown lines from the `pass1` model or `--unknown-models` (P5).
- `scripts/roundtrip_check.py` back-translation calque score (0 to 1) for dialogue lines over `min_words` words, `"applied": false` elsewhere, and `--calibrate` to derive `roundtrip_threshold.json` from the contrastive set (P6).
- `scripts/eval_critic.py` calibrates every jury member on the contrastive set. Seeded pairwise preference with the 0.85 phase A gate, absolute native, robot and unknown means, inter and intra family kappa, warm-up on and off compared in one command, result stored in the trust card (B3.6, P7).
- `scripts/budget_report.py` aggregates `budget.jsonl` by role, provider and model (calls, tokens, latency, cost from the config prices, "price not set" for null prices) and projects the cost to 20,000 lines in 15 locales (P8).
- `scripts/jury.py` tiered mixed-family jury (J1, J2, J3) over a blind slice with the A4 agreement rule, the critical shortcut to J3, budget caps that stop the run (30 % to J2, 10 % to J3), ban list, TM and back-translation evidence, B3.3 votes and B3.4 verdicts (P9).
- `scripts/deliberate.py` J3 deliberation round. Anonymous rationales (model and family names scrubbed), evidence package (ban hits, three approved TM lines, back-translation signal), one re-vote, majority decides, three different scores stay unresolved. `jury.py` runs it by default (`--no-deliberation` to skip) (P10).
- `scripts/tm.py` SQLite translation memory. Character trigram neighbours in category and speaker tiers (top 5), approved and candidate rows, approval flow back from change reports. `jury.py --tm` puts the closest approved lines into the evidence (P11).
- `scripts/pass2_rewrite.py` and `prompts/pass2.tr-TR.md`, `prompts/pass2.de-DE.md`, `prompts/pass2.generic.md`. The pass2 model writes three candidates per flagged line, the J1 members pick one blind (majority), and the pick is checked with `validate_critique` before it replaces the old line (P12).
- `scripts/report_changes.py` developer report `changes_<locale>_<batch>.json` and `.md` (B3.8) with trust level (A9), language pack version, budget summary, confidence per line, votes per tier, a decision field for `tm.py --mode approve` and an unresolved section with three rationales. The Markdown is checked against the house punctuation style (P13).
- `scripts/orchestrator_stub.py` jury flow. Phase 0 adds the trust level, warm-up and translation memory, Phase 1 uses the `pass1` model with warm-up and TM retrieval, Phase 2 runs blind slice, jury with deliberation, Pass 2 candidates with a blind J1 pick and the change report, Phase 3 keeps the gate (P14).
- Methodology section on the jury, deliberation, language packs and trust levels, SKILL.md map entries, a README section and a test that keeps README, SKILL.md, the methodology, CLI_REFERENCE, the test README and this changelog free of semicolons, dashes and sentence colons (P15).

### Changed
- `orchestrator_stub.py --dry-run` now runs the jury flow with the fake provider. `--live` runs it with the real APIs. The single critic flow of 2.1 stays available through `--provider module:function` and `run_pipeline(..., DryRunProvider(locale))`. Without one of the three modes the run stops with exit 2, so a real API is never called by accident (P14).
- README, SKILL.md, the methodology, CLI_REFERENCE and the test README follow the house punctuation style (P15).
- `.gitignore` covers `langpack/*/local/`, `langpack/.cache/`, `loc_work/`, `*.sqlite` and the R&D planning notes (P1, P2).
- Version 2.2.0 in `plugin.json` and `l10n_common.py` (P15).

### Known limits
- Native judgement for locales without a professional reference is an estimate (trust level `estimated`). Only tr-TR can be measured once the studio reference is in place.
- Open corpora are mostly translations themselves, so warm-up calibrates to good translation, not to original writing. Dialogue lines are rare in the bundled sources.
- Back-translation carries no signal for UI and short text. Self-preference of a model family is reduced by deliberation, not removed. Cultural errors are not caught by any proxy signal.
- Prices of Gemini 4 Hydrogen and Neon are not entered yet, budget projections that use them are lower bounds.
- Native critic and Pass 2 prompts exist for tr-TR and de-DE. The other 13 locales use the English fallback prompts.

## [2.1.0] 2026-11-26

Audit driven release (the finding numbers below refer to the audit notes kept outside the repository).

### Added
- `scripts/make_blind_slice.py`, a deterministic blind slice generator (key, context and target only, no source column) so the native ear critique is actually blind (A2, E1).
- `scripts/validate_critique.py` and a fixed critique JSON schema (`critique_<locale>_<batch>.json` with a naturalness `score` 1 to 5, `issue_type`, `reason`, `suggested` and the optional `needs_source_check`) (B18, C41).
- `scripts/CLI_REFERENCE.md` with every flag and the unified exit codes, `0` clean, `1` findings, `2` usage or input error (B8, B9, C39).
- Five project independent voice archetypes A1 to A5 documented in `SKILL.md`. Golden Voice Anchors in all playbooks are tagged with them (B28, E9).
- Twelve section playbook template shared by all 15 locales (plurals and ICU, UI glossary, placeholder grammar traps, typography, expansion, ratings) (A6, B26, B27, C34).
- Glossary and termbase format (`glossary.csv` with `term_en,<locale>...,notes`) enforced by `lqa_linter.py --glossary`. TM, string freeze, delta localization, regression, in-context LQA, pseudo localization and versioning and rollback sections in the methodology (04 §10).
- Transcreation ledger schema (CSV and JSON columns, example rows) and the duct tape idiom table completed for all 15 locales (C37).
- `tests/` with stdlib `unittest` fixtures, `.gitignore`, `LICENSE` (MIT) and this changelog (B20).
- README with a quick start, the official `agy plugin validate` and `agy plugin install` commands, usage examples, CLI summary, input schema, engine support matrix, use outside Antigravity and a Turkish quick start (B21).

### Changed
- `agents/game-culturalizer.md`. The tool list now includes `invoke_subagent`, `ask_question`, `search_web` and `read_url_content`, with a `skills:` binding, explicit Pass 1 and Pass 2 input and output contracts, and the fixed critique schema as input (A1, B18, C40).
- `agents/native-ear-critic.md` is a read only reviewer (`view_file` plus a single `write_to_file` for the critique file, `commandExecutionPolicy: off`, `model: pro`). The "unless checking a factual bug" exception is gone, suspected factual issues are flagged with `needs_source_check` instead. Two axis rubric (A2, B17, C41).
- Canonical phase numbering everywhere. Phase 0 pre-flight, 1 clean room Pass 1, 2 blind critique and Pass 2, 3 automated gate. The workflow template (renamed `localization_pipeline_template.workflow.py`) and the new API independent `orchestrator_stub.py` use the same names and include Phase 0 and the LQA gate. The bible file is `<LOCALE>_BIBLE.md` (B15, B19).
- Methodology runbook with per phase inputs and outputs and measurable gate criteria, a blind slice step with a concrete command, `--fail-on-error`, `--fail-on-high` and `--json` in every gate command, and engine independent wording with Unity, Unreal and Godot notes separated (A5, 04 §6).
- `rules/AGENTS.md` names the current scripts, the mandatory blind slice and the exit code semantics.
- `plugin.json` gained `$schema`, `license` and `keywords`, a description shortened to 157 characters and version 2.1.0 (C40).
- `SKILL.md`. The progressive disclosure map lists the new scripts, the Unity claim now reads "Unity Localization StringTable `.asset` string extraction" and matches the linter (B16), and the 8 Laws follow the blind slice, the critique schema and the exit codes.
- All project specific names (characters, items, class names) were removed from agent prompts, methodology and ledger examples in favour of generic roles and items (B28, 02 §3.6).

### Fixed
- Linter and checker crashes and silent passes in `scripts/` (UTF-8 console output, BOM tolerant input, unknown locale gives exit 2, CJK word boundary regexes, printf false positives, rich-text tag set, per locale expansion ratios, `.ttc` fonts) (A3 to A5, B7 to B14, C38, C42).

## [2.0.0] 2026-11-25

- Initial public structure. 15 locale playbooks with Golden Voice Anchors, `game-culturalizer` and `native-ear-critic` agents, `lqa_linter.py`, `ui_expansion_checker.py`, `font_glyph_scanner.py` and a `run_workflow` pipeline template.
