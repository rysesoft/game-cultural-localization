# 4-Phase Culturalization Methodology & Automated QA Runbook

Use this runbook whenever you localize or overhaul a game locale, whatever the engine or string table format. Unity Localization `.asset` tables, Unreal `.po` or `.csv`, Godot `.csv` or `.po`, plain JSON (dict or list), TSV and ICU message bundles all work. The four phases are numbered **0 to 3** everywhere in this plugin (`SKILL.md`, `rules/AGENTS.md`, the agents, `scripts/localization_pipeline_template.workflow.py` and `scripts/orchestrator_stub.py` use the same names).

| Phase | Name | Main actor | Key output |
|---|---|---|---|
| 0 | Context map first, then pre-flight. Codebase, font and transcreation audit | `context-cartographer` (Claude Opus) with `context-scout` agents (Claude Sonnet), the user's answers, CLI tools | `CONTEXT_MAP.md`, `checksums_before.txt`, `<LOCALE>_BIBLE.md`, `transcreation_ledger.csv`, font report |
| 1 | Clean room culturalization (Pass 1) | `game-culturalizer` | `pass1_<locale>_<batch>.json` |
| 2 | Blind native ear critique and Pass 2 colloquial rewrite | `make_blind_slice.py`, then `native-ear-critic` (or the jury), `validate_critique.py`, `game-culturalizer` | `blind_<locale>_<batch>.json`, `critique_<locale>_<batch>.json`, `final_<locale>_<batch>.json` |
| 3 | Automated LQA, UI overflow and font gate | `lqa_linter.py --fail-on-error`, `ui_expansion_checker.py --fail-on-high`, `font_glyph_scanner.py` | reports (`--json`), exit codes `0`, `checksums_after.txt` |

All commands below run from the plugin's `skills/game-cultural-localization/` folder (`<plugin_dir>` is `~/.gemini/config/plugins/game-cultural-localization` or `<project>/.agents/plugins/game-cultural-localization`). Every script is pure Python 3.9+ standard library, reads UTF-8 with or without BOM and prints UTF-8 on any console. Flag details are in [scripts/CLI_REFERENCE.md](../scripts/CLI_REFERENCE.md).

### Shared file conventions

- **Working field names.** `key`, `en` (source) and `dst` (target) by default. Override them with `--key-field`, `--src-field` and `--dst-field` (or `--key-col` and `--target-col` for the slice tool) when the project table uses other names, for example a locale named column `de-DE`.
- **Optional context fields.** `category` (`ui_button`, `ui_toast`, `tutorial`, `item`, `lore`, `dialogue` and so on), `speaker`, `archetype` (A1 to A5, see `SKILL.md`), `context`, `max_chars`, `plural` (ICU category).
- **Engine token syntaxes supported everywhere.** `{0}` and `{name}` (Unity, .NET, Python), `%s`, `%d` and `%1$s` (printf, Godot), ICU `{count, plural, one {...} other {...}}`, Unreal `{Name}` and the Hangul post-position `|hpp(...)`, rich text `<b> <i> <u> <color=...> <size=...> <sprite=...> <style=...> <link=...> <br>` and BBCode `[b] [i] [color=...] [url=...]`. Engine specific notes are marked **(Unity)**, **(Unreal)** and **(Godot)**.
- **Context map.** `CONTEXT_MAP.md` of the project (see Phase 0 step 1) is the source of meaning for every line. Language is flexible, one source word takes different target words depending on where the game uses it (*Play* is *Oyna* for a game and *Çal* for music), so words are chosen per place from the map and never locked in a term list.
- **Fixed names (optional).** `lqa_linter.py --glossary names.csv` can check proper names that never change, such as the game's title, characters, factions, stations and brands, in a CSV with the header `term_en,<locale>[,<locale>...],notes`. It is a spelling check for names, not a way to decide words.

- **Naming.** `<LOCALE>_BIBLE.md` (for example `DE-DE_BIBLE.md`), `pass1_<locale>_<batch>.json`, `blind_<locale>_<batch>.json`, `critique_<locale>_<batch>.json`, `final_<locale>_<batch>.json`, `lqa_<locale>.json`. The jury flow adds `verdicts_<locale>_<batch>.json`, `rewrites_<locale>_<batch>.json` and `changes_<locale>_<batch>.json` with its `.md` twin.

---

## Phase 0. Pre-Flight Codebase, Font & Transcreation Audit

