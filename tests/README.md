# Tests

Standard-library `unittest` only. Run from the repository root:

```
python -B -m unittest discover tests      # -B keeps __pycache__ out of the source tree
pwsh tests/run_all.ps1          # runs the suite with every Python it finds (bundled runtime, py -3.14, python)
```

| Module | Covers |
|---|---|
| `test_common.py` | locale aliases, placeholder styles (unity/unreal/godot/icu/printf/python, `%` false positives, ICU nesting), rich-text tags (full TMP set, order, colour names, BBCode), visual width (NFC, zero-width, ambiguous), PO (multi-line, plural, fuzzy, msgctxt, CRLF), loaders (BOM, delimiter sniffing, column validation, JSON shapes, Unity YAML), glossary layouts, config |
| `test_rules_selftest.py` | every `rules/<locale>.json` compiles, every `examples.match` matches and `examples.nomatch` does not, ids unique, ≥ 70 % of the playbook ban-table examples are flagged, known false positives stay clean, `--variant hk`, contexts (player/button), `lqa_ignore`, invalid rule files |
| `test_lqa_linter.py` | exit codes 0/1/2, 15 locales, BOM/CSV/TSV/PO/Unity inputs, `--json` schema + file, determinism, `--max-report`, Windows cp1252 pipe, glossary + config, placeholder/tag styles, custom rules, strict whitespace, 50k-row performance (< 10 s) |
| `test_ui_expansion.py` | audit cases (ON→EINGESCHALTET …), locale factors, CJK/ambiguous width, budgets (`max_chars`, `--max-width`, config table), line-count, sorting, CLI/JSON/config |
| `test_font_glyph.py` | synthetic TTF (cmap 4 + 12), TTC, WOFF, corrupt fonts → exit 2, TMP static vs dynamic (`--strict`), character collection, real `msgothic.ttc` when present |
| `test_blind_slice_and_critique.py` | blind slice has no source column, leak refusal, CSV/TSV/PO/.asset inputs, CSV output; critique schema validation, parity, CLI |
| `test_pipeline_and_cli.py` | workflow template compiles with top-level await and references existing scripts, orchestrator dry-run passes deterministically / fails on bad output, `--help`/`--version` for every script, CLI_REFERENCE.md documents every flag |
| `test_providers.py` | provider config validation (model ids, one family per jury tier, missing keys), request shape of the three adapters, retry and backoff, model fallback, local urllib round trip, fake provider scenarios, budget log, `providers_check.py` exit codes |
| `test_language_pack.py` | bundled manifest (no OpenSubtitles, license classes, https URLs), corpus parsers (PO, properties, Fluent, OpenTTD, nested JSON), register inference, tr-TR and de-DE packs built offline, one dropped and one passing row per filter layer, local class rows never outside `local/`, hash pin and lock, determinism, exit codes |
| `test_warmup.py` | same seed gives the same sample, register filter, local toggle, source balancing with the reference first, cleaning of engine codes, prompt block, exit codes |
| `test_prompts.py` | critic prompts are written in Turkish and German with persona, slots, rubric, seven step task order and vote schema, generic fallback, `literal.md`, slot rendering, seeded contrastive block, punctuation style of every prompt file |
| `test_contrastive.py` | reference loading and registers, B3.5 pair schema, `literal.md` used for robot lines, identical and broken robot lines dropped, seeded subset, fake provider dry run, budget log roles, exit codes |
| `test_roundtrip.py` | calque score range, register and word count eligibility (no call for ineligible rows), threshold search, calibration from a contrastive set, weak calibration, check mode with the calibrated pack threshold, exit codes |

Fixtures live in `tests/fixtures/` (JSON, BOM-JSON, CSV, semicolon CSV, multi-line CSV, TSV, PO LF/CRLF, Unity StringTable `.asset`, TMP FontAsset `.asset` static/dynamic, fake font). Temporary files are created under the OS temp directory, never inside the repository.
