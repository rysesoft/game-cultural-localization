# 4-Phase Culturalization Methodology & Automated QA Runbook

Use this runbook whenever localizing or overhauling a game locale, regardless of engine or string-table format: Unity Localization `.asset` tables, Unreal `.po` / `.csv`, Godot `.csv` / `.po`, plain JSON (dict or list), TSV, or ICU message bundles. The four phases are numbered **0–3** everywhere in this plugin (`SKILL.md`, `rules/AGENTS.md`, agents, `scripts/localization_pipeline_template.workflow.py`, and `scripts/orchestrator_stub.py` use the same names).

| Phase | Name | Main actor | Key output |
|---|---|---|---|
| 0 | Pre-flight: codebase, font & transcreation audit | human + CLI tools | `checksums_before.txt`, `glossary.csv`, `<LOCALE>_BIBLE.md`, `transcreation_ledger.csv`, font report |
| 1 | Clean-room culturalization (Pass 1) | `game-culturalizer` | `pass1_<locale>_<batch>.json` |
| 2 | Blind native-ear critique + Pass 2 colloquial rewrite | `make_blind_slice.py` → `native-ear-critic` → `validate_critique.py` → `game-culturalizer` | `blind_<locale>_<batch>.json`, `critique_<locale>_<batch>.json`, `final_<locale>_<batch>.json` |
| 3 | Automated LQA, UI overflow & font gate | `lqa_linter.py --fail-on-error`, `ui_expansion_checker.py --fail-on-high`, `font_glyph_scanner.py` | reports (`--json`), exit codes `0`, `checksums_after.txt` |

All commands below are run from the plugin's `skills/game-cultural-localization/` directory (`<plugin_dir>` is `~/.gemini/config/plugins/game-cultural-localization` or `<project>/.agents/plugins/game-cultural-localization`). Every script is pure Python 3.9+ standard library, reads UTF-8 with or without BOM, and prints UTF-8 on any console. Flag details: [scripts/CLI_REFERENCE.md](../scripts/CLI_REFERENCE.md).

### Shared file conventions

- **Working field names:** `key`, `en` (source), `dst` (target) by default; override with `--key-field / --src-field / --dst-field` (or `--key-col / --target-col` for the slice tool) when the project table uses other names (for example a locale-named column `de-DE`).
- **Optional context fields:** `category` (`ui_button`, `ui_toast`, `tutorial`, `item`, `lore`, `dialogue`, …), `speaker`, `archetype` (A1–A5, see `SKILL.md`), `context`, `max_chars`, `plural` (ICU category).
- **Engine token syntaxes supported everywhere:** `{0}` / `{name}` (Unity, .NET, Python), `%s` / `%d` / `%1$s` (printf, Godot), ICU `{count, plural, one {…} other {…}}`, Unreal `{Name}` and Hangul post-position `|hpp(…)`, rich text `<b> <i> <u> <color=…> <size=…> <sprite=…> <style=…> <link=…> <br>`, BBCode `[b] [i] [color=…] [url=…]`. Engine-specific notes are marked **(Unity)**, **(Unreal)**, **(Godot)**.
- **Glossary / termbase:** `glossary.csv`, UTF-8, header `term_en,<locale>[,<locale>…],notes`. One row per source term; a non-empty locale cell is a **locked** rendering that `lqa_linter.py --glossary` enforces (the target of a string whose source contains `term_en` must contain the locked rendering; alternatives may be separated with `|`); an empty cell means "not locked for this locale yet". Glossary findings are `[GLOSSARY]` warnings by default; the gates below pass `--glossary-severity ERR` so they block. `notes` holds part of speech, collision pairs, and forbidden alternatives (`forbidden: Auftrag`). Example:

  ```csv
  term_en,de-DE,fr,ja-JP,notes
  Contract,Vertrag,contrat,契約,"customer job; collision pair with Order — forbidden: Auftrag"
  Order,Auftrag,commande,注文,"machine queue item; collision pair with Contract"
  Stamina,Ausdauer,endurance,スタミナ,"player stat; never Haltbarkeit (Durability)"
  ```

- **Naming:** `<LOCALE>_BIBLE.md` (for example `DE-DE_BIBLE.md`), `pass1_<locale>_<batch>.json`, `blind_<locale>_<batch>.json`, `critique_<locale>_<batch>.json`, `final_<locale>_<batch>.json`, `lqa_<locale>.json`.

---

## Phase 0: Pre-Flight Codebase, Font & Transcreation Audit