**Inputs.** Engine string tables, game code, scenes, prefabs and data assets, fonts and atlases, the user for every open question.
**Outputs.** `CONTEXT_MAP.md`, `checksums_before.txt`, the concatenation seam list (ledger type `concat`), font report, `<LOCALE>_BIBLE.md`, `transcreation_ledger.csv`, pseudo localization findings.

0. **Context map, always first.** A professional game translator studies the game before the first line, reads the code that shows each string and learns the world, the systems and the screens. `context-cartographer` does that work for every later step and runs on the strongest model (Claude Opus, role `context_orchestrator`). It inventories the engine, the string tables, the game's own code, scenes, prefabs and data assets (`build_context_map.py --scan` lists for every key the files, objects, classes and fields that use it), splits the game into slices (systems, screens, tables, lore) and hands each slice to a `context-scout` agent (Claude Sonnet, role `context_agent`). `build_context_map.py --slices` writes every scout's input from the project's own string tables, paragraph breaks intact, and `--check-slices` confirms that the reports cover every key exactly once. The scouts report per key where it shows, what the player is doing, what is inserted next to it, the room it has, who speaks to whom and what stayed unclear. The orchestrator merges the reports into `CONTEXT_MAP.md` (the game on one page, world, systems, screens, line notes, decisions, open questions), and **asks the user** every question that changes how a line should read instead of guessing. The questions are collected while the work goes on and asked in one batch at the end of the session, with a best guess each, and game bugs the scouts found are listed apart from them. The map never quotes source lines, so the jury and the critic may read it and stay blind to the source wording. Nothing else in this runbook starts before the map exists, and every later actor reads it first.
1. **Baseline file checksums.** Record SHA-256 hashes of all localization files so you can prove at the end that only the intended target locale files changed.
   ```bash
   # Windows PowerShell
   Get-ChildItem -Recurse <loc_dir> -File | Get-FileHash -Algorithm SHA256 | Sort-Object Path | Format-Table Hash,Path -AutoSize | Out-File checksums_before.txt
   # macOS / Linux
   find <loc_dir> -type f -print0 | sort -z | xargs -0 sha256sum > checksums_before.txt
   ```
2. **Code concatenation and slot scan.** Search game code (`.cs`, `.cpp`, `.gd`, `.ts`, Blueprints exported as text) for string concatenation, `string.Format`, `FText::Format` or `tr()` with `%`, Smart Strings, leading or trailing spaces (`' is assigned.'`, `'Total: '`), auto appended colons, and status plus noun slots (`"x3 " + status + " " + itemName`). Every hit becomes a ledger row of type `concat` with the constraint spelled out.
3. **Font glyph pre-check.** Before translating into diacritic heavy (`pl-PL`, `lt-LT`, `tr-TR`, `fr`, `es-ES`, `pt-*`) or CJK (`ja-JP`, `ko-KR`, `zh-CN`, `zh-Hant`) locales, scan every font the UI can fall back to (`.ttf`, `.otf`, `.ttc` collections, **(Unity)** TextMeshPro `*.asset` atlases) against a representative sample or the playbook's character inventory. Decide now whether ALL CAPS German may use `SS` instead of `ẞ`, and whether `« »`, `„“` or `「」` are safe or ASCII quotes are required.
   ```bash
   python scripts/font_glyph_scanner.py --input <sample_or_previous_locale.json> --dst-field dst --font <ui_font.ttf> --font <fallback.ttc> --font <TMP_atlas.asset>
   ```
4. **UI ground truth verification.** The context map does this for every key. Check it for the short or ambiguous ones. Find where the key is bound (**(Unity)** `m_KeyId` in `.prefab` or `.unity`, `LocalizedString` fields, **(Unreal)** `NSLOCTEXT` or string table references in widgets, **(Godot)** `tr()` calls and scene `text` properties) and read the surrounding UI. Is the key a tab, a button, a progress status, a suffix appended after a machine name? Open the sprite for ambiguous asset names before naming them. Align the target to the object actually on screen when the source drifts between two names for one object.
5. **Build `<LOCALE>_BIBLE.md`.** The bible records the target-language decisions the map's situations led to (with the place each one applies to, never as a global lock), every character's register (`du/Sie`, `tu/vous`, `tú/usted`, `tu/Lei`, 반말, 해요체 and 합쇼체, Japanese first person pronouns and sentence enders), the archetype mapping (speaker to A1 to A5), the project's UI register, number, date and currency formats, and platform button conventions.
6. **Start the transcreation ledger** (schema in `transcreation_ledger_guide.md`). Pop culture quotes (verify official local dubs by web search before translating), idioms, spoiler guards, hidden plurality or gender facts, concatenation seams.
7. **Pseudo-localize once.** Run the source through a pseudo locale (lengthen 30 to 40 %, add diacritics and a few CJK characters, bracket each string) and play the build. Hard coded strings, concatenations, clipped controls and tofu show up before any real translation money is spent.
8. **Language pack and trust level (jury flow).** `build_language_pack.py` builds `langpack/<locale>/` once per locale, `eval_critic.py` calibrates the jury on its contrastive set. The resulting trust level (measured, estimated or rule based) goes into every change report.

