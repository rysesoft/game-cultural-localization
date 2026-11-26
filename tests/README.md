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

Fixtures live in `tests/fixtures/` (JSON, BOM-JSON, CSV, semicolon CSV, multi-line CSV, TSV, PO LF/CRLF, Unity StringTable `.asset`, TMP FontAsset `.asset` static/dynamic, fake font). Temporary files are created under the OS temp directory, never inside the repository.
