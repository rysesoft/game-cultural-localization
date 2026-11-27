---
name: game-cultural-localization
description: >-
  End-to-end video game localization and culturalization suite for translating,
  adapting, blind-critiquing, linting, and polishing game UI, tutorials,
  warnings, items, lore, and character dialogue into warm, natural, everyday
  spoken language and authentic gamer terminology across 15 locales (en,
  tr-TR, de-DE, fr, es-ES, it-IT, pt-BR, pt-PT, pl-PL, lt-LT, ru-RU, ja-JP,
  ko-KR, zh-CN, zh-Hant). Use whenever starting, reviewing, or fixing any game
  localization language, string table, or LQA pass.
---

# Game Localization & Culturalization Engine

Video game localization fails whenever text is **grammatically correct on paper yet nobody in real life talks like that**. Players immediately spot robotic *translationese*, manual style passive voice, mismatched formality, UI text clipping or missing font glyphs (`□`).

Every run starts with a **context map** of the game (`context-cartographer` on Claude Opus with `context-scout` agents on Claude Sonnet), because no translator or juror can choose the right word for a line without knowing where and why the game shows it. On top of that map the suite combines **15 native ear language playbooks** with **Golden Voice Anchors**, a **blind native ear critic** (`native-ear-critic`), a **colloquial rewriter** (`game-culturalizer`), a **mixed-family LLM jury** with language packs, and **zero dependency CLI gates**. It is project independent (no title specific cast or lore), engine independent (Unity, Unreal, Godot, ICU, printf and Python style placeholders are all first class), and the agent prompts work as plain system prompts with any LLM API.

---

## 1. Progressive Disclosure Map (Load Only What You Need)

Keep your context window lean. Read the methodology and the ledger guide when you orchestrate a locale, and load **only** the playbook of the active target locale.

### Context Map (always first)
* [agents/context-cartographer.md](../../agents/context-cartographer.md) orchestrates the context map on Claude Opus (role `context_orchestrator`), splits the game among [agents/context-scout.md](../../agents/context-scout.md) agents on Claude Sonnet (role `context_agent`), asks the user whenever something stays unclear and writes `CONTEXT_MAP.md` for every later step.
* [build_context_map.py](./scripts/build_context_map.py) `--scan` gives the agents the facts. For every key of a Unity project the prefabs, scenes and data assets that use it (prefab overrides included), the object's hierarchy path, the class and field, and the code lines that show it, with a flag where the code glues the text to something else. `--slices` writes every scout's input from the project's own string tables and `--check-slices` checks that the scout reports cover every key once.

### Core Runbooks & Templates
* [methodology_and_qa.md](./references/methodology_and_qa.md). The canonical 4 phase pipeline (Phase 0 to 3) with per phase inputs, outputs and measurable gate criteria, the context map, the jury and deliberation flow, language packs and trust levels, plus TM, string freeze, regression, in-context LQA, pseudo localization and rollback practices.
* [transcreation_ledger_guide.md](./references/transcreation_ledger_guide.md). Ledger schema (CSV and JSON) for pop culture nods, idioms, spoiler guards, hidden plurality or gender and concatenation seams, with a 15 locale idiom table.

