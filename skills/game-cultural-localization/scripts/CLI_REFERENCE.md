# CLI Reference. game-cultural-localization scripts (v3.0.0)

All tools live in `skills/game-cultural-localization/scripts/`, need **Python 3.9+ with the standard
library only**, run on Windows, macOS and Linux, force UTF-8 console output and share one
exit-code contract.

| Exit code | Meaning |
|---|---|
| `0` | clean (no findings, risks or missing glyphs, critique valid, pipeline passed) |
| `1` | findings. `ERR` (or `WARN` with `--fail-on-warn`), `HIGH` risks with `--fail-on-high`, missing glyphs, invalid critique, a model tool below its gate |
| `2` | usage or input error. Unknown locale, missing file or column, broken JSON, CSV or font, bad regex, argparse error, missing API key |

Every script takes its main file either as the first positional argument or as `--input FILE` (`validate_critique.py` takes the positional or `--critique FILE`). Both spellings are equivalent and giving both with different values is a usage error.

Common flags of every script are `--version`, `--help`, `--config l10n.config.json`,
`--json [FILE]` (JSON report to stdout, or to FILE), `--output FILE` (copy of the printed report),
`--max-report N` (truncate text output, default unlimited) and `--debug` (tracebacks for internal errors).
Explicit CLI flags always override `--config` values. Unknown locales are **never** silently accepted.

The 15 supported locales are `en`, `tr-TR`, `de-DE`, `fr`, `es-ES`, `it-IT`, `pt-BR`, `pt-PT`, `pl-PL`, `lt-LT`, `ru-RU`, `ja-JP`, `ko-KR`, `zh-CN` and `zh-Hant`.
Aliases are normalised (`de`, `de_DE`, `pt_BR`, `zh-TW`, `zh-Hans`, `jp`, `kr` and more). `zh-HK` and `zh-MO` map to `zh-Hant` with variant `hk`, a bare `pt` is rejected as ambiguous.

Supported input tables, all BOM tolerant.

| Format | Notes |
|---|---|
| JSON list `[{key, en, dst, category, speaker, max_chars}]` | `id` is accepted as key, `table` is prefixed to the key |
| JSON map `{key: {en, dst}}` or `{key: "text"}` | the plain-string map is target only |
| CSV / TSV | delimiter sniffed among `,` `;` tab and `\|` (or `--delimiter`), multi-locale tables (`key,en,de-DE,fr`) work with `--dst-field de-DE` |
| gettext PO | multi-line strings, plurals (one row per form, key `msgid\|[n]`), `#, fuzzy`, `msgctxt` (key `ctxt\|msgid`), `#~` obsolete entries skipped |
| Unity Localization StringTable `.asset` | `m_TableData / m_Id / m_Localized`. Pair it with the source table via `--src-input en.asset` and resolve key names via `--shared-table Shared.asset` |

Missing `--src-field` or `--dst-field` columns are reported with the available column list (exit 2). Use `--target-only` for source-free files.

---

## lqa_linter.py (anti-translationese and technical LQA linter)

```
python lqa_linter.py --input <table> --locale <loc> [options]
```

| Flag | Meaning |
|---|---|
| `--input` | table to lint (JSON, CSV, TSV, PO or Unity `.asset`) |
| `--locale` | target locale (see the aliases above) |
| `--variant` | regional variant that relaxes rules, for example `hk` for zh-Hant (implied by `zh-HK`) |
| `--src-field` / `--dst-field` / `--key-field` | column names (defaults `en`, `dst`, `key`) |
| `--target-only` | the input has no source column (blind slices). Parity checks are skipped, locale rules still run |
| `--src-input` / `--shared-table` | Unity `.asset` pairing and key names |
| `--delimiter` | CSV delimiter override |
| `--placeholder-style` | `auto` (braces and printf), `unity` (`{0}`, `{0:plural:...}`, `{{` escape), `unreal` (`{Name}`, backtick escape, `\|plural(...)`), `godot` (`%s %d` and `{name}`), `icu` (`{count, plural, one {...} other {...}}` with nested slots), `printf` (`%1$s %ld %.2f %@`, order matters unless positional), `python` (`{name}` and `%(name)s`) |
| `--placeholder-regex` | extra project placeholder syntax, for example `'\$\w+\$'` or `'\[[A-Z_]+\]'` |
| `--tag-style` | `auto` (angle tags and known BBCode), `tmp` (the TextMeshPro set with sprite, link, br, mark, font, align, size, color and `<#hex>`, style, b, i, u, s, nobr, sup, sub, voffset, cspace, indent, line-height, alpha, gradient and more), `html`, `bbcode` (Godot `[b][/b]`, `[color=...]`). Parity is checked as a multiset **and** in open and close order |
| `--rules DIR_OR_FILE` | extra rule files (repeatable). Built-ins come from `rules/<locale>.json` and `rules/custom/*.json` |
| `--no-builtin-rules` | use only `--rules` files |
| `--glossary CSV` | termbase `term_en,<locale>,...,notes` (notes may contain `forbidden: X; Y`) or `source,target[,locale][,forbidden]`. `\|` separates alternatives, the `re:` prefix marks a regex |
| `--glossary-severity` | `WARN` (default) or `ERR` |
| `--forbid-chars` | characters banned in targets, for example `";—–"` |
| `--forbid-spaced-hyphen` / `--allow-spaced-hyphen-substr` | ban `" - "` except in listed substrings |
| `--strict-whitespace` | leading and trailing whitespace (space, tab, NBSP) and trailing-newline parity |
| `--no-untranslated-check` | disable the `[UNTRANSLATED]` warning (target identical to source) |
| `--fail-on-error` | default behaviour (ERR gives exit 1), accepted so runbooks can be explicit |
| `--fail-on-warn` | also exit 1 on WARN |

Finding codes are `EMPTY`, `FUZZY`, `PLURAL_FORMS`, `ENCODING`, `CONTROL_CHAR`, `FORBIDDEN_CHAR`, `SPACED_HYPHEN`, `PLACEHOLDER`, `RICH_TAG`, `LEADING_SPACE`, `TRAILING_SPACE`, `TRAILING_NEWLINE`, `UNTRANSLATED`, `GLOSSARY` and the locale rule ids (`DE-EHE`, `KO-PLACEHOLDER-PARTICLE` and so on).

Rule files (`rules/<locale>.json`, schema in `rules/rules.schema.json`) hold `id`, `severity` (`ERR` or `WARN`), `pattern`, `flags` (`i m x s`), `message`, `context` (`any`, `ui`, `dialog`, `player`, `button`, `formal`), `skip_contexts`, `skip_variants`, `variant_severity` and `examples{match,nomatch}`. A row is `formal` when its category is `dialogue_formal`, `formal`, `official`, `news`, `announcement`, `press`, `lore`, `codex` or `encyclopedia`, or when its key has a `Codex`, `Lore` or `News` segment. The register names `dialogue_casual` and `dialogue_formal` count as dialogue. `skip_contexts` lists row contexts where a rule never applies, `tr-TR` uses it to allow report style (`-mektedir`, `sahip olmak`) in formal text, in-world news and codex lore.
Row metadata drives contexts. `category`, `context` or `tags` containing ui, button, dialog or player, `player: true`, and keys containing `BTN` or `BUTTON`. Suppress a rule on one row with `"lqa_ignore": "DE-EHE, PROJ-1"`.

JSON report `{tool, version, locale, variant, input, entries_checked, rules_loaded, summary{errors, warnings}, findings[{severity, code, key, message, target}], exit_code}`. Findings are in input order (deterministic).

Examples.

```
python lqa_linter.py --input final_de-DE.json --locale de-DE --src-field en --dst-field de-DE --fail-on-error --json lqa_de-DE.json
python lqa_linter.py --input strings.po --locale pl-PL --placeholder-style printf --fail-on-warn
python lqa_linter.py --input Assets/Localization/UI_ja-JP.asset --src-input Assets/Localization/UI_en.asset --shared-table Assets/Localization/UI\ Shared\ Data.asset --locale ja-JP
python lqa_linter.py --input blind_fr_01.json --locale fr --target-only --dst-field target
python lqa_linter.py --input table.csv --locale zh-HK --glossary termbase.csv --glossary-severity ERR --config l10n.config.json
```

---

## ui_expansion_checker.py (UI overflow risk)

```
python ui_expansion_checker.py --input <table> --locale <loc> [--fail-on-high] [options]
```