**Inputs:** engine string tables, game code, fonts/atlases, UI prefabs or scenes, existing glossary if any.
**Outputs:** `checksums_before.txt`, concatenation seam list (ledger type `concat`), font report, `glossary.csv`, `<LOCALE>_BIBLE.md`, `transcreation_ledger.csv`, pseudo-localization findings.

1. **Baseline file checksums.** Record SHA-256 hashes of all localization files so you can prove at the end that only the intended target-locale files changed.
   ```bash
   # Windows PowerShell
   Get-ChildItem -Recurse <loc_dir> -File | Get-FileHash -Algorithm SHA256 | Sort-Object Path | Format-Table Hash,Path -AutoSize | Out-File checksums_before.txt
   # macOS / Linux
   find <loc_dir> -type f -print0 | sort -z | xargs -0 sha256sum > checksums_before.txt
   ```
2. **Code concatenation & slot scan.** Search game code (`.cs`, `.cpp`, `.gd`, `.ts`, Blueprints exported as text) for string concatenation, `string.Format` / `FText::Format` / `tr()` with `%`, Smart Strings, leading/trailing spaces (`' is assigned.'`, `'Total: '`), auto-appended colons, and status+noun slots (`"x3 " + status + " " + itemName`). Every hit becomes a ledger row of type `concat` with the constraint spelled out.
3. **Font glyph pre-check.** Before translating into diacritic-heavy (`pl-PL`, `lt-LT`, `tr-TR`, `fr`, `es-ES`, `pt-*`) or CJK (`ja-JP`, `ko-KR`, `zh-CN`, `zh-Hant`) locales, scan every font the UI can fall back to (`.ttf`, `.otf`, `.ttc` collections, **(Unity)** TextMeshPro `*.asset` atlases) against a representative sample or the playbook's character inventory. Decide now whether ALL-CAPS German may use `SS` instead of `ẞ`, and whether `« »` / `„“` / `「」` are safe or ASCII quotes are required.
   ```bash
   python scripts/font_glyph_scanner.py --input <sample_or_previous_locale.json> --dst-field dst --font <ui_font.ttf> --font <fallback.ttc> --font <TMP_atlas.asset>
   ```
4. **UI ground-truth verification.** For every short or ambiguous key find where it is bound (**(Unity)** `m_KeyId` in `.prefab`/`.unity`, `LocalizedString` fields; **(Unreal)** `NSLOCTEXT` / string table references in widgets; **(Godot)** `tr()` calls and scene `text` properties) and read the surrounding UI: is the key a tab, a button, a progress status, a suffix appended after a machine name? Open the sprite for ambiguous asset names before naming them. Align the target to the object actually on screen when the source drifts between two names for one object.
5. **Lock `glossary.csv` and build `<LOCALE>_BIBLE.md`.** The bible records: locked terminology (collision pairs separated explicitly), every character's register (`du/Sie`, `tu/vous`, `tú/usted`, `tu/Lei`, 반말/해요체/합쇼체, Japanese first-person pronouns and sentence-enders), archetype mapping (speaker → A1–A5), the project's UI register, number/date/currency formats, and platform button conventions.
6. **Start the transcreation ledger** (schema in `transcreation_ledger_guide.md`): pop-culture quotes (verify official local dubs by web search before translating), idioms, spoiler guards, hidden plurality/gender facts, concatenation seams.
7. **Pseudo-localize once.** Run the source through a pseudo-locale (lengthen 30–40 %, add diacritics and a few CJK characters, bracket each string) and play the build: hard-coded strings, concatenations, clipped controls, and tofu show up before any real translation money is spent.

**Gate 0 (all must hold):** checksums recorded · every concatenation seam has a ledger row · font scan has 0 missing glyphs for the planned character set (or a documented fallback font) · `glossary.csv` has a non-empty cell for every collision-pair term in the target locale · `<LOCALE>_BIBLE.md` names a register for every speaker and for UI · pseudo-localization issues are filed.

---

## Phase 1: Clean-Room Culturalization — Pass 1 (`game-culturalizer`)

**Inputs:** clean-room source batches `in_<locale>_<batch>.json` (`key`, `en`, optional context fields; **never** legacy machine-translated target text), `glossary.csv`, ledger, `<LOCALE>_BIBLE.md`, `references/<locale>.md`.
**Outputs:** `pass1_<locale>_<batch>.json` (same keys, same order, target text in `dst`).