### Executable CLI Tools & Workflow (`scripts/`)
The full flag reference and the exit codes are in [CLI_REFERENCE.md](./scripts/CLI_REFERENCE.md).
* [make_blind_slice.py](./scripts/make_blind_slice.py) strips the source column from a string table (JSON dict or list, CSV, TSV, PO) and writes the key, context and target only slice the blind critic is allowed to read.
* [validate_critique.py](./scripts/validate_critique.py) validates a `critique_<locale>_<batch>.json` file against the fixed critique schema (optionally cross-checking keys against the slice).
* [lqa_linter.py](./scripts/lqa_linter.py) is the per locale anti-translationese and regional leak scanner (data driven rules in `scripts/rules/<locale>.json`) plus the placeholder (`--placeholder-style unity|unreal|godot|icu|printf|python`), rich-text or BBCode tag (`--tag-style`), whitespace and glossary parity validator for JSON, CSV, TSV, PO and Unity Localization StringTable `.asset` (YAML) string extraction (`--src-input en.asset --shared-table Shared.asset`).
* [ui_expansion_checker.py](./scripts/ui_expansion_checker.py) detects per locale expansion ratio and CJK visual width overflow for buttons, tabs, badges and headers.
* [font_glyph_scanner.py](./scripts/font_glyph_scanner.py) is a zero dependency `.ttf/.otf/.ttc/.woff` (`cmap`) and Unity TextMeshPro FontAsset `.asset` missing glyph (`□` tofu) scanner (`--strict` turns fallback covered misses into failures).
* [localization_pipeline_template.workflow.py](./scripts/localization_pipeline_template.workflow.py) is the Antigravity `/run-workflow` template of Phase 0 to 3 with the same names as the methodology (it runs only inside the Antigravity workflow runtime, not as a standalone Python script).
* [orchestrator_stub.py](./scripts/orchestrator_stub.py) runs Phase 0 to 3 against any LLM API. `--dry-run` runs the jury flow offline with the fake provider, `--live` with the real APIs, `--provider module:function` keeps the single critic flow.

### Jury, Language Packs and Measurement (`scripts/`, `prompts/`, `langpack/`)
Model access goes through [providers/](./scripts/providers/) and [providers.config.json](./scripts/providers.config.json) (model ids, prices, roles, jury tiers). API keys come only from `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` and `DEEPSEEK_API_KEY`. Every model calling tool takes `--dry-run`.
* [providers_check.py](./scripts/providers_check.py) checks the config and the keys and pings every model.
* [build_language_pack.py](./scripts/build_language_pack.py) builds `langpack/<locale>/` from [sources.manifest.json](./langpack/sources.manifest.json) with a five layer trust filter and license classes (`bundle` ships, `local` stays on the machine).
* [warmup_loader.py](./scripts/warmup_loader.py) picks a seeded, register aware warm-up sample of 30 to 50 native lines.
* [build_contrastive_set.py](./scripts/build_contrastive_set.py) builds native, robot and unknown line pairs from the studio's professional reference.
* [roundtrip_check.py](./scripts/roundtrip_check.py) runs the back-translation calque test on long dialogue and calibrates its threshold.
* [eval_critic.py](./scripts/eval_critic.py) calibrates every juror on the contrastive set (pairwise gate 0.85, kappa, warm-up on and off).
* [jury.py](./scripts/jury.py) runs the J1, J2, J3 mixed-family jury with the agreement rule and budget caps, [deliberate.py](./scripts/deliberate.py) runs the anonymous J3 deliberation round.
* [tm.py](./scripts/tm.py) is the SQLite translation memory with n-gram neighbours for Pass 1 RAG and the jury evidence.
* [pass2_rewrite.py](./scripts/pass2_rewrite.py) writes three Pass 2 candidates, lets J1 pick one blind and validates it.
* [report_changes.py](./scripts/report_changes.py) writes the developer change report (JSON and Markdown), [budget_report.py](./scripts/budget_report.py) the token, call and cost report with a project projection.
* [prompts/](./prompts/) holds the native critic and Pass 2 prompts of all 15 locales (`critic.<locale>.md`, `pass2.<locale>.md`, each written in its own language), the English fallbacks and `literal.md`.

### 15 Language Culturalization & Golden-Voice Playbooks (`references/`)
* **Source Polish.** [en.md](./references/en.md)
* **Turkic & Germanic.** [tr-TR.md](./references/tr-TR.md) · [de-DE.md](./references/de-DE.md)
* **Romance.** [fr.md](./references/fr.md) · [es-ES.md](./references/es-ES.md) · [it-IT.md](./references/it-IT.md) · [pt-BR.md](./references/pt-BR.md) · [pt-PT.md](./references/pt-PT.md)
* **Slavic & Baltic.** [pl-PL.md](./references/pl-PL.md) · [lt-LT.md](./references/lt-LT.md) · [ru-RU.md](./references/ru-RU.md)
* **East Asian (CJK).** [ja-JP.md](./references/ja-JP.md) · [ko-KR.md](./references/ko-KR.md) · [zh-CN.md](./references/zh-CN.md) · [zh-Hant.md](./references/zh-Hant.md)