| Flag | Meaning |
|---|---|
| `--input`, `--locale`, `--src-field`, `--dst-field`, `--key-field`, `--src-input`, `--shared-table`, `--delimiter` | as for the linter |
| `--factor` | override the locale expansion ceiling. Defaults are de-DE 1.35, fr, es-ES, pt-BR, pt-PT, pl-PL, lt-LT and ru-RU 1.30, it-IT and tr-TR 1.25, and ja-JP 1.30, ko-KR 1.40, zh-CN and zh-Hant 1.10 as *visual* ratios (see the module docstring and section 9 of each playbook) |
| `--warn-factor` / `--high-factor` | WARN when the ratio is above allowed × 1.0, HIGH when it is above allowed × 1.5 (allowed is the factor plus a short-string bonus `max(0,(10-src_width)/10)`, plus 0.1 for sentences over 24 cells) |
| `--max-width` | global width budget in Latin cells, anything wider is HIGH. Per-row `max_chars`, `max_width` or `max_length` metadata and the config `max_width` table (per key, per locale or `*`) take precedence |
| `--cjk-cell-width` | width of a Wide or Fullwidth glyph (default 1.8 cells) |
| `--ambiguous-wide` | count East Asian *Ambiguous* glyphs (`… “ ” →`) as wide, on by default for ja, ko and zh |
| `--tag-style` | tags stripped before measuring |
| `--fail-on-high` | exit 1 on HIGH (without it the exit code is always 0 and the report says so) |
| `--fail-on-warn` | exit 1 on any risk |

Risks are sorted HIGH before WARN, then by ratio (descending) and key. JSON report `{tool, version, locale, factor, cjk_cell_width, ambiguous_wide, entries_checked, summary{high, warn}, risks[{level, key, src, dst, src_width, dst_width, ratio, allowed, reason}], exit_code}`.

```
python ui_expansion_checker.py --input final_de-DE.json --locale de-DE --src-field en --dst-field de-DE --fail-on-high
python ui_expansion_checker.py --input ui.csv --locale ja-JP --max-width 14 --json ui_ja.json
```

---

## font_glyph_scanner.py (missing glyph scan)

```
python font_glyph_scanner.py --input <table|text> --font <font> [--font <font> ...] [options]
```

| Flag | Meaning |
|---|---|
| `--input` | JSON, CSV, TSV, PO or Unity `.asset` table, or a plain text file |
| `--dst-field` | target column (default `dst`) |
| `--font` | `.ttf`, `.otf`, `.ttc` (every sub-font merged), `.woff` or a TextMeshPro FontAsset `.asset`. Repeatable, coverage is the union. `.woff2` and corrupt fonts end with exit 2 and a clear message |
| `--strict` | missing glyphs are ERR even when a TMP asset is dynamic (`m_AtlasPopulationMode` 1 or 2) or has fallbacks (otherwise those are WARN, exit 0) |
| `--also-upper` | also scan the upper-cased text (runtime `.ToUpper()`, `<uppercase>`), which catches Turkish `İ` and German `ẞ` |

Ignored characters are controls, space, NBSP and ideographic space, zero-width and variation selectors, combining marks (NFC), rich-text tags and `{placeholders}`. JSON report `{tool, version, input, fonts[], lenient, unique_chars, summary{missing, severity}, missing[{codepoint, char, name, count, first_key}], exit_code}`.

```
python font_glyph_scanner.py --input final_ja-JP.json --dst-field ja-JP --font C:\Windows\Fonts\msgothic.ttc
python font_glyph_scanner.py --input final_de-DE.json --dst-field de-DE --font "Assets/Fonts/Bebas SDF.asset" --also-upper --strict
```

---

## make_blind_slice.py (target-only slice for the blind critic)

```
python make_blind_slice.py --input <table> --locale <loc> --out <path> [--key-col key] [--target-col <loc>] [--context-cols category,speaker]
```

| Flag | Meaning |
|---|---|
| `--input` (or positional) | JSON, CSV, TSV, PO or Unity `.asset` |
| `--locale` | recorded in the slice, also tried as the target column name of multi-locale tables |
| `--out` | `.json` (`{locale, source_file, blind: true, entries[{key, category?, speaker?, target}]}`) or `.csv` / `.tsv` |
| `--key-col`, `--target-col`, `--source-col` | column names (defaults `key`, auto, `en`) |
| `--context-cols` | context columns to keep (default `category,speaker`). The source column is refused, and a context value equal to the row's own source line or to any source sentence of more than three words aborts with exit 2. A short name another row holds is no leak, a speaker such as `Dorian Crowe` is also the English text of the line that names him |
| `--src-input`, `--shared-table`, `--delimiter` | Unity and CSV options |
| `--skip-empty` | drop empty targets |
| `--max-rows N` | batch size |

---

## validate_critique.py (critic output schema check)

```
python validate_critique.py --critique critique_<locale>_<batch>.json [--slice blind_<locale>_<batch>.json] [--locale <loc>]
```

`--critique` (or the positional) is the critic output file. The tool validates the fixed schema `{locale, source_file, entries[{key, score 1-5, issue_type, reason, suggested}], summary{total, flagged, critical}}`.
Only entries with a score below 5 are listed. `issue_type` is one of `translationese`, `register`, `tense`, `regional_leak`, `gender_leak`, `ui_verb`, `placeholder_grammar`, `terminology` or `other`, and `critical` counts the entries with a score of 2 or lower. With `--slice` every key must exist in the slice and `suggested` must keep placeholder and tag parity
with the slice target (an entry typed `placeholder_grammar` may deliberately repair tokens, the blind critic never sees the source). `--placeholder-style` and `--tag-style` work as for the linter. Pass 2 knows the source line and calls the same check with it, then placeholders and tags are compared with the source line, without the `placeholder_grammar` exception.

---

## orchestrator_stub.py (Phase 0 to 3 runner)

```
python orchestrator_stub.py --input <source table> --locale <loc> --workdir <dir> (--dry-run | --live | --provider module:function) [options]
```

Two flows share Phase 0 and Phase 3. One of `--dry-run`, `--live` or `--provider` is required, without any of them the run stops with exit 2.

Jury flow (`--dry-run` with the offline fake provider, `--live` with the real APIs and the keys from `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`).

| Phase | What happens | Files in `--workdir` |
|---|---|---|
| 0 | locale, rules, bible stub, optional font scan, trust level of the language pack, warm-up sample, translation memory | `<LOCALE>_BIBLE.md` |
| 1 | Pass 1 with the `pass1` model, warm-up in the system prompt, the closest approved TM lines per row (RAG) | `pass1_batch_NN.json` |
| 2 | blind slice, J1 to J3 jury with deliberation, Pass 2 with three candidates and a blind J1 pick, `validate_critique`, change report | `blind_<loc>_NN.json`, `verdicts_<loc>_NN.json`, `rewrites_<loc>_NN.json`, `final_batch_NN.json`, `changes_<loc>_NN.json`, `changes_<loc>_NN.md` |
| 3 | `lqa_linter`, `ui_expansion_checker`, optional `font_glyph_scanner` on the final batches | `lqa_<loc>_NN.json`, `budget.jsonl` |

A line whose placeholders or rich text tags differ from its source line goes to Pass 2 as `rewrite` whatever the jury said, with the difference as its first rationale and under `evidence.parity`, since the blind jury cannot see a lost token. In the Pass 2 pick such an old line never stays. Validated Pass 2 lines replace the Pass 1 text in `final_batch_NN.json`, unresolved lines keep the Pass 1 text until the developer decides. When the budget cap stops the jury, the batch report is written, Phase 3 is skipped and the run exits 1.

Legacy flow (`--provider module:function`). Any callable `complete(system: str, user: str) -> str` drives the 2.1 single critic flow (`critique_<loc>_NN.json`). Code callers keep `run_pipeline(..., DryRunProvider(locale))` for the old offline flow.

| Flag | Meaning |
|---|---|
| `--input` | source table, the `--src-field` column (default `en`) holds the English text |
| `--workdir` | scratch folder for every file above |
| `--dry-run` | jury flow with the fake provider, no key and no network |
| `--live` | jury flow with the real APIs |
| `--provider module:function` | legacy single critic flow |
| `--providers-config`, `--fake-scenario`, `--budget-log` | model access of the jury flow, the budget log defaults to `<workdir>/budget.jsonl` |
| `--langpack-dir` | root of the language packs, default the skill's `langpack/` |
| `--tm` | translation memory (`tm.py` SQLite) for Pass 1 RAG and the jury evidence |
| `--font` | font files for the glyph scan of the Phase 3 gate, repeatable. Without one the gate says so in its log and summary (`glyphs_checked` false, `PASSED (glyphs not checked)`), and `missing_glyphs` counts the distinct characters no font covers |
| `--no-resume` | ignore the finished model batches in `<workdir>/model_batches.json` and call every model again. By default every finished batch of Pass 1, the jury, the back-translations and Pass 2 is kept there, and the same command with the same `--workdir` resumes a stopped run at the batch where it stopped without paying for the finished ones again. A changed source line, prompt or model makes a new batch, an old answer is never reused for it |
| `--context-map` | `CONTEXT_MAP.md` of the game, the output of Phase 0 step 0 (also `context_map` in `l10n.config.json`). Pass 1 and Pass 2 read the map, the locale appendix and the full line notes, the jury and the blind pickers read the map and the neutral line fields only. Without it the run logs that every step works without the game's context |
| `--draft-field` | input column that already holds a translation, such as the game's machine translation. Pass 1 keeps it as it is and translates only the rows where it is empty, the jury judges the draft and Pass 2 corrects only the lines the jury flags, so the change reports show the real corrections and an unchanged good line stays as the game has it |
| `--no-deliberation` | leave J3 disagreements unresolved |
| `--no-budget-caps` | never stop at the J2 or J3 cap |
| `--candidates` | Pass 2 candidates per flagged line, default 3 |
| `--seed` | seed of warm-up, few-shots and candidate order, default 1234 |
| `--workers` | model calls in flight per step, default 4, 1 sends one call at a time. Pass 1, the jury members, the deliberation round and the Pass 2 pickers run in parallel and the files stay the same. Each batch of `--batch-size` lines runs as one unit, so a live run of a whole game wants a larger batch such as `--batch-size 200` |
| `--key-field`, `--placeholder-style`, `--tag-style`, `--batch-size`, `--font` | pipeline options |