1. Export the table to the working JSON format and split into batches of roughly 80–150 strings grouped by category/speaker (keep one speaker's scene together).
2. Run `game-culturalizer` with `pass: 1` per batch (batches can run in parallel; they are independent).
3. Run the linter on each batch immediately so token or glossary slips are caught before the critic sees them:
   ```bash
   python scripts/lqa_linter.py --input pass1_<locale>_<batch>.json --locale <locale> --src-field en --dst-field dst --glossary glossary.csv --glossary-severity ERR --fail-on-error
   ```

**Gate 1:** every batch file has exactly the input keys · linter exit `0` on every batch · no source-language text left in `dst` (the `[UNTRANSLATED]` check) · glossary violations 0.

---

## Phase 2: Blind Native-Ear Critique (`native-ear-critic`) + Pass 2 Colloquial Rewrite (`game-culturalizer`)

**Why this phase is the secret weapon:** reviewers who see the English forgive English sentence order. Real players never see the English.

**Inputs:** `pass1_<locale>_<batch>.json`.
**Outputs:** `blind_<locale>_<batch>.json`, `critique_<locale>_<batch>.json`, `final_<locale>_<batch>.json`, Pass 2 summary.

1. **Generate the blind slice (mandatory; this is what makes the critique blind):**
   ```bash
   python scripts/make_blind_slice.py pass1_<locale>_<batch>.json --locale <locale> --out blind_<locale>_<batch>.json --key-col key --target-col dst --context-cols category,speaker,archetype
   ```
   The output contains only `key`, the listed context columns, and the target text. The script refuses to write a file that would still contain a source column and exits `2` on missing columns or unknown locales.
2. **Run the critic** on the blind file only (as a subagent, via `scripts/localization_pipeline_template.workflow.py`, via `scripts/orchestrator_stub.py` with your own provider, or as a plain system prompt with any LLM API). It reads `blind_<locale>_<batch>.json` and `references/<locale>.md`, nothing else, and writes `critique_<locale>_<batch>.json` in the fixed schema (`score` 1–5 naturalness, `issue_type`, `reason`, `suggested`, optional `needs_source_check`; see `agents/native-ear-critic.md`).
3. **Validate the critique** before anyone consumes it:
   ```bash
   python scripts/validate_critique.py critique_<locale>_<batch>.json --slice blind_<locale>_<batch>.json
   ```
   Exit `1` (schema or key mismatch) means the critique is re-run, not patched by hand.
4. **Pass 2 rewrite:** run `game-culturalizer` with `pass: 2`, the Pass 1 file and the critique. It rewrites every flagged key (critical first), re-checks each suggestion against the source, glossary, tokens and `max_chars`, resolves `needs_source_check` items against code/prefabs/sprites, and writes `final_<locale>_<batch>.json` plus a summary of adopted / adapted / rejected suggestions.
5. **Blind-critic context guardrail:** the critic cannot see source, code, or sprites, so it can mislabel items, decals, tabs, and buttons. Every rename of an item, decal, tab, or button suggested by the critic is cross-checked against code, prefabs, and sprites before acceptance.

**Gate 2 (measurable):** blind slice contains no source column (the slice tool guarantees it; spot-check the header) · `validate_critique.py` exit `0` for every batch · 100 % of entries with `score ≤ 2` rewritten, 100 % of `score 3–4` rewritten or explicitly rejected with a reason · a second blind pass on the final batch shows **≥ 95 % of lines at score 5 and 0 lines at score ≤ 2** (sample at least 100 lines or the whole batch if smaller) · `needs_source_check` items all resolved in the summary.

The rewrite rate is a consequence, not a target: a Pass 1 that needs 10 % rewriting is better than one that needs 40 %. Historic projects landed between 25 % and 50 % on first runs; use that only to sanity-check a suspiciously low flag count.

---

## Phase 3: Automated CLI LQA, UI Overflow & Font Gate

**Inputs:** merged `final_<locale>.json` (all batches), `glossary.csv`, fonts.
**Outputs:** `lqa_<locale>.json`, `ui_<locale>.json`, font report, `checksums_after.txt`, engine tables written back.

```bash
# 1. Anti-translationese + regional leak scan, placeholder/tag/whitespace/punctuation parity, glossary enforcement
python scripts/lqa_linter.py --input final_<locale>.json --locale <locale> \
  --src-field en --dst-field dst --glossary glossary.csv --glossary-severity ERR \
  --forbid-chars ";—–" --forbid-spaced-hyphen --strict-whitespace \
  --json lqa_<locale>.json --fail-on-error

# 2. UI button, tab, and badge overflow risk (per-locale expansion ratio + CJK width); blocks on HIGH
python scripts/ui_expansion_checker.py --input final_<locale>.json --locale <locale> \
  --src-field en --dst-field dst --json ui_<locale>.json --fail-on-high

# 3. Font missing-glyph (tofu □) scan against every font in the fallback chain
python scripts/font_glyph_scanner.py --input final_<locale>.json --dst-field dst \
  --font <ui_font.ttf> --font <fallback.ttc> --font <TMP_atlas.asset>
```

Use `--forbid-chars`, `--forbid-spaced-hyphen`, and `--strict-whitespace` only when the project's bible declares those rules (CJK playbooks forbid dashes; concatenation seams require exact leading/trailing spaces). Add `--fail-on-warn` for release candidates. Set `--placeholder-style` / `--tag-style` explicitly (**(Unreal)** `unreal`, **(Godot)** `godot` + `bbcode`, ICU bundles `icu`) when auto-detection is ambiguous; add `--strict` to the font scan when no runtime fallback font exists. Project-wide defaults can live in `l10n.config.json` (`--config`).

**Exit codes (all three tools):** `0` clean · `1` findings (errors, or warnings with `--fail-on-warn` / HIGH with `--fail-on-high`) · `2` usage or input error (unknown locale, malformed file, missing column, unreadable font). Exit `2` is never "pass".

**Gate 3:** all three commands exit `0` · 100 % of HIGH overflow risks resolved (shorter string, approved `max_chars` change, or UI change filed with the key) · 0 missing glyphs or a documented fallback font that covers them · engine tables written back and re-imported without warnings · `checksums_after.txt` differs from `checksums_before.txt` **only** in the target-locale files · **(Unity)** Smart String flags (`IsSmart`) unchanged for every entry that uses `{…}` formatting · **(Unreal)** `.po` re-gathered with 0 fuzzy entries · **(Godot)** CSV re-imported with the same column count.

### Validating external / table-only QA reports

Reports written from the string tables alone can be wrong about runtime context. Verify each suggestion against engine code and prefabs before applying it. Typical false positives: forcing ALL CAPS on a suffix that code appends after a Title-Case name, merging a whole object with its part, and guessing the pronunciation of foreign proper names for suffix rules (consult the locale playbook's section 8). Apply the confirmed items; reject the rest with a stated reason in the Pass 2 summary.

---

## Ongoing Practices (every phase, every release)

### Glossary / termbase management
- `glossary.csv` is the single source of truth; the bible explains, the glossary enforces. Add a term the moment two keys could collide. Changes go through a changelog line in `<LOCALE>_BIBLE.md` (`date · term · old → new · reason`), and every change triggers a linter re-run with `--glossary` on all final files.
- Part of speech, number/gender, and the forbidden alternatives live in `notes`; the linter only enforces the locked rendering, humans enforce the notes.

### Translation memory (TM)
- Keep `tm_<locale>.json` (`{"<en>": "<dst>"}`) built from every approved `final_<locale>` file. Before Pass 1 of a new batch, pre-fill exact matches and mark them `"tm": "exact"` so the culturalizer keeps them unless context changed; fuzzy candidates (same key prefix, small edit distance) are shown as hints only. A string that changed in source is always retranslated, never patched.

### String freeze & delta localization
- Declare a string freeze date per milestone; after it, source edits require a ticket. Localize deltas only: diff the new source export against the frozen one (`key` added / changed / removed), run Phases 1–3 on the changed keys, and keep unchanged keys untouched so TM and checksums stay valid.

### Regression
- Every delta run re-executes the Phase 3 gate on the **whole** locale file, not only on the delta, and a blind critic sample of 50–100 unchanged lines guards against drift when the glossary or bible changed.

### In-context LQA
- After the automated gate, a native tester plays the build (or reviews screenshots mapped to keys) with a checklist: clipping, overlap, wrapping (CJK line-break rules, Korean word-wrap), wrong register in context, placeholders rendering with wrong article/case/particle, dynamic plurals, platform button glyphs, and fallback fonts. Every finding references the `key`; fixes go through Pass 2 and the Phase 3 gate again.

### Pseudo-localization
- Run in Phase 0 and again whenever new UI is added. Use a 1.3–1.4× expansion with accented Latin plus a few CJK characters; anything that does not survive pseudo-localization will not survive `de-DE` or `ja-JP`.

### Versioning & rollback
- Tag or branch the localization files per milestone (`l10n/<locale>/<version>`); store `checksums_before/after.txt`, the critique files, and the Pass 2 summaries alongside. Rollback = restore the tagged files and re-run the Phase 3 gate; never hand-edit engine tables outside the pipeline.