Locale codes are the canonical ones above. The linter also accepts common aliases (`de` for `de-DE`, `pt_BR` for `pt-BR`, `zh-TW` and `zh-HK` for `zh-Hant`, `fr-FR` for `fr`) and rejects unknown locales with exit code `2`.

Every playbook follows the same 12 section template, so agents and reviewers always find the same information in the same place.

1. Anti-Translationese Ban List · 2. Register, Address & Character Voice · 3. Spoken vs. Literary Tense · 4. Player Gender Neutrality · 5. Plurals, Numbers & ICU · 6. Placeholder & Rich-Text Grammar Traps · 7. Core UI Glossary · 8. Typography, Numbers & Formatting · 9. Text Expansion & UI Fit · 10. Ratings, Legal & Sensitive Content · 11. Golden Voice Anchors · 12. Linter Coverage Note

---

## 2. The Five Voice Archetypes (A1 to A5)

Golden Voice Anchors in every playbook are tagged with these five project independent archetypes. Tag dialogue entries with `"archetype": "A1".."A5"` in the string table (or a `speaker` the project maps to one) so the culturalizer, the critic and the jury calibrate the same voice.

| ID | Archetype | Voice fingerprint | Typical lines |
|---|---|---|---|
| **A1** | Mentor / Veteran | Warm, senior, gives advice. Relaxed sentences, mild teasing, never bureaucratic. | Tutorial hand-holding, "take your time", post-failure encouragement. |
| **A2** | Hotshot Rival | Cocky, fast, competitive. Short jabs, slang, challenges the player. | Race and duel taunts, leaderboard banter, sore-loser lines. |
| **A3** | Rookie / Teen | Excited, everyday slang, short sentences, exclamations, fillers. | First-time reactions, side-kick chatter, chat messages. |
| **A4** | Scientist / Engineer | Precise and technical but conversational. Explains without manual speak. | Mechanic explanations, lore terminals, crafting hints. |
| **A5** | Outlaw / Antagonist | Threatening, cold, clipped. No small talk, no exclamation spam. | Threat letters, boss intros, ultimatum messages. |

UI system text (buttons, toasts, errors, tooltips) is **not** an archetype. It uses the locale's locked UI register from playbook section 7.

Anchors use generic roles and items only (*the Mentor*, *the Rival*, `{itemName}`, *a generator*, *the workshop*). Project specific names belong in the project's `<LOCALE>_BIBLE.md`, never in the playbooks.

---

## 3. The 8 Laws of Authentic Game Culturalization

