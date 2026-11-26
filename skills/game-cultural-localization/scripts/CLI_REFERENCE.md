# CLI Reference — game-cultural-localization scripts (v2.1.0)

All tools live in `skills/game-cultural-localization/scripts/`, need **Python 3.9+ with the standard
library only**, run on Windows / macOS / Linux, force UTF-8 console output, and share one
exit-code contract:

| Exit code | Meaning |
|---|---|
| `0` | clean (no findings / risks / missing glyphs; critique valid; pipeline passed) |
| `1` | findings: `ERR` (or `WARN` with `--fail-on-warn`), `HIGH` risks with `--fail-on-high`, missing glyphs, invalid critique |
| `2` | usage / input error: unknown locale, missing file or column, broken JSON/CSV/font, bad regex, argparse error |

Every script takes its main file either as the first positional argument or as `--input FILE` (`validate_critique.py`: positional or `--critique FILE`); both spellings are equivalent and giving both with different values is a usage error.

Common flags (every script): `--version`, `--help`, `--config l10n.config.json`,
`--json [FILE]` (JSON report to stdout, or to FILE), `--output FILE` (copy of the printed report),
`--max-report N` (truncate text output; default unlimited), `--debug` (tracebacks for internal errors).
Explicit CLI flags always override `--config` values. Unknown locales are **never** silently accepted.

Supported locales (15): `en`, `tr-TR`, `de-DE`, `fr`, `es-ES`, `it-IT`, `pt-BR`, `pt-PT`, `pl-PL`, `lt-LT`, `ru-RU`, `ja-JP`, `ko-KR`, `zh-CN`, `zh-Hant`.
Aliases are normalised (`de`, `de_DE`, `pt_BR`, `zh-TW`, `zh-Hans`, `jp`, `kr`…); `zh-HK`/`zh-MO` map to `zh-Hant` with variant `hk`; bare `pt` is rejected as ambiguous.

Supported input tables (all BOM-tolerant):

| Format | Notes |
|---|---|
| JSON list `[{key, en, dst, category, speaker, max_chars…}]` | `id` is accepted as key, `table` is prefixed to the key |
| JSON map `{key: {en, dst}}` or `{key: "text"}` | the plain-string map is target-only |
| CSV / TSV | delimiter sniffed among `, ; tab |` (or `--delimiter`); multi-locale tables (`key,en,de-DE,fr`) work with `--dst-field de-DE` |
| gettext PO | multi-line strings, plurals (one row per form, key `msgid|[n]`), `#, fuzzy`, `msgctxt` (key `ctxt|msgid`), `#~` obsolete entries skipped |
| Unity Localization StringTable `.asset` | `m_TableData / m_Id / m_Localized`; pair with the source table via `--src-input en.asset`, resolve key names via `--shared-table Shared.asset` |

Missing `--src-field`/`--dst-field` columns are reported with the available column list (exit 2); use `--target-only` for source-free files.

---

## lqa_linter.py — anti-translationese & technical LQA linter

```
python lqa_linter.py --input <table> --locale <loc> [options]
```