JSON report. `{passed, flow (jury or legacy), summary (gate), log, finals, batches[{batch, verdicts, rewrites, final, report, unresolved, stats}], halted, unresolved, trust_level, notes, exit_code}`.

Exit codes. 0 the gate passed and no line is unresolved. 1 the gate failed, the budget cap stopped the run, a line is unresolved, or a legacy critique is invalid. 2 usage or input error.

---

## LLM providers (providers/ and providers.config.json)

The `providers/` package talks to Anthropic, Google Gemini and DeepSeek with `urllib` only, no SDK. Every adapter returns a `ChatResult(text, input_tokens, output_tokens, model, latency_ms)` through one interface, `complete(system, user, temperature, max_tokens, json_mode)`. The Anthropic adapter drops `temperature`, because current Claude models answer it with HTTP 400. Every call asks for the model's own output maximum, `max_output_tokens` per model in `providers.config.json` (Claude 5.5 128000 and DeepSeek 393216 as the APIs state them, Gemini 4 caps any value itself), whatever `max_tokens` the caller passes. Current Claude, Gemini and DeepSeek models think before they answer and the thinking counts against that limit, fixed floors of 16000 and 32000 cut replies in live runs. Only generated tokens are billed. A batched task re-asks up to three times in total, and a reply without content counts as a failed attempt instead of ending the run. Every socket read times out after 600 seconds. Every reply is streamed (Claude and DeepSeek `stream: true`, Gemini `streamGenerateContent?alt=sse`), so a reply that thinks for minutes keeps sending events and never reaches that timeout. Each adapter puts the events back together into one reply and retries a stream that sends an error or ends before its end mark. The Gemini key travels in the `x-goog-api-key` header. Prompt caching, checked live per provider. Anthropic caches only on request, so the adapter sends the system prompt as one block with `cache_control` and the following calls of a run read it at a tenth of the input price or less. DeepSeek caches prompt prefixes on its own. Gemini 4 showed no cache hits in live tests, and explicit caching is not offered for Gemini 4. `ChatResult` carries `cache_read_tokens` and `cache_write_tokens`, the budget log records them and `budget_report.py` prices them with `price_cache_read` and `price_cache_write` of `providers.config.json`. `as_legacy()` wraps a provider for the old `complete(system, user) -> str` interface of `orchestrator_stub.py`.

| Piece | Behaviour |
|---|---|
| Retry | HTTP 429, 5xx and network errors are retried with exponential backoff (1, 2, 4, 8 seconds, or the `Retry-After` header), at most 5 attempts |
| Rate limit | `rps` per provider from the config, shared by every model of that provider |
| Budget log | every call appends one JSON line to `budget.jsonl` with `role`, `provider`, `alias`, `model`, `input_tokens`, `output_tokens`, `latency_ms`, `ok` and `fallback_from` when a fallback answered |
| Fallback | a model the API does not know (`not found`) switches once to the `fallback` alias of its config entry and the switch is noted in the report. Without a fallback the run stops with exit 2 |
| Fake provider | `providers/fake.py` answers from a scenario file (prompt hash to reply, per line score rules) or from deterministic built-in rules. Every tool that calls a model takes `--dry-run` (fake provider, no key, no network) and `--fake-scenario FILE` |
| Offline guard | the environment variable `GCL_OFFLINE=1` refuses every network call (the test suite sets it) |

`providers.config.json` holds the provider endpoints, the name of the API key environment variable of each provider (`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`), the model ids with prices in USD per 1M tokens (`null` means the price is not entered yet), the roles (`pass1`, `pass2`, `roundtrip`, `literal`) and the three jury tiers `J1`, `J2`, `J3`. Every tier needs one member from each family, two members of one family in a tier is a config error (exit 2). `agreement`, `budget_caps` and `roundtrip` hold the jury thresholds. `providers.deepseek.thinking` maps a role (or `default`) to `true` or `false` to switch DeepSeek thinking mode, a missing role keeps the API default. API keys are never written to any file.

## providers_check.py (provider config, API keys, model ping)

```
python providers_check.py providers.config.json [--roles J1,J2,J3] [--ping] [--dry-run] [--fake-scenario FILE] [--budget-log FILE]
```

| Flag | Meaning |
|---|---|
| `--input` (or positional) | the providers config to check, normally `scripts/providers.config.json` |
| `--roles` | comma separated roles to check, default all (`pass1,pass2,roundtrip,literal,J1,J2,J3`) |
| `--ping` | send one tiny JSON request to every model of the roles, real API unless `--dry-run` |
| `--dry-run` | fake provider, needs no API key |
| `--fake-scenario` | scenario JSON for the fake provider (for example `{"errors": {"deepseek-v4-pro": "not_found"}}`) |
| `--budget-log` | append one JSON line per ping to this file |

Exit codes. 0 config, keys and pings are fine. 1 a model was not found and its fallback answered. 2 config error, a missing API key environment variable, an unknown role, or a model that failed without a fallback.

## build_context_map.py (context map facts, the first step of every run)

```
python build_context_map.py --scan --project "<unity project>" --out loc_work/context [--keys-from loc_work/reference/tr.csv] [--use-sites 12]
python build_context_map.py --scan --project "<unity project>" --out loc_work/context --slices slices.json --locale tr-TR [--keys-from loc_work/reference/tr.csv]
python build_context_map.py --check-slices --out loc_work/context
```

The context map is the mandatory first step (Phase 0 step 0). `context-cartographer` on Claude Opus and its `context-scout` agents on Claude Sonnet write `CONTEXT_MAP.md` and ask the user whatever stays unclear. This tool collects the facts they need, builds the input of every scout and checks that the scout reports cover every key. It reads the project only and never writes into it.

For a Unity project it reads the Unity Localization string tables (Shared Data assets) and every reference in prefabs, scenes and ScriptableObjects, by table GUID or table name and by key id or key name (`LocalizedString` fields and `LocalizeStringEvent` components). A scene or prefab that binds a key through a prefab override (`m_Modifications` of a `PrefabInstance`) counts too, its object reads `<prefab> (override)`. For every key it records the file, the object with its hierarchy path, the class and the field, and the code lines of that class that show the field. A code line is flagged `concat` when it glues the text to something else (`+`, string interpolation, `string.Format`), those lines belong in the transcreation ledger. Paths longer than the Windows limit are read with the long path prefix. Other engines exit 2 for now, the agents read their code directly.

The use trace follows every loaded text to the code that reads it. A key's code line often only loads the text into a variable (`X = X_LOC.GetLocalizedString();`, or a `StringChanged` handler that stores its value), and the line that shows it sits in another method or another file. The scan finds that variable, reads its declaration and looks for every read of it, the bare name in the declaring class and its partial parts, `ClassName.FIELD` in the whole code base for a static field (`WarningMessageController.NEED_BROKEN_ITEM` read in `SalvageMachine.cs`) and `.FIELD` in the files that name the class for a public one. A property or method that returns the text is followed the same way, and a line that uses the text in place counts as a use site of the field itself. Every use site records the method, the conditions around it as `trigger` (the enclosing `if (...)`, `else of if (...)`, `case X of switch (...)` or the branch of a `?:`, innermost first, at most three), the body of a one line bool helper the condition calls (`CanSalvage()` is `GetTotalItemCount() > 0`), the variable the text is handed on to, and the `shape` of the glued text with `{THIS}` standing for the key's own text (`$"{X}: {itemName}"` gives `{THIS}: {itemName}`, `X + "\n¢" + amount` gives `{THIS}` followed by a line break, `¢` and `{amount}`). A key whose loaded variable is never read anywhere is `loaded_not_shown`, the game never shows that text. Comments and string literals never count as a use. Sites in `Debug.Log` calls and Editor folders carry `debug` and come last. The trace is a heuristic, regex only and no compiler, so reflection, UnityEvents and texts passed on as `LocalizedString` objects stay invisible and such a key is never flagged. Read the code before you call a text unused. On the first project it took about five seconds for 2297 C# files and flagged seven keys, each one confirmed by hand.