1. **Write for the Ear, Not the Dictionary.** Grasp the scene beat, discard the English clause order and write what a native speaker says out loud.
2. **Anchor Voices Before Translating.** Calibrate every character against the archetype tagged **Golden Voice Anchors** (A1 to A5) in `references/<locale>.md` so mentors, rivals, rookies, scientists and antagonists never blur into one narrator voice.
3. **Ban Appliance-Manual & Bureaucratic Language.** Toasts and tutorials talk like modern games (*"That doesn't fit here."*, *"Spot's already taken!"*), never like municipal paperwork (*"This item cannot be placed in this location."*).
4. **Use Living Spoken Tenses in Personal Messages.** Never use literary past tenses (*Präteritum*, *passé simple*, *passato remoto*) in emails, chat or letters where real speakers use conversational tenses (*Perfekt*, *passé composé*, *passato prossimo*, *pretérito perfecto compuesto*), see playbook section 3.
5. **Context Decides Every Word.** Language is flexible. One source word takes different target words depending on where the game uses it (*Play* is *Oyna* for a game and *Çal* for music, *Stamina* can be an energy bar on the HUD or a durability stat on an item), so no term is ever locked in a list. Read the line notes of `CONTEXT_MAP.md` for every key, find where it shows, what the player is doing and what sits next to it, and choose the word for that place. A tutorial that names a button uses the same word as that button, because the map links them.
6. **Natural Player Gender Neutrality.** When player gender is unspecified, use each language's natural non-gendered constructions from playbook section 4. Never default to male forms and never use immersion-breaking `@/*/(a)` hacks.
7. **Blind Native-Ear Critique.** Pass 1 output is always reviewed from a **blind slice** generated by `make_blind_slice.py` (no source column exists in the file the critic or the jury reads). The critic returns `critique_<locale>_<batch>.json` in the fixed schema (naturalness `score` 1 to 5 and `issue_type`), validated by `validate_critique.py`. The jury flow scores every line with three model families per tier and settles disagreements by anonymous deliberation. Every entry with `score` below 5 is rewritten in Pass 2.
8. **Deterministic Tool Gate.** A locale is complete only when `lqa_linter.py --fail-on-error`, `ui_expansion_checker.py --fail-on-high` and (for custom fonts) `font_glyph_scanner.py` all exit `0`. Exit `1` means findings to fix. Exit `2` means the command or input is wrong (unknown locale, malformed file, missing column) and must be corrected, never skipped.

---

## 4. Minimal Instructions (one locale, one table)

1. **Phase 0, pre-flight.** First the context map. Run `context-cartographer`, answer its questions, and keep `CONTEXT_MAP.md` with the project. Then record file checksums, scan code for concatenation seams, run `font_glyph_scanner.py` on the project fonts, build `<LOCALE>_BIBLE.md` and the transcreation ledger (schema in the ledger guide). Pseudo-localize once to catch hard-coded strings.
2. **Phase 1, Pass 1.** Split the clean room source batch (`key`, `en`, optional `category`, `speaker`, `archetype`, `max_chars`) and run `game-culturalizer` with `pass: 1` per batch to get `pass1_<locale>_<batch>.json`.
3. **Phase 2, blind critique and Pass 2.**
   `python scripts/make_blind_slice.py pass1_<locale>_<batch>.json --locale <locale> --out blind_<locale>_<batch>.json --key-col key --target-col dst --context-cols category,speaker,archetype`
   Then run `native-ear-critic` on the blind file only, check it with `python scripts/validate_critique.py critique_<locale>_<batch>.json --slice blind_<locale>_<batch>.json` and run `game-culturalizer` with `pass: 2` to get `final_<locale>_<batch>.json`.
   With API keys the whole phase also runs as a jury, `python scripts/jury.py blind_<locale>_<batch>.json --locale <locale> --source-table pass1_<locale>_<batch>.json --context-map loc_work/context/CONTEXT_MAP.md`, followed by `pass2_rewrite.py` and `report_changes.py`. `--context-map` gives every juror the map and every line its note, writers also get the locale appendix.
4. **Phase 3, automated gate.**
   `python scripts/lqa_linter.py --input final_<locale>.json --locale <locale> --src-field en --dst-field dst --fail-on-error`
   `python scripts/ui_expansion_checker.py --input final_<locale>.json --locale <locale> --src-field en --dst-field dst --fail-on-high`
   `python scripts/font_glyph_scanner.py --input final_<locale>.json --dst-field dst --font <font.ttf|.ttc|TMP.asset>`
   All must exit `0`. Then write back to the engine tables and verify that only the target locale files changed.

`python scripts/orchestrator_stub.py --dry-run --locale <locale> --input <table> --workdir <dir>` runs Phase 0 to 3 with the jury end to end without any API key, `--live` does the same with the real models.

Input and output contracts of the agents, including the critique JSON schema, are defined in `agents/context-cartographer.md`, `agents/context-scout.md`, `agents/game-culturalizer.md` and `agents/native-ear-critic.md`. The full phase runbook with gate criteria is in `references/methodology_and_qa.md`.