| Flag | Meaning |
|---|---|
| `--input` | table to lint (JSON / CSV / TSV / PO / Unity `.asset`) |
| `--locale` | target locale (see aliases above) |
| `--variant` | regional variant that relaxes rules, e.g. `hk` for zh-Hant (implied by `zh-HK`) |
| `--src-field` / `--dst-field` / `--key-field` | column names (defaults `en` / `dst` / `key`) |
| `--target-only` | input has no source column (blind slices): parity checks skipped, locale rules still run |
| `--src-input` / `--shared-table` | Unity `.asset` pairing / key names |
| `--delimiter` | CSV delimiter override |
| `--placeholder-style` | `auto` (braces + printf), `unity` (`{0}`, `{0:plural:…}`, `{{` escape), `unreal` (`{Name}`, backtick escape, `|plural(...)`), `godot` (`%s %d` + `{name}`), `icu` (`{count, plural, one {…} other {…}}` with nested slots), `printf` (`%1$s %ld %.2f %@`; order matters unless positional), `python` (`{name}` + `%(name)s`) |
| `--placeholder-regex` | extra project placeholder syntax, e.g. `'\$\w+\$'` or `'\[[A-Z_]+\]'` |
| `--tag-style` | `auto` (angle tags + known BBCode), `tmp` (TextMeshPro set: sprite, link, br, mark, font, align, size, color/`<#hex>`, style, b/i/u/s, nobr, sup/sub, voffset, cspace, indent, line-height, alpha, gradient, …), `html`, `bbcode` (Godot `[b][/b]`, `[color=…]`) — parity is checked as a multiset **and** open/close order |
| `--rules DIR_OR_FILE` | extra rule files (repeatable); built-ins come from `rules/<locale>.json` + `rules/custom/*.json` |
| `--no-builtin-rules` | use only `--rules` files |
| `--glossary CSV` | termbase: `term_en,<locale>,…,notes` (notes may contain `forbidden: X; Y`) or `source,target[,locale][,forbidden]`; `|` separates alternatives, `re:` prefix = regex |
| `--glossary-severity` | `WARN` (default) or `ERR` |
| `--forbid-chars` | characters banned in targets, e.g. `";—–"` |
| `--forbid-spaced-hyphen` / `--allow-spaced-hyphen-substr` | ban `" - "` except in listed substrings |
| `--strict-whitespace` | leading/trailing whitespace (space, tab, NBSP) and trailing-newline parity |
| `--no-untranslated-check` | disable the `[UNTRANSLATED]` warning (target identical to source) |
| `--fail-on-error` | default behaviour (ERR → exit 1); accepted so runbooks can be explicit |
| `--fail-on-warn` | also exit 1 on WARN |

Finding codes: `EMPTY`, `FUZZY`, `PLURAL_FORMS`, `ENCODING`, `CONTROL_CHAR`, `FORBIDDEN_CHAR`, `SPACED_HYPHEN`, `PLACEHOLDER`, `RICH_TAG`, `LEADING_SPACE`, `TRAILING_SPACE`, `TRAILING_NEWLINE`, `UNTRANSLATED`, `GLOSSARY` and the locale rule ids (`DE-EHE`, `KO-PLACEHOLDER-PARTICLE`, …).

Rule files (`rules/<locale>.json`, schema in `rules/rules.schema.json`): `id`, `severity` (ERR|WARN), `pattern`, `flags` (i m x s), `message`, `context` (any|ui|dialog|player|button), `skip_variants`, `variant_severity`, `examples{match,nomatch}`.
Row metadata drives contexts: `category`/`context`/`tags` containing ui/button/dialog/player, `player: true`, keys containing `BTN`/`BUTTON`. Suppress a rule on one row with `"lqa_ignore": "DE-EHE, PROJ-1"`.

JSON report: `{tool, version, locale, variant, input, entries_checked, rules_loaded, summary{errors, warnings}, findings[{severity, code, key, message, target}], exit_code}` — findings are in input order (deterministic).

Examples:

```
python lqa_linter.py --input final_de-DE.json --locale de-DE --src-field en --dst-field de-DE --fail-on-error --json lqa_de-DE.json
python lqa_linter.py --input strings.po --locale pl-PL --placeholder-style printf --fail-on-warn
python lqa_linter.py --input Assets/Localization/UI_ja-JP.asset --src-input Assets/Localization/UI_en.asset --shared-table Assets/Localization/UI\ Shared\ Data.asset --locale ja-JP
python lqa_linter.py --input blind_fr_01.json --locale fr --target-only --dst-field target
python lqa_linter.py --input table.csv --locale zh-HK --glossary termbase.csv --glossary-severity ERR --config l10n.config.json
```

---

## ui_expansion_checker.py — UI overflow risk

```
python ui_expansion_checker.py --input <table> --locale <loc> [--fail-on-high] [options]
```

