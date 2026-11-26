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

Video game localization fails whenever text is **grammatically correct on paper yet nobody in real life talks like that**. Players immediately spot robotic *translationese*, manual-style passive voice, mismatched formality, UI text clipping, or missing font glyphs (`□`).

This suite combines **15 native-ear language playbooks** with **Golden Voice Anchors**, a **blind native-ear critic** (`native-ear-critic`), a **colloquial rewriter** (`game-culturalizer`), and **zero-dependency CLI gates**. It is project-independent (no title-specific cast or lore), engine-independent (Unity, Unreal, Godot, ICU, printf, Python-style placeholders are all first-class), and the agent prompts work as plain system prompts with any LLM API.

---

## 1. Progressive Disclosure Map (Load Only What You Need)

Keep your context window lean: read the methodology and ledger guide when orchestrating a locale, and load **only** the playbook of the active target locale.

### Core Runbooks & Templates
* [methodology_and_qa.md](./references/methodology_and_qa.md) : the canonical 4-phase pipeline (Phase 0–3) with per-phase inputs, outputs, and measurable gate criteria; glossary/TM/string-freeze/regression/in-context LQA/pseudo-localization/rollback practices.
* [transcreation_ledger_guide.md](./references/transcreation_ledger_guide.md) : ledger schema (CSV/JSON) for pop-culture nods, idioms, spoiler guards, hidden plurality/gender, and concatenation seams, with a 15-locale idiom table.

### Executable CLI Tools & Workflow (`scripts/`)
Full flag reference and exit codes: [CLI_REFERENCE.md](./scripts/CLI_REFERENCE.md).
* [make_blind_slice.py](./scripts/make_blind_slice.py) : strips the source column from a string table (JSON dict/list, CSV, TSV, PO) and writes the key + context + target-only slice the blind critic is allowed to read.
* [validate_critique.py](./scripts/validate_critique.py) : validates a `critique_<locale>_<batch>.json` file against the fixed critique schema (optionally cross-checks keys against the slice).
* [lqa_linter.py](./scripts/lqa_linter.py) : per-locale anti-translationese and regional-leak scanner (data-driven rules in `scripts/rules/<locale>.json`) plus placeholder (`--placeholder-style unity|unreal|godot|icu|printf|python`) / rich-text or BBCode tag (`--tag-style`) / whitespace / glossary parity validator for JSON, CSV, TSV, PO and Unity Localization StringTable `.asset` (YAML) string extraction (`--src-input en.asset --shared-table Shared.asset`).
* [ui_expansion_checker.py](./scripts/ui_expansion_checker.py) : per-locale expansion-ratio and CJK visual-width overflow detector for buttons, tabs, badges, and headers.
* [font_glyph_scanner.py](./scripts/font_glyph_scanner.py) : zero-dependency `.ttf/.otf/.ttc/.woff` (`cmap`) and Unity TextMeshPro FontAsset `.asset` missing-glyph (`□` tofu) scanner (`--strict` turns fallback-covered misses into failures).
* [localization_pipeline_template.workflow.py](./scripts/localization_pipeline_template.workflow.py) : Antigravity `/run-workflow` template implementing Phase 0–3 with the same names as the methodology (runs only inside the Antigravity workflow runtime, not as a standalone Python script).
* [orchestrator_stub.py](./scripts/orchestrator_stub.py) : API-independent Phase 0–3 orchestrator skeleton with a `complete(system, user) -> str` provider interface and `--dry-run`, for running the same pipeline against any LLM API.

### 15 Language Culturalization & Golden-Voice Playbooks (`references/`)
* **Source Polish:** [en.md](./references/en.md)
* **Turkic & Germanic:** [tr-TR.md](./references/tr-TR.md) · [de-DE.md](./references/de-DE.md)
* **Romance:** [fr.md](./references/fr.md) · [es-ES.md](./references/es-ES.md) · [it-IT.md](./references/it-IT.md) · [pt-BR.md](./references/pt-BR.md) · [pt-PT.md](./references/pt-PT.md)
* **Slavic & Baltic:** [pl-PL.md](./references/pl-PL.md) · [lt-LT.md](./references/lt-LT.md) · [ru-RU.md](./references/ru-RU.md)
* **East Asian (CJK):** [ja-JP.md](./references/ja-JP.md) · [ko-KR.md](./references/ko-KR.md) · [zh-CN.md](./references/zh-CN.md) · [zh-Hant.md](./references/zh-Hant.md)

Locale codes are the canonical ones above; the linter also accepts common aliases (`de` → `de-DE`, `pt_BR` → `pt-BR`, `zh-TW` / `zh-HK` → `zh-Hant`, `fr-FR` → `fr`) and rejects unknown locales with exit code `2`.

Every playbook follows the same 12-section template, so agents and reviewers always find the same information in the same place:

1. Anti-Translationese Ban List · 2. Register, Address & Character Voice · 3. Spoken vs. Literary Tense · 4. Player Gender Neutrality · 5. Plurals, Numbers & ICU · 6. Placeholder & Rich-Text Grammar Traps · 7. Core UI Glossary · 8. Typography, Numbers & Formatting · 9. Text Expansion & UI Fit · 10. Ratings, Legal & Sensitive Content · 11. Golden Voice Anchors · 12. Linter Coverage Note

---

## 2. The Five Voice Archetypes (A1–A5)

Golden Voice Anchors in every playbook are tagged with these five project-independent archetypes. Tag dialogue entries with `"archetype": "A1".."A5"` in the string table (or a `speaker` the project maps to one) so the culturalizer and the critic calibrate the same voice.