**Gate 0 (all must hold).** `CONTEXT_MAP.md` exists and has line notes for every key of the run · every open question that changes how a line reads is answered by the user · checksums recorded · every concatenation seam has a ledger row · the font scan has 0 missing glyphs for the planned character set (or a documented fallback font) · `<LOCALE>_BIBLE.md` names a register for every speaker and for UI · pseudo localization issues are filed.

---

## Phase 1. Clean-Room Culturalization, Pass 1 (`game-culturalizer`)

**Inputs.** Clean room source batches `in_<locale>_<batch>.json` (`key`, `en`, optional context fields, **never** legacy machine translated target text), `CONTEXT_MAP.md`, ledger, `<LOCALE>_BIBLE.md`, `references/<locale>.md`.
**Outputs.** `pass1_<locale>_<batch>.json` (same keys, same order, target text in `dst`).

1. Export the table to the working JSON format and split it into batches of roughly 80 to 150 strings grouped by category or speaker (keep one speaker's scene together).
2. Run `game-culturalizer` with `pass: 1` per batch. Batches are independent and can run in parallel. In the jury flow the `pass1` model also gets a warm-up block from the language pack and, with `--tm`, the three closest approved translation memory lines for every row.
3. Run the linter on each batch immediately so token slips are caught before the critic sees them.
   ```bash
   python scripts/lqa_linter.py --input pass1_<locale>_<batch>.json --locale <locale> --src-field en --dst-field dst --fail-on-error
   ```

**Gate 1.** Every batch file has exactly the input keys · linter exit `0` on every batch · no source language text left in `dst` (the `[UNTRANSLATED]` check).

---

## Phase 2. Blind Native-Ear Critique (`native-ear-critic` or the jury) and Pass 2 Colloquial Rewrite (`game-culturalizer`)

**Why this phase is the secret weapon.** Reviewers who see the English forgive English sentence order. Real players never see the English.

**Inputs.** `pass1_<locale>_<batch>.json`.
**Outputs.** `blind_<locale>_<batch>.json`, `critique_<locale>_<batch>.json`, `final_<locale>_<batch>.json`, Pass 2 summary.

1. **Generate the blind slice.** This step is mandatory, it is what makes the critique blind.
   ```bash
   python scripts/make_blind_slice.py pass1_<locale>_<batch>.json --locale <locale> --out blind_<locale>_<batch>.json --key-col key --target-col dst --context-cols category,speaker,archetype
   ```
   The output contains only `key`, the listed context columns and the target text. The script refuses to write a file that would still contain a source column and exits `2` on missing columns or unknown locales.
2. **Run the critic** on the blind file only (as a subagent, via `scripts/localization_pipeline_template.workflow.py`, via `scripts/orchestrator_stub.py`, or as a plain system prompt with any LLM API). It reads `blind_<locale>_<batch>.json` and `references/<locale>.md`, nothing else, and writes `critique_<locale>_<batch>.json` in the fixed schema (`score` 1 to 5 naturalness, `issue_type`, `reason`, `suggested`, optional `needs_source_check`, see `agents/native-ear-critic.md`). The jury flow below replaces the single critic with three model families.
3. **Validate the critique** before anyone consumes it.
   ```bash
   python scripts/validate_critique.py critique_<locale>_<batch>.json --slice blind_<locale>_<batch>.json
   ```
   Exit `1` (schema or key mismatch) means the critique is re-run, not patched by hand.
4. **Pass 2 rewrite.** Run `game-culturalizer` with `pass: 2`, the Pass 1 file and the critique. It rewrites every flagged key (critical first), re-checks each suggestion against the source, the context map, tokens and `max_chars`, resolves `needs_source_check` items against the map, code, prefabs and sprites, and writes `final_<locale>_<batch>.json` plus a summary of adopted, adapted and rejected suggestions.
5. **Blind critic context guardrail.** The critic cannot see source, code or sprites, so it can mislabel items, decals, tabs and buttons. Every rename of an item, decal, tab or button suggested by the critic is cross-checked against code, prefabs and sprites before acceptance.

**Gate 2 (measurable).** The blind slice contains no source column (the slice tool guarantees it, spot-check the header) · `validate_critique.py` exit `0` for every batch · 100 % of entries with `score` 2 or lower rewritten, 100 % of `score` 3 or 4 rewritten or explicitly rejected with a reason · a second blind pass on the final batch shows **at least 95 % of lines at score 5 and 0 lines at score 2 or lower** (sample at least 100 lines, or the whole batch if smaller) · `needs_source_check` items all resolved in the summary.

The rewrite rate is a consequence, not a target. A Pass 1 that needs 10 % rewriting is better than one that needs 40 %. Historic projects landed between 25 % and 50 % on first runs, use that only to sanity-check a suspiciously low flag count.

---

## Phase 2 with the Mixed-Family Jury (since 2.2)

The jury flow replaces the single critic with three tiers of three models, one model from each family (Anthropic, Google, DeepSeek). A family that likes its own style is outvoted by the two others, and no human native reviewer is needed in the loop. Model ids, prices and tiers live in `scripts/providers.config.json`, the API keys in `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` and `DEEPSEEK_API_KEY`. Every step runs offline with `--dry-run`.

```bash
python scripts/jury.py blind_<locale>_<batch>.json --locale <locale> --source-table pass1_<locale>_<batch>.json --tm loc_work/tm.sqlite --context-map loc_work/context/CONTEXT_MAP.md
python scripts/pass2_rewrite.py verdicts_<locale>_<batch>.json --source-table pass1_<locale>_<batch>.json --locale <locale> --critique-out critique_<locale>_<batch>.json --context-map loc_work/context/CONTEXT_MAP.md
python scripts/report_changes.py verdicts_<locale>_<batch>.json --locale <locale> --rewrites rewrites_<locale>_<batch>.json --budget-log loc_work/
```

`python scripts/orchestrator_stub.py --live --locale <locale> --input <table> --workdir <dir> --context-map loc_work/context/CONTEXT_MAP.md` chains Phase 0 to 3 with these steps.

`--context-map` hands the map of step 0 to every model call. The map joins the system prompt, where the prompt cache keeps it cheap from the second batch on, and every line carries its own note from `line_notes.json`. Jurors and blind pickers read the neutral fields only (screen, element, player action, inserted text, room, speaker, listener, register). Pass 1 and Pass 2 also read the scout notes and the locale appendix `CONTEXT_MAP.<locale>.md` with the choices of an existing translation. Jurors never read that appendix, it would hand a calibration its answer key. `eval_critic.py --context-map` calibrates the jury the same way.

### Tiers and agreement

| Tier | Members (default) | Reads |
|---|---|---|
| J1 | Haiku, DeepSeek V4 Flash, Gemini 4 Hydrogen | every line |
| J2 | Sonnet, DeepSeek V4 Pro, Gemini 4 Neon | lines J1 did not settle |
| J3 | Opus, DeepSeek V4 Pro, Gemini 4 Carbon | lines J2 did not settle and every critical line |

Agreement is judged on the three scores of one tier.

- **Pass.** All three scores are 4 or 5 and the spread is at most 1. The line score is the lowest score. A 4 goes to Pass 2 as a light rewrite, a 5 stays as it is.
- **Escalate.** Any score of 3 or lower, or a spread of 2 or more. The line moves to the next tier.
- **Critical.** Any score of 2 or lower. The line goes straight to J3, whatever the tier.

At J3 an agreeing tier settles the line with its lowest score. A disagreeing J3 starts the deliberation round.

**Budget caps.** When more than 30 % of the lines judged so far in the run would go to J2, or more than 10 % to J3, the run stops before calling that tier and writes the report with the lines that tripped it. The caps read the whole run, not one batch, and wait for a fair sample (at least 100 judged lines and at least 10 lines over the cap, `min_judged` and `min_escalated` of `budget_caps`), so one bad line in a short batch never stops a game. The problem is then in Pass 1 or in the prompt, not in single lines. Fix the cause and run the batch again.

### Deliberation

1. The three J3 members have voted.
2. Each member sees the other two scores and reasons without model or family names, plus a mechanical evidence package. Ban list hits from `rules/<locale>.json`, the three closest approved translation memory lines (target text only) and, for dialogue over six words, the back-translation calque signal.
3. Each member votes once more.
4. The majority decides. When three different scores remain, the line goes to the developer as unresolved with the three rationales.

### Pass 2 and the developer report

The `pass2` model writes three candidates for every flagged line. The three J1 members see only the candidates and the context and pick one blind, the most picked candidate wins. The winner must pass `validate_critique` (schema, placeholder and tag parity), otherwise the next candidate is tried and, when none passes, the old line stays. `report_changes.py` lists every line with its old and new text, status, reason, evidence, confidence and votes, and the developer accepts or rejects each one. `tm.py --mode approve` stores the decisions as approved translation memory, which feeds the next Pass 1 and the next jury.

### Language packs and calibration

| Step | Tool | Result |
|---|---|---|
| Build the pack once per locale | `build_language_pack.py` | warm-up corpus with license classes and a five layer trust filter (source selection, mechanical filter, MT detection, cross consistency, jury pre-screen) |
| Warm up the ear | `warmup_loader.py` | 30 to 50 seeded native lines of the right register in every prompt |
| Build contrastive pairs | `build_contrastive_set.py` | professional native line, deliberately literal robot line and raw strong model lines |
| Calibrate the back-translation test | `roundtrip_check.py --calibrate` | the calque threshold of the locale |
| Calibrate the jurors | `eval_critic.py` | pairwise accuracy per member (gate 0.85), score means, kappa, warm-up effect |
| Watch the cost | `budget_report.py` | tokens, calls and cost per role and model, projection to a full project |

`bundle` class lines (permissive licenses, the studio's own translations) may ship with the plugin. `local` class lines (copyleft games, translation memories) stay in the gitignored `langpack/<locale>/local/` folder and never leave the machine. OpenSubtitles is not used.

### Trust levels

| Level | When | Meaning of a verdict |
|---|---|---|
| measured | professional reference and a passing calibration (tr-TR first) | measured against the professional translation |
| estimated | a language pack is installed | estimated from proxy signals |
| rule based | no language pack | only the rule based gates speak for the line |

Known limits, written into every trust card. Native judgement without a professional reference is an estimate. Open corpora are mostly translations, so warm-up calibrates to good translation, not to original writing. Back-translation carries no signal for UI and short text. Self-preference of a model family is reduced by deliberation, not removed. Cultural errors are not caught by any proxy signal. The cost is unknown until measured, a rough estimate is 5 to 15 calls per line.

---

## Phase 3. Automated CLI LQA, UI Overflow & Font Gate

**Inputs.** The merged `final_<locale>.json` (all batches), fonts.
**Outputs.** `lqa_<locale>.json`, `ui_<locale>.json`, font report, `checksums_after.txt`, engine tables written back.

```bash
# 1. Anti-translationese + regional leak scan, placeholder/tag/whitespace/punctuation parity
python scripts/lqa_linter.py --input final_<locale>.json --locale <locale> \
  --src-field en --dst-field dst \
  --forbid-chars ";—–" --forbid-spaced-hyphen --strict-whitespace \
  --json lqa_<locale>.json --fail-on-error

# 2. UI button, tab, and badge overflow risk (per-locale expansion ratio + CJK width); blocks on HIGH
python scripts/ui_expansion_checker.py --input final_<locale>.json --locale <locale> \
  --src-field en --dst-field dst --json ui_<locale>.json --fail-on-high

# 3. Font missing-glyph (tofu □) scan against every font in the fallback chain
python scripts/font_glyph_scanner.py --input final_<locale>.json --dst-field dst \
  --font <ui_font.ttf> --font <fallback.ttc> --font <TMP_atlas.asset>
```

Use `--forbid-chars`, `--forbid-spaced-hyphen` and `--strict-whitespace` only when the project's bible declares those rules (CJK playbooks forbid dashes, concatenation seams require exact leading and trailing spaces). Add `--fail-on-warn` for release candidates. Set `--placeholder-style` and `--tag-style` explicitly (**(Unreal)** `unreal`, **(Godot)** `godot` and `bbcode`, ICU bundles `icu`) when auto detection is ambiguous. Add `--strict` to the font scan when no runtime fallback font exists. Project wide defaults can live in `l10n.config.json` (`--config`).

**Write back.** `export_translations.py` applies the developer's decisions of the change reports (accept keeps the new line, reject puts the old line back, a changed line without a decision is reported) and writes the final texts in the game's own table format to a folder outside the game project. Unity StringTables change only in the text of the known keys, every other line stays as it was and a missing entry is added. CSV, TSV, JSON and PO tables change only in the target of the known keys. Only tables with a changed text are written, the developer copies them over the originals and re-imports.

```bash
python scripts/export_translations.py <workdir> --locale <locale> --template-dir <game>/Assets/Localisation/Tables --out loc_work/export
```

**Exit codes of all three tools.** `0` clean · `1` findings (errors, or warnings with `--fail-on-warn`, or HIGH with `--fail-on-high`) · `2` usage or input error (unknown locale, malformed file, missing column, unreadable font). Exit `2` is never a pass.

**Gate 3.** All three commands exit `0` · 100 % of HIGH overflow risks resolved (shorter string, approved `max_chars` change, or a UI change filed with the key) · 0 missing glyphs, or a documented fallback font that covers them · engine tables written back and re-imported without warnings · `checksums_after.txt` differs from `checksums_before.txt` **only** in the target locale files · **(Unity)** Smart String flags (`IsSmart`) unchanged for every entry that uses `{...}` formatting · **(Unreal)** `.po` re-gathered with 0 fuzzy entries · **(Godot)** CSV re-imported with the same column count.

### Validating external or table-only QA reports

Reports written from the string tables alone can be wrong about runtime context. Verify each suggestion against engine code and prefabs before applying it. Typical false positives are forcing ALL CAPS on a suffix that code appends after a Title Case name, merging a whole object with its part, and guessing the pronunciation of foreign proper names for suffix rules (consult section 8 of the locale playbook). Apply the confirmed items and reject the rest with a stated reason in the Pass 2 summary.

---

## Ongoing Practices (every phase, every release)

### Context map maintenance
- `CONTEXT_MAP.md` is the single source of meaning. When the game changes (a new screen, a new system, a renamed mechanic, new lore), `context-cartographer` updates the map before the next run, and the user answers the new questions. Every change gets a dated line under the map's decisions.
- A word problem found in testing is fixed in the map first (what the line really is, where it shows), then in the translation. Fixing only the translation leaves the next new line to fail the same way.

### Translation memory (TM)
- `tm.py` keeps a SQLite translation memory per project (`--mode add --status approved` for the studio reference, `--mode approve` for the developer decisions of every change report). Neighbours are found by character n-gram similarity, same category and speaker first. Pass 1 of a new batch gets the closest approved lines as hints, the jury gets them as evidence.
- Exact matches keep their approved text unless the context changed. A string that changed in source is always retranslated, never patched.

### String freeze and delta localization
- Declare a string freeze date per milestone. After it, source edits require a ticket. Localize deltas only. Diff the new source export against the frozen one (key added, changed or removed), run Phases 1 to 3 on the changed keys and keep unchanged keys untouched so TM and checksums stay valid.

### Regression
- Every delta run re-executes the Phase 3 gate on the **whole** locale file, not only on the delta, and a blind critic or jury sample of 50 to 100 unchanged lines guards against drift when the context map or bible changed.

### In-context LQA
- After the automated gate, a native tester plays the build (or reviews screenshots mapped to keys) with a checklist. Clipping, overlap, wrapping (CJK line break rules, Korean word wrap), wrong register in context, placeholders rendering with the wrong article, case or particle, dynamic plurals, platform button glyphs and fallback fonts. Every finding references the `key`, and fixes go through Pass 2 and the Phase 3 gate again.

### Pseudo-localization
- Run it in Phase 0 and again whenever new UI is added. Use a 1.3 to 1.4× expansion with accented Latin and a few CJK characters. Anything that does not survive pseudo localization will not survive `de-DE` or `ja-JP`.

### Versioning and rollback
- Tag or branch the localization files per milestone (`l10n/<locale>/<version>`) and store `checksums_before.txt`, `checksums_after.txt`, the critique files, the change reports and the Pass 2 summaries alongside. A rollback restores the tagged files and re-runs the Phase 3 gate. Never hand edit engine tables outside the pipeline.