| Flag | Meaning |
|---|---|
| `--input`, `--locale`, `--src-field`, `--dst-field`, `--key-field`, `--src-input`, `--shared-table`, `--delimiter` | as for the linter |
| `--factor` | override the locale expansion ceiling (defaults: de-DE 1.35; fr, es-ES, pt-BR, pt-PT, pl-PL, lt-LT, ru-RU 1.30; it-IT, tr-TR 1.25; ja-JP 1.30, ko-KR 1.40, zh-CN/zh-Hant 1.10 as *visual* ratios — see the module docstring and each playbook §9) |
| `--warn-factor` / `--high-factor` | WARN when ratio > allowed × 1.0; HIGH when ratio > allowed × 1.5 (allowed = factor + short-string bonus `max(0,(10−src_width)/10)`, +0.1 for sentences > 24 cells) |
| `--max-width` | global width budget (Latin cells); anything wider is HIGH. Per-row `max_chars`/`max_width`/`max_length` metadata and the config `max_width` table (per key / per locale / `*`) take precedence |
| `--cjk-cell-width` | width of a Wide/Fullwidth glyph (default 1.8 cells) |
| `--ambiguous-wide` | count East-Asian *Ambiguous* glyphs (`… “ ” →`) as wide — on by default for ja/ko/zh |
| `--tag-style` | tags stripped before measuring |
| `--fail-on-high` | exit 1 on HIGH (without it the exit code is always 0 and the report says so) |
| `--fail-on-warn` | exit 1 on any risk |

Risks are sorted HIGH→WARN, ratio desc, key. JSON: `{tool, version, locale, factor, cjk_cell_width, ambiguous_wide, entries_checked, summary{high, warn}, risks[{level, key, src, dst, src_width, dst_width, ratio, allowed, reason}], exit_code}`.

```
python ui_expansion_checker.py --input final_de-DE.json --locale de-DE --src-field en --dst-field de-DE --fail-on-high
python ui_expansion_checker.py --input ui.csv --locale ja-JP --max-width 14 --json ui_ja.json
```

---

## font_glyph_scanner.py — missing glyph (tofu) scan

```
python font_glyph_scanner.py --input <table|text> --font <font> [--font <font> …] [options]
```

| Flag | Meaning |
|---|---|
| `--input` | JSON / CSV / TSV / PO / Unity `.asset` table or a plain text file |
| `--dst-field` | target column (default `dst`) |
| `--font` | `.ttf` / `.otf` / `.ttc` (every sub-font merged) / `.woff` or TextMeshPro FontAsset `.asset`; repeatable, coverage is the union. `.woff2` and corrupt fonts → exit 2 with a clear message |
| `--strict` | missing glyphs are ERR even when a TMP asset is dynamic (`m_AtlasPopulationMode` 1/2) or has fallbacks (otherwise those are WARN, exit 0) |
| `--also-upper` | also scan the upper-cased text (runtime `.ToUpper()`, `<uppercase>`; catches Turkish `İ`, German `ẞ`) |

Ignored characters: controls, space/NBSP/ideographic space, zero-width & variation selectors, combining marks (NFC), rich-text tags, `{placeholders}`. JSON: `{tool, version, input, fonts[], lenient, unique_chars, summary{missing, severity}, missing[{codepoint, char, name, count, first_key}], exit_code}`.

```
python font_glyph_scanner.py --input final_ja-JP.json --dst-field ja-JP --font C:\Windows\Fonts\msgothic.ttc
python font_glyph_scanner.py --input final_de-DE.json --dst-field de-DE --font "Assets/Fonts/Bebas SDF.asset" --also-upper --strict
```

---

## make_blind_slice.py — target-only slice for the blind critic

```
python make_blind_slice.py --input <table> --locale <loc> --out <path> [--key-col key] [--target-col <loc>] [--context-cols category,speaker]
```

| Flag | Meaning |
|---|---|
| `--input` (or positional) | JSON / CSV / TSV / PO / Unity `.asset` |
| `--locale` | recorded in the slice; also tried as the target column name for multi-locale tables |
| `--out` | `.json` (`{locale, source_file, blind: true, entries[{key, category?, speaker?, target}]}`) or `.csv` / `.tsv` |
| `--key-col`, `--target-col`, `--source-col` | column names (defaults `key`, auto, `en`) |
| `--context-cols` | context columns to keep (default `category,speaker`); the source column is refused, and any context value equal to a source text aborts with exit 2 |
| `--src-input`, `--shared-table`, `--delimiter` | Unity / CSV options |
| `--skip-empty` | drop empty targets |
| `--max-rows N` | batch size |