| Flag | Meaning |
|---|---|
| `--scan` | scan the project |
| `--slices` | also write one scout input per slice to `<out>/slices/<slice>.input.json`, the value is a JSON file `{"slice": ["TableName", "Table*"]}` (implies `--scan`) |
| `--locale` | target locale whose existing texts go into the slice inputs, for example `tr-TR` |
| `--source-locale` | locale of the source texts in the slice inputs, default `en` |
| `--check-slices` | check `<out>/slices`, every key of `<slice>.input.json` must sit in exactly one entry of the scout's `<slice>.report.json` |
| `--check-leak` | check the jurors' view of `--context-map` against an existing translation (`--reference`, column `--locale`). It lists every word of that translation its English source never uses and every source line of 25 characters or more quoted verbatim. Exit 1 on any. Run it before every calibration against that translation |
| `--context-map` / `--reference` | the map and the existing translation (key, en and the `--locale` column) of `--check-leak` |
| `--project` | the game project folder (a Unity project or its Assets folder) |
| `--out` | output folder, for example `loc_work/context`, refused inside the game project |
| `--keys-from` | a string table whose keys must be covered, for example the studio reference, the report lists keys without a usage. Its `category` and `speaker` columns go into the slice inputs |
| `--code-lines` | code lines kept per localized field, default 4 |
| `--use-sites` | use sites kept per key by the use trace, default 12, player facing sites first. `uses_total` still counts them all. 0 turns the trace off |

Output files. `key_usage.json` (`engine`, `project`, `tables`, `keys` with `table`, `name` for a key name that two tables share (the key itself is then `Table:Key`), `usages` of `{file, object, class, field}` and `code` of `{file, line, text, concat}`, `unresolved_references` for references to a key its table no longer has, `missing_table_references` for references to a table the project no longer has) and `scan_summary.md` (coverage, tables, main classes per table, stale references, keys without a usage, keys loaded but never shown). Paths are relative to the project.

The use trace adds `use_trace` to `key_usage.json` (`heuristic` true, a `note` saying so, `code_files`, `use_sites_per_key`, `keys_with_uses`, `loaded_not_shown`) and four fields to every key.

| Field | Meaning |
|---|---|
| `loads` | where the text is loaded, `{file, line, variable, via, scope}` plus `shape` when the load itself glues text on and `trigger` when it is one branch of a `?:`. `via` is `GetLocalizedString`, `StringChanged` or `return`, `scope` is `static`, `field`, `local`, `member` (a property or method that returns the text) or `unknown` (no declaration found) |
| `uses` | the use sites, `{file, line, text, variable, method, trigger, concat}` plus `shape`, `helpers`, `assigned_to` and `debug` when they apply |
| `uses_total` | every use site found, also those beyond `--use-sites` |
| `loaded_not_shown` | true when every binding of the key loads its text into a variable that nothing reads |

The jurors' view. Next to `CONTEXT_MAP.md` (the user's language) and `line_notes.json` the map folder may hold `CONTEXT_MAP.jury.md` and `line_notes.jury.json`, the same map and notes in English. Every tool that gives jurors the map (`eval_critic.py`, `jury.py`, `deliberate.py`, the blind pickers of `pass2_rewrite.py`, the orchestrator) uses them instead when they exist, writers keep the user's map. Scouts who read an existing translation write its words into a map in the target language, and a calibration against that translation then partly matches words instead of judging. On the first project the Turkish notes shared words with the studio line on 115 of 400 pairs and with the literal line on 18.

Slice inputs. A list of rows `{key, table, <source locale>, <target locale>, category, speaker, usages, code, loads, uses, uses_total, loaded_not_shown}`. The texts come from the project's own locale tables (`<Collection>_<locale>.asset` next to the Shared Data asset, matched by its GUID), so line and paragraph breaks stay intact. Never build scout inputs by hand from an export, the first project lost every paragraph break that way. Every table lands in exactly one slice. A table claimed by two slices or a slice that claims no table is an input error, tables no slice claims go to `unassigned.input.json`. The scout writes `<slice>.report.json` next to its input, a list of entries with `keys` (a list) and the fields of `agents/context-scout.md`.

Exit codes. 0 written, or every key covered. 1 findings, keys of `--keys-from` without a usage, tables no slice claims, a locale table that was not found, or keys a scout report misses, repeats or invents. 2 usage or input error (not a Unity project, no string table, `--out` inside the project, a bad slice file, no slice inputs to check).

## build_language_pack.py (language asset pack with a five-layer filter)

```
python build_language_pack.py ../langpack/sources.manifest.json --locale tr-TR [--reference loc_work/reference/tr.csv] [--offline] [--mt-check] [--jury-screen]
```

Builds `langpack/<locale>/` from the corpora listed in `langpack/sources.manifest.json` plus the studio's own professional translation. Every source carries a license class. `bundle` (CC0, CC-BY, MIT, the studio's own lines) may ship with the plugin and is credited in `LICENSES.md`. `local` (GPL, LGPL, MPL, translation memories) is used on this machine only and is written under `langpack/<locale>/local/`, which is gitignored. OpenSubtitles is not a source and a manifest that lists it is rejected (exit 2).

| Flag | Meaning |
|---|---|
| `--input` (or positional) | the sources manifest |
| `--locale` | pack locale |
| `--langpack-dir` | root of the packs, default the skill's `langpack/` |
| `--cache-dir` | download cache and offline source, default `<langpack-dir>/.cache` (gitignored). Files are mirrored as `<cache>/<source id>/<host>/<url path>` |
| `--offline` | never download, read every corpus file from the cache |
| `--refresh` | download again even when a cached copy exists |
| `--lock-hashes` | write the sha256 of every file into the manifest where it is still `null` |
| `--reference` | the studio's EN and target table (`key`, `en`, `<locale>`, `category`, `speaker`), repeatable. Exempt from the length ratio and the ban list of layer 2 and from layers 3 to 5 |
| `--reference-license` / `--reference-attribution` | license and credit line of the studio's lines in `manifest.json` and `LICENSES.md`, default `proprietary (studio owned)` and none. The `tr-TR` pack ships the Rysesoft lines under MIT |
| `--src-field` / `--dst-field` | columns of `--reference` (defaults `en` and the locale code, then `dst`, `target`) |
| `--mt-check` | run the back-translation check of layer 3 with the `roundtrip` model |
| `--jury-screen` | run the J1 pre-screen of layer 5 with the three J1 models |
| `--min-words` | back-translation applies to lines with more words than this, default `roundtrip.min_words` of the providers config (6) |
| `--seed` / `--sample-size` | seed and size of the pre-screen sample (defaults 1234 and 50) |
| `--providers-config`, `--dry-run`, `--fake-scenario`, `--budget-log` | model access as for every model calling tool, the budget log defaults to `<cache-dir>/budget_<locale>.jsonl` |

Manifest source fields. `id`, `name`, `homepage`, `license`, `license_class`, `attribution`, `register` (`ui`, `game` or `dialogue`), `review_process`, `version`, `format` (`po`, `properties`, `json_nested`, `openttd`, `ftl`, `table`) and `files`, a list of `{locale, url or path, sha256}`. Paired formats (`properties`, `json_nested`, `openttd`, `ftl`) also name the English file in `en_url` or `en_path`.

The five layers, with counts in `manifest.json` under `filters`.

| Layer | Drops |
|---|---|
| 1 source selection | license class not `bundle` or `local`, no license, no review process, version not pinned, sha256 mismatch, file not cached or not downloadable |
| 2 mechanical | empty, fuzzy, untranslated, length ratio outside 0.3 to 3.0, ban list hit (`rules/<locale>.json`), broken placeholders or tags, duplicate inside one source |
| 3 MT detection | more than 500 rows from one commit (`commit` column), and with `--mt-check` lines over `min_words` words whose back-translation equals the English source |
| 4 cross consistency | short terms (up to 4 words) rendered the same by 3 or more sources are `trusted`, conflicting renderings are `disputed` and dropped unless they agree with the reference |
| 5 jury pre-screen | with `--jury-screen` a line stays only when all three J1 members give 4 or 5, a seeded sample goes to `prescreen_sample.jsonl` |

The professional reference wins over the heuristics of layer 2. Its lines stay even when they are far longer or shorter than the English or hit a ban list rule. `filters.layer2_mechanical.reference_exempt` in `manifest.json` lists these lines (`length_ratio`, `rule_hits` with key and rule, `by_rule`), and the report prints the counts. A rule that keeps hitting the reference fights the studio voice and is worth narrowing with `context` or `skip_contexts`.