| ID | Archetype | Voice fingerprint | Typical lines |
|---|---|---|---|
| **A1** | Mentor / Veteran | Warm, senior, gives advice; relaxed sentences, mild teasing, never bureaucratic. | Tutorial hand-holding, "take your time", post-failure encouragement. |
| **A2** | Hotshot Rival | Cocky, fast, competitive; short jabs, slang, challenges the player. | Race/duel taunts, leaderboard banter, sore-loser lines. |
| **A3** | Rookie / Teen | Excited, everyday slang, short sentences, exclamations, fillers. | First-time reactions, side-kick chatter, chat messages. |
| **A4** | Scientist / Engineer | Precise and technical but conversational; explains without manual-speak. | Mechanic explanations, lore terminals, crafting hints. |
| **A5** | Outlaw / Antagonist | Threatening, cold, clipped; no small talk, no exclamation spam. | Threat letters, boss intros, ultimatum messages. |

UI system text (buttons, toasts, errors, tooltips) is **not** an archetype: it uses the locale's locked UI register from playbook section 7.

Anchors use generic roles and items only (*the Mentor*, *the Rival*, `{itemName}`, *a generator*, *the workshop*). Project-specific names belong in the project's `<LOCALE>_BIBLE.md`, never in the playbooks.

---

## 3. The 8 Laws of Authentic Game Culturalization

1. **Write for the Ear, Not the Dictionary:** Grasp the scene beat, discard the English clause order, and write what a native speaker says out loud.
2. **Anchor Voices Before Translating:** Calibrate every character against the archetype-tagged **Golden Voice Anchors** (A1–A5) in `references/<locale>.md` so mentors, rivals, rookies, scientists, and antagonists never blur into one narrator voice.
3. **Ban Appliance-Manual & Bureaucratic Language:** Toasts and tutorials talk like modern games (*"That doesn't fit here."*, *"Spot's already taken!"*), never like municipal paperwork (*"This item cannot be placed in this location."*).
4. **Use Living Spoken Tenses in Personal Messages:** Never use literary past tenses (*Präteritum*, *passé simple*, *passato remoto*) in emails, chat, or letters where real speakers use conversational tenses (*Perfekt*, *passé composé*, *passato prossimo*, *pretérito perfecto compuesto*); see playbook section 3.
5. **Zero Terminology Collisions:** Lock lookalike mechanics in the glossary (`glossary.csv`: `term_en`, one column per locale, `notes`) before Pass 1 (*Contract* vs *Order*, *Stamina* vs *Durability*, *Blueprint* vs *Recipe*), keep tutorial references identical to live UI labels, and let the linter enforce the glossary.
6. **Natural Player Gender Neutrality:** When player gender is unspecified, use each language's natural non-gendered constructions from playbook section 4 — never default to male forms and never use immersion-breaking `@/*/(a)` hacks.
7. **Blind Native-Ear Critique:** Pass 1 output is always reviewed from a **blind slice** generated by `make_blind_slice.py` (no source column exists in the file the critic reads). The critic returns `critique_<locale>_<batch>.json` in the fixed schema (naturalness `score` 1–5 + `issue_type`), validated by `validate_critique.py`; every entry with `score < 5` is rewritten in Pass 2 by `game-culturalizer`.
8. **Deterministic Tool Gate:** A locale is complete only when `lqa_linter.py --fail-on-error`, `ui_expansion_checker.py --fail-on-high`, and (for custom fonts) `font_glyph_scanner.py` all exit `0`. Exit `1` = findings to fix; exit `2` = the command or input is wrong (unknown locale, malformed file, missing column) and must be corrected, never skipped.

---

## 4. Minimal Instructions (one locale, one table)

1. **Phase 0 — Pre-flight:** record file checksums, scan code for concatenation seams, run `font_glyph_scanner.py` on the project fonts, lock `glossary.csv`, build `<LOCALE>_BIBLE.md` and the transcreation ledger (schema in the ledger guide). Pseudo-localize once to catch hard-coded strings.
2. **Phase 1 — Pass 1:** split the clean-room source batch (`key`, `en`, optional `category`/`speaker`/`archetype`/`max_chars`) and run `game-culturalizer` with `pass: 1` per batch → `pass1_<locale>_<batch>.json`.
3. **Phase 2 — Blind critique + Pass 2:**
   `python scripts/make_blind_slice.py pass1_<locale>_<batch>.json --locale <locale> --out blind_<locale>_<batch>.json --key-col key --target-col dst --context-cols category,speaker,archetype`
   → run `native-ear-critic` on the blind file only → `python scripts/validate_critique.py critique_<locale>_<batch>.json --slice blind_<locale>_<batch>.json` → run `game-culturalizer` with `pass: 2` → `final_<locale>_<batch>.json`.
4. **Phase 3 — Automated gate:**
   `python scripts/lqa_linter.py --input final_<locale>.json --locale <locale> --src-field en --dst-field dst --glossary glossary.csv --glossary-severity ERR --fail-on-error`
   `python scripts/ui_expansion_checker.py --input final_<locale>.json --locale <locale> --src-field en --dst-field dst --fail-on-high`
   `python scripts/font_glyph_scanner.py --input final_<locale>.json --dst-field dst --font <font.ttf|.ttc|TMP.asset>`
   All must exit `0`; then write back to the engine tables and verify that only the target-locale files changed.

Input / output contracts for both agents, including the critique JSON schema, are defined in `agents/game-culturalizer.md` and `agents/native-ear-critic.md`; the full phase runbook with gate criteria is in `references/methodology_and_qa.md`.