---

## validate_critique.py — critic output schema check

```
python validate_critique.py --critique critique_<locale>_<batch>.json [--slice blind_<locale>_<batch>.json] [--locale <loc>]
```

`--critique` (or positional) is the critic output file. Validates the fixed schema `{locale, source_file, entries[{key, score 1-5, issue_type, reason, suggested}], summary{total, flagged, critical}}`
(only score < 5 entries; `issue_type` ∈ translationese | register | tense | regional_leak | gender_leak | ui_verb | placeholder_grammar | terminology | other;
`critical` = score ≤ 2). With `--slice` every key must exist in the slice and `suggested` must keep placeholder/tag parity
with the slice target (an entry typed `placeholder_grammar` may deliberately repair tokens). `--placeholder-style` / `--tag-style` as for the linter.

---

## orchestrator_stub.py — API-independent Phase 0-3 runner

```
python orchestrator_stub.py --input <source table> --locale <loc> --workdir <dir> (--dry-run | --provider module:function) [options]
```

| Flag | Meaning |
|---|---|
| `--input` | source table; the `--src-field` column (default `en`) holds the English text |
| `--workdir` | receives `<LOCALE>_BIBLE.md` (stub if missing), `pass1_batch_NN.json`, `blind_<loc>_NN.json`, `critique_<loc>_NN.json`, `final_batch_NN.json`, `lqa_<loc>_NN.json` |
| `--dry-run` | offline `DryRunProvider` (pseudo-translation, empty critique) — exercises the whole file flow and the gate without an LLM |
| `--provider module:function` | any callable `complete(system: str, user: str) -> str` (OpenAI, Anthropic, Gemini, local…) |
| `--key-field`, `--placeholder-style`, `--tag-style`, `--batch-size`, `--font` | pipeline options |

Phases: 0 pre-flight (locale, rules, bible, optional font scan) → 1 Pass-1 → 2 blind slice → critic → `validate_critique` → Pass-2 → 3 gate (linter + UI checker + font scan). Exit 1 when the gate fails or a critique is invalid.

---

## localization_pipeline_template.workflow.py — Antigravity `/run-workflow` template

Not a standalone Python module (uses the workflow DSL with top-level `await`). Run it from Antigravity:

```
/run-workflow Run skills/game-cultural-localization/scripts/localization_pipeline_template.workflow.py
   with args {"locale": "de-DE", "scratch_dir": "loc_work", "batches": ["01", "02"], "plugin_dir": "<plugin path>", "fonts": [], "placeholder_style": "unity", "tag_style": "tmp"}
```

Phase 0 pre-flight → Phase 1 Pass 1 (`game-culturalizer`, parallel per batch, failed batches retried sequentially) → Phase 2 `make_blind_slice` → `native-ear-critic` → `validate_critique` → Pass 2 → Phase 3 gate (`lqa_linter --fail-on-error`, `ui_expansion_checker --fail-on-high`, `font_glyph_scanner`).

---

## l10n.config.json

```json
{
  "locales": ["de-DE", "fr", "ja-JP"],
  "src_field": "en", "dst_field": "dst", "key_field": "key",
  "placeholder_style": "unity", "tag_style": "tmp", "placeholder_regex": "\\$\\w+\\$",
  "rules_dir": "loc/rules", "glossary": "loc/termbase.csv", "glossary_severity": "ERR",
  "max_width": {"*": 40, "BTN_APPLY": 12, "ja-JP": 30}, "expansion": {"de-DE": 1.4}, "cjk_cell_width": 1.8,
  "ambiguous_wide": false, "fail_on_warn": false, "forbid_chars": ";—", "forbid_spaced_hyphen": true, "strict_whitespace": true
}
```

Unknown keys or wrong types abort with exit 2. Relative `rules_dir` / `glossary` paths resolve from the config file's folder.

---

## Tests

```
python -m unittest discover tests          # from the repository root (or tests/run_all.ps1)
```