Output files. `manifest.json` (sources, versions, hashes, filter statistics, `langpack_version`), `trust_card.json` (trust level, sources, row counts, known limits, calibration slot), `warmup.jsonl` (bundle class lines `{text, register, source, license_class, key, consistency}`), `local/warmup.jsonl` (local class lines), `roundtrip_threshold.json` (default 0.85 until calibrated), `LICENSES.md`. Registers are `ui`, `tutorial`, `dialogue_casual` and `dialogue_formal`, taken from the row category or guessed from the text shape.

Exit codes. 0 pack built. 1 pack built but a source could not be loaded or no row survived. 2 usage or input error.

## warmup_loader.py (seeded warm-up sample)

```
python warmup_loader.py ../langpack/tr-TR --register dialogue_casual [--register ui] [--count 40] [--seed 1234] [--out warm.txt]
```

Picks native lines of the requested registers from `warmup.jsonl` and `local/warmup.jsonl` of a pack so a model hears the target language before it translates or judges (recommended 30 to 50 lines per session). The same pack, registers, count and seed always return the same lines. Lines are balanced across sources (the studio reference first, `trusted` lines first inside a source), rich-text tags and engine colour codes such as `{BLACK}` or `[accent]` are removed, lines shorter than 2 or longer than 300 characters are skipped.

| Flag | Meaning |
|---|---|
| `--input` (or positional) | pack folder, for example `langpack/tr-TR` |
| `--register` | `ui`, `tutorial`, `dialogue_casual` or `dialogue_formal`, repeatable, default all |
| `--count` | lines to pick, default 40 |
| `--seed` | sampling seed, default 1234 |
| `--no-local` | ignore `local/warmup.jsonl` |
| `--format` | file format of `--out`, `text` (the prompt block, grouped by register) or `jsonl` |
| `--out` | write the sample to this file |

Exit codes. 0 the sample has the requested size. 1 the pack has fewer matching lines (the smaller sample is still written). 2 usage or input error (no pack, unknown register).

## build_contrastive_set.py (native, robot and unknown lines)

```
python build_contrastive_set.py loc_work/reference/tr.csv --locale tr-TR [--out ../langpack/tr-TR/contrastive.json] [--limit 300] [--dry-run]
```

Reads the studio's professional reference table (`key`, `en`, the target column, optional `category`, `speaker`, `archetype`) and writes the contrastive set of a pack. `native` is the professional line. `robot` is a deliberately literal translation by the `literal` model with `prompts/literal.md`. `unknown` holds raw translations by strong models (default the `pass1` model), unlabeled and used for observation only. Pairs whose robot line equals the native line, or breaks a placeholder of the English source, carry no contrast and are dropped.

| Flag | Meaning |
|---|---|
| `--input` (or positional) | reference table (CSV, TSV, JSON or PO) |
| `--locale` | target locale |
| `--out` | output JSON, default `langpack/<locale>/contrastive.json` |
| `--src-field` / `--dst-field` / `--key-field` | columns, defaults `en`, the locale code (then `dst`, `target`) and `key` |
| `--unknown-models` | comma separated model aliases for the unknown lines, default the `pass1` model |
| `--no-unknown` | skip the unknown lines |
| `--limit` / `--seed` | seeded subset of N rows (default all rows, seed 1234) |
| `--batch-size` | rows per model call, default 30 |
| `--min-pairs` | exit 1 when fewer usable pairs result, default 30 |
| `--providers-config`, `--dry-run`, `--fake-scenario`, `--budget-log` | model access, the budget log defaults to `budget.jsonl` next to `--out` (or `langpack/.cache/` inside the bundled langpack folder) |

Output (`contrastive.json`). `{locale, source_ref, seed, limit, generated_with, pairs[{key, en, native, robot, unknown{model id: text}, register, speaker, archetype}]}`.

Exit codes. 0 set written. 1 set written with fewer usable pairs than `--min-pairs`. 2 usage or input error, including a missing API key.

## roundtrip_check.py (back-translation calque check)

```
python roundtrip_check.py pass1_tr-TR_01.json --locale tr-TR [--dst-field dst] [--threshold 0.85] [--dry-run]
python roundtrip_check.py ../langpack/tr-TR/contrastive.json --locale tr-TR --calibrate [--dry-run]
```

The `roundtrip` model translates a target line back into English as literally as it can. The calque score (0 to 1, mean of word sequence and character similarity) says how closely the back translation follows the English source. Native writing drifts away from the English, a calque comes back almost verbatim. The test carries information only for longer dialogue, so it applies only to rows whose register is in `roundtrip.registers` of the providers config (`dialogue_casual`, `dialogue_formal`) and whose target has more than `roundtrip.min_words` words (6). Every other row is reported with `"applied": false` and costs no call.

| Flag | Meaning |
|---|---|
| `--input` (or positional) | translated table (`key`, `en`, target, `category` or `register`), or a `contrastive.json` with `--calibrate` |
| `--locale` | target locale |
| `--calibrate` | score the native and robot lines of the contrastive set and write the threshold with the best balanced accuracy |
| `--src-field` / `--dst-field` / `--key-field` | columns, defaults `en`, then `dst`, the locale code or `target`, and `key` |
| `--threshold` | calque threshold, default the pack's `roundtrip_threshold.json`, else 0.85 |
| `--min-words` | override `roundtrip.min_words` |
| `--langpack-dir` | root of the packs, default the skill's `langpack/` |
| `--out` | calibration output, default `langpack/<locale>/roundtrip_threshold.json` |
| `--batch-size` | lines per model call, default 30 |
| `--providers-config`, `--dry-run`, `--fake-scenario`, `--budget-log` | model access |

Check report. `rows[{key, applied, calque_score, back, suspect}]` (`reason` `register` or `short` when not applied) and `summary{rows, applied, suspects}`. Calibration file. `{locale, threshold, calibrated, weak, balanced_accuracy, n_native, n_robot, native_mean, robot_mean, min_words, registers, source}`.

Exit codes. Check mode 0 no suspect, 1 at least one line at or above the threshold. Calibrate mode 0 written, 1 written but weak (fewer than 5 lines per class or balanced accuracy below 0.75). 2 usage or input error.

## eval_critic.py (jury calibration on the contrastive set)

```
python eval_critic.py ../langpack/tr-TR/contrastive.json --locale tr-TR [--tiers J1,J2,J3] [--compare-warmup] [--update-trust-card] [--dry-run]
```

Measures every jury member against the contrastive set. Each model is called once, even when it sits in two tiers.

| Measure | How | Target |
|---|---|---|
| Pairwise accuracy (primary) | the member sees native and robot lines of one pair blind, side order seeded at random, and picks the more natural one | 0.85 or more for every member (phase A gate) |
| Absolute means (secondary) | 1 to 5 scores for native, robot and unknown lines in seeded order | native above 4.5, robot below 3 |
| Unknown distribution (observation) | score histogram of the raw strong-model lines | none |
| Kappa | quadratic weighted Cohen's kappa between members of different families in one tier (`inter_family_kappa`) and between models of one family across tiers (`intra_family_kappa`) | none |

The system prompt is `prompts/critic.<locale>.md` with a seeded warm-up sample from the pack and `--shots` contrastive pairs as few-shots. The few-shot pairs are held out of the evaluation.

| Flag | Meaning |
|---|---|
| `--input` (or positional) | `contrastive.json` |
| `--locale` | target locale |
| `--tiers` | comma separated tiers, default `J1,J2,J3` |
| `--langpack-dir` | root of the packs for the warm-up sample and `trust_card.json` |
| `--no-warmup` | evaluate without the warm-up block |
| `--compare-warmup` | run with and without warm-up in one command and report `delta_pairwise` |
| `--warmup-count` | warm-up lines, default 40 |
| `--shots` | held out few-shot pairs, default 6 |
| `--limit` / `--seed` | seeded subset of the remaining pairs, seed for side order, subsets and warm-up (default 1234) |
| `--pairwise-min` | gate, default 0.85 |
| `--workers` | batches in flight per model, default 4. Above 1 every distinct model is calibrated in its own thread. The report is the same for every value, only the wall clock changes. A live full run with 8 models drops from hours to minutes |
| `--keep-mixed-robots` | keep pairs whose literal line left three or more English words of its source untranslated. By default they are left out and counted (`dropped_mixed_robots`), any reader spots such a line and it measures no native ear. The report gives every member's accuracy on short labels (three English words or fewer, `pairwise_short`) and on longer lines (`pairwise_long`) apart, short labels often read the same either way |
| `--cache` | JSON file that keeps the answers of every finished model under a signature of model, tier, prompt and items. When one model fails the others are kept and the run stops with a hint, the same command then only calls the missing models. Every finished batch is also kept in `<cache stem>.batches.json` next to it, so a model stopped halfway by a rate limit or a provider queue resumes at the batch where it stopped. Keep both out of the shipped pack, for example in `loc_work/` |
| `--context-map` | `CONTEXT_MAP.md` of the game. The map joins the critic prompt and every pair and entry gets the neutral fields of its line note from `line_notes.json` next to the map (screen, element, player action, inserted text, room, speaker, listener, register). The locale appendix `CONTEXT_MAP.<locale>.md` is never read here, it holds the studio's own choices and would hand the jurors the answer key. The report and the trust card name the map and count the pairs with line context |
| `--update-trust-card` | store the result under `calibration` in `langpack/<locale>/trust_card.json` |
| `--providers-config`, `--dry-run`, `--fake-scenario`, `--budget-log` | model access |

Report (B3.6). `{locale, langpack_version, warmup, members[{tier, family, model, pairwise_accuracy, native_mean, robot_mean, unknown_mean, n}], inter_family_kappa, intra_family_kappa, gate{pairwise_min, passed}, secondary}`. With `--compare-warmup` the report holds `with_warmup`, `without_warmup` and `delta_pairwise`, and the gate is the one with warm-up.

Exit codes. 0 every member reached the gate. 1 at least one member is below it. 2 usage or input error.

## budget_report.py (tokens, calls, latency, cost and projection)

```
python budget_report.py loc_work/budget.jsonl [--rows 400] [--project-rows 20000] [--project-locales 15] [--max-cost 500]
```

Aggregates the `budget.jsonl` lines of every model call by role, by provider, by model and by role and model. Cost uses `price_in` and `price_out` (USD per 1M tokens) of `providers.config.json`. A model with a `null` price is shown as `price not set (fiyat girilmedi)` and its cost is left out of every total, so a total that contains such a model is a lower bound. Calls made with `--dry-run` are counted and flagged, their tokens are estimates.

| Flag | Meaning |
|---|---|
| `--input` (or positional) | a `budget.jsonl` file, or a folder whose `budget*.jsonl` files are all read |
| `--providers-config` | config with the prices, default the bundled one |
| `--rows` | source lines the logged run processed, enables the projection |
| `--project-rows` / `--project-locales` | projection size, default 20000 lines and 15 locales |
| `--max-cost` | exit 1 when the projected cost (or the actual cost without `--rows`) in USD is above this |

JSON report. `{files, records, dry_run_records, totals, by_role, by_provider, by_model, by_role_model, projection{calls_per_row, cost_per_row_usd, calls, input_tokens, output_tokens, cost_usd, complete, note}, missing_prices, fallbacks}`. Every group has `calls`, `errors`, `input_tokens`, `output_tokens`, `latency_ms`, `mean_latency_ms`, `cost_usd` and `priced`.

Exit codes. 0 report written. 1 cost above `--max-cost`. 2 usage or input error (no log, broken line).

## jury.py (tiered mixed-family jury)

```
python jury.py blind_tr-TR_01.json --locale tr-TR [--source-table pass1_tr-TR_01.json] [--out verdicts_tr-TR_01.json] [--dry-run]
```

Three tiers of three members, one from each family (`J1` Haiku, V4 Flash, Hydrogen, `J2` Sonnet, V4 Pro, Neon, `J3` Opus, V4 Pro, Carbon by default). The members read only the blind slice (key, `register`, `category`, `speaker`, `archetype`, target). A slice that carries a source column (`en`, `source`, `src`) is refused with exit 2. The system prompt is `prompts/critic.<locale>.md` with the pack's seeded warm-up and contrastive few-shots.

Every juror first asks of every word of a line whether it belongs to everyday use of the language, a rare, bookish, archaic, word for word or dictionary choice is not everyday even when it is correct (proper names, placeholders, tags and the game's own terms in the map are not judged this way). The juror lists such words in `odd_words`. The answer weighs heavily. When two of the three jurors of a tier find such a word in the same line, the code caps every score of that tier at 3 (`llm_tasks.everyday_rule`), so the line never passes and an agreeing J3 sends it to Pass 2, and every reason names the words. One juror alone caps nothing, its words stay in its vote as evidence. Measured on 385 tr-TR pairs with J1, a single flag would have sent 29 percent of the studio's own lines up a tier (16 percent without the check) for 2 more points of the literal lines, two flags send 17 percent. Only words the line really holds count, so a made up word never lowers a score. The deliberation round keeps the rule, and Pass 2 gets the words of the settling votes as `odd_words` and replaces them.

| Outcome of one tier | Rule | Next |
|---|---|---|
| pass | every score 4 or 5 and a spread of at most 1 | settled, line score is the minimum, 5 gives `pass`, 4 gives `rewrite_light` |
| escalate | any score 3 or lower, or a spread of 2 or more | next tier |
| critical | any score 2 or lower | straight to J3 from any tier |
| J3 agreement | spread of at most 1 | settled with the minimum, 3 gives `rewrite`, 2 or 1 give `critical` |
| J3 disagreement | spread of 2 or more | deliberation round (`deliberate.py`), without it `unresolved` with three rationales |

Budget caps from `budget_caps` of the providers config. When more than 30 % of the lines judged so far in the run would go to J2, or more than 10 % to J3, the run stops before calling that tier, writes the report with the settled lines, lists the rest under `pending` and names the lines of the batch that tripped the cap (`halted.keys`). The problem is then in Pass 1 or the prompt. The caps read the whole run (`orchestrator_stub.py` carries the count across batches, a single slice counts alone) and stop only with at least `min_judged` (100) judged lines and `min_escalated` (10) lines over the cap, and only when the batch sends lines to that tier. The verdict stats carry both the batch ratio (`to_J3_ratio`) and the run ratio (`run_to_J3_ratio`).

Evidence per line. `ban_hits` (locale rules of `rules/<locale>.json` on the target), `tm_neighbors` (when a translation memory is attached) and, for lines that reach J3, `roundtrip` (back-translation calque score, needs `--source-table`, which only the harness reads).

| Flag | Meaning |
|---|---|
| `--input` (or positional) | blind slice from `make_blind_slice.py` |
| `--locale` | target locale |
| `--out` | verdict file, default `verdicts_<locale>_<batch>.json` next to the slice |
| `--source-table` | harness side table with the English source, enables the back-translation evidence |
| `--src-field` / `--dst-field` / `--key-field` | columns of `--source-table` (defaults `en`, `dst` or `target`, `key`) |
| `--langpack-dir` | root of the packs for warm-up and few-shots |
| `--no-warmup` / `--warmup-count` | leave out the warm-up, or set its size (default 40) |
| `--shots` | contrastive few-shot pairs, default 6 |
| `--seed` | seed of the warm-up and few-shot sample, default 1234 |
| `--batch-size` | lines per model call, default 40 |
| `--no-budget-caps` | never stop at the J2 or J3 cap |
| `--no-deliberation` | leave J3 disagreements `unresolved` instead of running the deliberation round |
| `--tm` | translation memory (`tm.py` SQLite file) for the `tm_neighbors` evidence, queried by the English source when `--source-table` is given, else by the target |
| `--workers` | batches in flight per member, default 4. The three members of a tier, the back-translations and the disputed J3 lines of the deliberation round run in parallel, the verdicts are the same as with 1 |
| `--context-map` | `CONTEXT_MAP.md` of the game. The map joins the critic prompt (and the deliberation round), every entry without a `context` gets the neutral fields of its line note from `line_notes.json` next to the map. Jurors never read the locale appendix. The verdict file records the map under `prompt` |
| `--cache` | JSON file that keeps every finished batch of votes and back-translations, the same command resumes a stopped run where it ended |
| `--providers-config`, `--dry-run`, `--fake-scenario`, `--budget-log` | model access |

Vote (B3.3). `{key, tier, member, family, model, score, issue_type, reason, suggested}`. Verdict (B3.4). `{key, final_tier (J1, J2, J3 or deliberation), score, status (pass, rewrite_light, rewrite, critical, unresolved), votes, evidence{ban_hits, tm_neighbors, roundtrip}, rationales}`. The verdict file holds `locale`, `source_file`, `langpack_version`, `prompt`, `stats` (lines per tier, escalation ratios, status counts), `halted`, `verdicts`, `pending` and `notes`.

Exit codes. 0 every line settled. 1 the budget cap stopped the run or a line is unresolved. 2 usage or input error, including a source column in the slice, two members of one family in a tier and a missing API key.

## deliberate.py (J3 deliberation round)

```
python deliberate.py verdicts_tr-TR_01.json --slice blind_tr-TR_01.json --locale tr-TR [--out FILE] [--dry-run]
```

For lines the J3 tier disagrees on (spread of 2 or more). `jury.py` runs it automatically unless `--no-deliberation` is given, the CLI deliberates the J3 lines still marked `unresolved` in a verdict file.

1. The three J3 members have voted.
2. Each member sees the other two scores, issue types, reasons and suggestions as juror A and juror B. Model and family names are never shown and are scrubbed from the reason text. The evidence package holds the ban list hits, the three closest approved translation memory lines (target text only) and the back-translation signal (`applied`, `calque_score`, `suspect`). No source text reaches the jurors.
3. Each member votes once more.
4. Two equal scores decide (`final_tier` `deliberation`, status from the score). Three different scores leave the line `unresolved`, it reaches the developer with the three rationales. A juror who still scores the line critical (at or below `critical_max`) next to a majority above it is not overruled either, the line goes to the developer (`critical_holdout`). One critical vote sends a line from J1 straight to J3, so the last tier is never laxer than the first.

| Flag | Meaning |
|---|---|
| `--input` (or positional) | verdict file written by `jury.py` |
| `--slice` | the blind slice the jury read |
| `--locale` | target locale |
| `--out` | write the updated verdicts here, default update the input file |
| `--langpack-dir` / `--no-warmup` / `--seed` | critic prompt warm-up as for `jury.py` |
| `--context-map` | `CONTEXT_MAP.md` of the game, as for `jury.py`. The jurors re-vote with the map and the neutral line notes, never the locale appendix. Without it a deliberation run on its own, for example to finish a stopped jury run by hand, saw no map |
| `--providers-config`, `--dry-run`, `--fake-scenario`, `--budget-log` | model access |

Every deliberated verdict gets three extra votes with `tier` `deliberation` and a `deliberation` block `{first, revote, majority}`.

Exit codes. 0 no line left unresolved. 1 at least one line stays unresolved. 2 usage or input error.

## tm.py (SQLite translation memory and retrieval)

```
python tm.py loc_work/reference/tr.csv --db loc_work/tm.sqlite --locale tr-TR --mode add --status approved
python tm.py pass1_tr-TR_01.json --db loc_work/tm.sqlite --locale tr-TR --mode query [--top 5]
python tm.py changes_tr-TR_01.json --db loc_work/tm.sqlite --locale tr-TR --mode approve
python tm.py --db loc_work/tm.sqlite --mode stats
```

One row per locale, key and source text, with `status` `approved` (studio reference, lines the developer accepted) or `candidate` (machine output). A candidate never replaces an approved row. Neighbours are found with character trigram similarity (Dice coefficient on case-folded text), standard library only. The closest rows come in three tiers, same `category` and `speaker` first, then same `category`, then any row, each tier ordered by similarity. Only approved rows count unless `--include-candidates` is given, the queried key itself is left out and the default floor is 0.3. `--mode approve` is the flow back. Every accepted change is stored as approved with its new text, a rejected change stores the kept old text as approved, lines without a decision are counted and left alone. `*.sqlite` files are gitignored.

| Flag | Meaning |
|---|---|
| `--input` (or positional) | table to add or query, or a change report (`report_changes.py`, or a list of `{key, en, old, new, decision}`) to approve. Not needed with `--mode stats` |
| `--db` | SQLite file, created when missing |
| `--locale` | target locale, required except with `--mode stats` |
| `--mode` | `add`, `query` (default), `approve` or `stats` |
| `--status` | status of added rows, `candidate` (default) or `approved` |
| `--origin` | free text origin label of added rows, default the input file name |
| `--src-field` / `--dst-field` / `--key-field` | columns, defaults `en`, the locale code (then `dst`, `target`) and `key` |
| `--top` | neighbours per row, default 5 |
| `--min-similarity` | lowest similarity, default 0.3 |
| `--include-candidates` | query candidate rows too |

Query report. `results[{key, en, neighbors[{key, src, dst, category, speaker, status, similarity, match}]}]` where `match` is `category+speaker`, `category` or `any`.

Exit codes. 0 done. 1 findings (rows skipped by `add`, rows without any neighbour in `query`, lines still without a decision in `approve`). 2 usage or input error.

## pass2_rewrite.py (Pass 2 with three candidates and a blind J1 pick)

```
python pass2_rewrite.py verdicts_tr-TR_01.json --source-table pass1_tr-TR_01.json --locale tr-TR [--critique-out critique_tr-TR_01.json] [--dry-run]
```

For every verdict with status `rewrite_light`, `rewrite`, `critical` or `unresolved` (the last one as a proposal for the developer).

1. The `pass2` model (default Opus) writes three different candidates with `prompts/pass2.<locale>.md` (a native prompt for each of the 15 locales, `pass2.generic.md` only as a fallback). It sees the English source, the current line, the context, the jury rationales and suggestions and the closest approved translation memory lines.
2. The three J1 members see the candidates and the current line among them (seeded order, ids `c1` to `c4`) and the context, never the source, and each picks the most natural one. Most picks wins, a tie goes to the earlier candidate. When the current line wins it stays (`kept_by_pick`), a line the jurors still prefer is not rewritten for nothing.
3. A new winner goes through `validate_critique` (fixed critique schema, placeholder and tag parity with the English source line, also when the jury named a `placeholder_grammar` problem, not identical to the current line). When it fails, the next candidate by votes is tried. When none passes, the old line stays and the line is reported.
4. A new winner is scored once more by the three J1 members (`recheck`). Unless they pass it by the jury's agreement rule, the old line stays and the line is reported to the developer, a rewrite nobody confirmed never replaces a line.

| Flag | Meaning |
|---|---|
| `--input` (or positional) | verdict file written by `jury.py` |
| `--source-table` | Pass 1 table with key, English source and current target |
| `--locale` | target locale |
| `--out` | rewrite file, default `rewrites_<locale>_<batch>.json` next to the verdicts |
| `--critique-out` | also write the selected lines as a critique file in the fixed schema (`summary.total` is the number of judged lines, so it validates against the blind slice) |
| `--src-field` / `--dst-field` / `--key-field` | columns of `--source-table` |
| `--candidates` | candidates per line, default 3 (1 to 6) |
| `--workers` | batches in flight per model, default 4. The three J1 pickers run in parallel, the result is the same as with 1 |
| `--cache` | JSON file that keeps every finished batch of candidates and blind picks, the same command resumes a stopped run where it ended |
| `--context-map` | `CONTEXT_MAP.md` of the game. The Pass 2 writer reads the map, the locale appendix `CONTEXT_MAP.<locale>.md` and the full line notes (scout notes included), the blind J1 pickers read the map and the neutral line fields only |
| `--statuses` | verdict statuses to rewrite, default `rewrite_light,rewrite,critical,unresolved` |
| `--placeholder-style` / `--tag-style` | token syntax for the parity check |
| `--langpack-dir` / `--no-warmup` / `--seed` | warm-up and few-shots of the prompts, seed of the candidate order |
| `--providers-config`, `--dry-run`, `--fake-scenario`, `--budget-log` | model access |

Rewrite file. `{locale, source_file, verdicts, lines[{key, en, old, new, status, final_tier, score, candidates, picks, votes_per_candidate, chosen, valid, problems, selected_by}], critique, notes}`.

Exit codes. 0 every rewritten line has a validated new text. 1 at least one line kept its old text because no candidate passed. 2 usage or input error.

## report_changes.py (developer change report)

```
python report_changes.py verdicts_tr-TR_01.json --locale tr-TR [--rewrites rewrites_tr-TR_01.json] [--source-table pass1_tr-TR_01.json] [--budget-log loc_work/]
```

Writes `changes_<locale>_<batch>.json` and `changes_<locale>_<batch>.md` (B3.8). The header holds the trust level, the language pack version and the budget summary of the batch. Every flagged line carries `key`, `en`, `old`, `new`, `status`, `reason`, `evidence`, `confidence` (0 to 1), the votes per tier and an empty `decision`. The developer sets `decision` to `accept` or `reject` and stores the result with `tm.py --mode approve`. Unresolved lines get their own section with the three rationales of the last round. Lines are sorted critical, unresolved, rewrite, rewrite light, then by confidence. Pass lines are counted but not listed.

| Trust level (A9) | When |
|---|---|
| `measured` | the pack has a professional reference and a passing `eval_critic.py` calibration in `trust_card.json` |
| `estimated` | a language pack is installed, judgement rests on proxy signals |
| `rule_based` | no language pack, only the rule based gates speak for the line |

The level follows the pairwise gate of the calibration. When its second check failed (native mean above 4.5, literal mean below 3), the header of a measured report says so and `secondary_passed` is `false`. The jurors then rank a native line above a literal one, but a single score is no grade.

Confidence is the tier base (J1 0.90, J2 0.80, J3 0.70, deliberation 0.60, unresolved 0.30), minus 0.10 per point of spread among the settling votes, plus 0.05 for a ban list hit and 0.05 for a back-translation calque flag, halved when no Pass 2 candidate passed validation, clamped to 0 and 1.

The Markdown follows the house punctuation style. Model text is rewritten to that style, game text stays verbatim in code spans (pipes escaped), and the tool refuses to write a report that breaks the style.

| Flag | Meaning |
|---|---|
| `--input` (or positional) | verdict file of `jury.py` (deliberated or not) |
| `--locale` | target locale |
| `--rewrites` | rewrite file of `pass2_rewrite.py`, gives `new` |
| `--source-table` | Pass 1 table for `en`, `old`, `category` and `speaker` of lines without a rewrite |
| `--budget-log` | `budget.jsonl` file or folder for the budget summary |
| `--providers-config` | config with the prices |
| `--langpack-dir` | root of the packs, for the trust level and version |
| `--batch` | batch id of the file names, default taken from `verdicts_<locale>_<batch>.json` |
| `--out-dir` | output folder, default next to the verdicts |

Exit codes. 0 report written. 1 report written and some lines are unresolved or kept their old text. 2 usage or input error.

## export_translations.py (decisions applied, texts written in the game's format)

```
python export_translations.py <workdir or final_batch_NN.json> --locale tr-TR (--template FILE ... | --template-dir DIR) --out loc_work/export [--changes changes_tr-TR_01.json ...]
```

The last step of the jury flow. It merges the final batches, applies the decisions of the change reports of `report_changes.py` (`accept` keeps the new line, `reject` puts the old line back, a changed line without a decision keeps its final text and is listed) and writes the texts into the format of the game's own tables. A folder as INPUT means every `final_batch_*.json` in it and, without `--changes`, every `changes_<locale>_*.json` in it.

| Template | What changes |
|---|---|
| `.asset` | Unity StringTable of the target locale. Only `m_Localized` of the known keys, every other line stays as it was and an unchanged text keeps its original line. Key names come from the collection's Shared Data asset, found next to the table by its `m_SharedData` guid. A key the table has no entry for gets a new entry. SmartFormat and rich text pass through as text. The written file is read back and compared before it is kept, every written line also by a strict YAML reader, since the plugin's own reader takes a broken line too |
| `.csv`, `.tsv` | the target column (`--dst-field`, default the locale code) of the known keys, other columns, the delimiter, the line ends and a BOM stay |
| `.json` | the target field of a list of objects, or the value of a `{key: text}` map |
| `.po` | `msgstr`, or `msgstr[n]` for the plural keys `msgid\|[n]`, the `fuzzy` flag of a filled entry is dropped |

A text whose placeholders or rich text tags differ from its source line (the `en` column of the final files) is held back. It is not written, the game's table keeps the text it has, and the key is listed under `held_back` with the difference. A text without a source line is not checked. A key name two Unity tables share needs its `Table:Key` label in the final files (the form `build_context_map.py` uses), otherwise the export stops instead of guessing. Only Unity tables with a changed text are written. On the first project a round trip of the studio reference through all 23 Turkish tables left every table byte for byte the same.

| Flag | Meaning |
|---|---|
| `--input` (or positional) | a final file, or the orchestrator's workdir |
| `--locale` | target locale |
| `--changes` | change report with filled decisions, repeatable, default the reports in the INPUT folder |
| `--template` | the game's table of the target locale, repeatable |
| `--template-dir` | folder of Unity StringTable assets, every table of `--locale` in it (found by `m_LocaleId`) is a template |
| `--shared-table` | Shared Data asset of a single Unity template when it is not next to the table |
| `--out` | output folder, refused inside a Unity, Godot or Unreal project and as the folder of a template |
| `--dst-field` | target column of the final files and of a CSV or JSON template, default the locale code |
| `--key-field` | key column, default `key` |
| `--placeholder-style`, `--tag-style` | syntax for the parity check against the source line, default `auto` or `placeholder_style` and `tag_style` of `--config` |

Exit codes. 0 exported, every changed line decided and every key placed. 1 exported but changed lines without a decision, texts held back for their placeholders or tags, or keys no template holds. 2 usage or input error (a decision other than accept or reject, a key two tables share without its label, an output inside the game project).

## Prompt templates (prompts/)

| File | Use |
|---|---|
| `prompts/critic.<locale>.md` (all 15 locales) | native critic prompt written in the target language. A concrete player persona (not a translator), warm-up slot, contrastive pair slot, 1 to 5 rubric, issue types, task order and the vote schema `{"votes": [{key, score, issue_type, reason, suggested}]}` |
| `prompts/critic.generic.md` | English fallback, used only when a project adds a locale without its own critic prompt |
| `prompts/pass2.<locale>.md` (all 15 locales), `prompts/pass2.generic.md` | Pass 2 rewrite prompt (writer persona, warm-up and contrastive slots, seven step task order, three candidates per line) |
| `prompts/literal.md` | instruction for the robot side of contrastive pairs (word for word, English word order, no idioms, placeholders kept) |

A template starts with a short frontmatter block (`name`, `locale`, `language`, `empty_warmup`, `empty_contrastive`) and uses the slots `{{LOCALE}}`, `{{WARMUP}}` and `{{CONTRASTIVE}}`. `prompt_templates.render_prompt(name, locale, warmup, contrastive)` picks `<name>.<locale>.md`, then `<name>.generic.md`, then `<name>.md`, fills the slots and rejects unknown ones. `render_contrastive(pairs, count, seed)` builds the seeded few-shot block, one `✓` native line and one `✗` robot line per pair. The jurors never write `tier`, `member`, `family` or `model`, the harness adds them.

Prompts, README, the docs and every generated Markdown report follow one punctuation style, checked by `text_style.punctuation_problems()`. Prose has no semicolons, no en or em dashes and no colon inside a sentence. Code blocks, inline code, URLs and frontmatter are exempt.

---

## localization_pipeline_template.workflow.py (Antigravity `/run-workflow` template)

Not a standalone Python module, it uses the workflow DSL with top-level `await`. Run it from Antigravity.

```
/run-workflow Run skills/game-cultural-localization/scripts/localization_pipeline_template.workflow.py
   with args {"locale": "de-DE", "scratch_dir": "loc_work", "batches": ["01", "02"], "plugin_dir": "<plugin path>", "fonts": [], "placeholder_style": "unity", "tag_style": "tmp", "context_map": "loc_work/context/CONTEXT_MAP.md"}
```

`context_map` defaults to `<scratch_dir>/context/CONTEXT_MAP.md`. Phase 0 stops at once when the map is missing, nothing is translated or judged before it exists. Pass 1 and Pass 2 read the map, the locale appendix `CONTEXT_MAP.<locale>.md` and the line notes, and choose every word for the place of the line, no term is locked in a list. The blind critic reads the slice (with `archetype`), the jurors' English view of the map (`CONTEXT_MAP.jury.md`) and the neutral fields of `line_notes.jury.json`, the user's map and notes only when there is no English view, never the appendix and never a pass1 or final batch. Its blindness rests on its prompt and on its two tools, `view_file` and `write_to_file`. Antigravity offers no per call tool limit, so the critic could still open a file with the source column. In the API flow (`jury.py`) the code keeps the source out of every juror's request.

Phase 0 pre-flight, Phase 1 Pass 1 (`game-culturalizer`, parallel per batch, failed batches retried one by one), Phase 2 `make_blind_slice`, `native-ear-critic`, `validate_critique` and Pass 2, Phase 3 gate (`lqa_linter --fail-on-error`, `ui_expansion_checker --fail-on-high`, `font_glyph_scanner`). The template drives the single critic flow, the multi-family jury runs through `orchestrator_stub.py --dry-run` or `--live`.

---

## l10n.config.json

```json
{
  "locales": ["de-DE", "fr", "ja-JP"],
  "src_field": "en", "dst_field": "dst", "key_field": "key",
  "placeholder_style": "unity", "tag_style": "tmp", "placeholder_regex": "\\$\\w+\\$",
  "rules_dir": "loc/rules", "glossary": "loc/termbase.csv", "glossary_severity": "ERR",
  "max_width": {"*": 40, "BTN_APPLY": 12, "ja-JP": 30}, "expansion": {"de-DE": 1.4}, "cjk_cell_width": 1.8,
  "ambiguous_wide": false, "fail_on_warn": false, "forbid_chars": ";—", "forbid_spaced_hyphen": true, "strict_whitespace": true,
  "context_map": "loc_work/context/CONTEXT_MAP.md"
}
```

Unknown keys or wrong types abort with exit 2. Relative `rules_dir`, `glossary` and `context_map` paths resolve from the config file's folder. The model tools read the keys that concern them, `eval_critic.py` and `deliberate.py` the `context_map`, `jury.py` also the field names of its source table, `pass2_rewrite.py` also `placeholder_style` and `tag_style`, `orchestrator_stub.py` all of them plus the gate rules `forbid_chars`, `forbid_spaced_hyphen`, `strict_whitespace` and `fail_on_warn` for its Phase 3 gate. An explicit flag always wins over the config.

---

## Tests

```
python -m unittest discover tests          # from the repository root (or tests/run_all.ps1)
```
