# Game Cultural Localization

**Game localization plugin for AI coding agents and LLM tools.** It turns machine or LLM first drafts into natural, native sounding game text in 15 locales. Built for localization leads, narrative teams, and indie developers who ship with AI assisted translation and refuse to ship translationese. Antigravity is the primary target. Claude Code, Gemini CLI, Cursor, Codex, and any plain LLM API are supported through the open Agent Skills format.

[![CI](https://github.com/rysesoft/game-cultural-localization/actions/workflows/tests.yml/badge.svg)](https://github.com/rysesoft/game-cultural-localization/actions/workflows/tests.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE) [![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB.svg)](#specification) [![Languages 15](https://img.shields.io/badge/languages-15-success.svg)](#supported-languages) [![Zero dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#specification)

Maintained by [Rysesoft](https://github.com/rysesoft) at [github.com/rysesoft/game-cultural-localization](https://github.com/rysesoft/game-cultural-localization).

## What You Get

1. **15 culturalization playbooks** with Golden Voice Anchors tagged with five voice archetypes (A1 to A5).
2. **Two agent prompts.** A culturalizer for Pass 1 and Pass 2, and a blind native ear critic that only ever reads a target only slice.
3. **Deterministic gates.** Linter, UI overflow checker, font tofu scanner, blind slice generator, and critique validator, all pure Python with zero dependencies.

## Supported Languages

| Locale | Playbook | Notes |
|---|---|---|
| `en` | [en.md](./skills/game-cultural-localization/references/en.md) | Source polish only (placeholder English, concatenation hygiene) |
| `tr-TR` | [tr-TR.md](./skills/game-cultural-localization/references/tr-TR.md) | Suffix and apostrophe rules for placeholders |
| `de-DE` | [de-DE.md](./skills/game-cultural-localization/references/de-DE.md) | Perfekt vs Präteritum, du/Sie lock, ẞ handling |
| `fr` | [fr.md](./skills/game-cultural-localization/references/fr.md) | Covers fr-FR, with a fr-CA note for Québec terminology and spacing |
| `es-ES` | [es-ES.md](./skills/game-cultural-localization/references/es-ES.md) | Peninsular Spanish, tú/usted |
| `it-IT` | [it-IT.md](./skills/game-cultural-localization/references/it-IT.md) | Passato prossimo, tu/Lei |
| `pt-BR` | [pt-BR.md](./skills/game-cultural-localization/references/pt-BR.md) | Brazilian, separate from pt-PT, leak checks both ways |
| `pt-PT` | [pt-PT.md](./skills/game-cultural-localization/references/pt-PT.md) | European, tu/você, separate playbook |
| `pl-PL` | [pl-PL.md](./skills/game-cultural-localization/references/pl-PL.md) | Three plural forms, gender neutral past tense |
| `lt-LT` | [lt-LT.md](./skills/game-cultural-localization/references/lt-LT.md) | Plural forms, vocative, diacritic font check |
| `ru-RU` | [ru-RU.md](./skills/game-cultural-localization/references/ru-RU.md) | Three plural forms, канцелярит ban list, ты/вы |
| `ja-JP` | [ja-JP.md](./skills/game-cultural-localization/references/ja-JP.md) | 役割語, UI register lock, counters, 禁則処理 |
| `ko-KR` | [ko-KR.md](./skills/game-cultural-localization/references/ko-KR.md) | 화계 lock, particle traps after placeholders |
| `zh-CN` | [zh-CN.md](./skills/game-cultural-localization/references/zh-CN.md) | Simplified, Mainland terminology and compliance notes |
| `zh-Hant` | [zh-Hant.md](./skills/game-cultural-localization/references/zh-Hant.md) | Traditional, Taiwan default with a Hong Kong subsection (`--variant hk`) |

## Why This Is Different

| Capability | Plain MT or LLM prompt | CAT tool AI plugins | This suite |
|---|---|---|---|
| Blind native ear critique (reviewer never sees the source) | no | no | yes, enforced by `make_blind_slice.py` |
| Per language culturalization playbook and five voice archetypes | no | partial (style guides) | yes, 15 playbooks on one template |
| Deterministic gates with exit codes 0/1/2 | no | partial (QA checks) | yes, linter, UI, font, critique schema |
| Engine independent tokens (Unity, Unreal, Godot, ICU, printf) | partial | partial | yes, parity checked per style |
| API independent (any LLM, plain system prompts) | yes | no (vendor bound) | yes |
| Zero dependencies | n/a | no | yes, Python 3.9+ stdlib only |
| Gender neutral player voice per language | no | no | yes, playbook section 4 |
| Plural and ICU categories (few, many) | no | partial | yes, playbook section 5 |
| Regional leak detection (pt-BR in pt-PT, zh-CN in zh-Hant) | no | partial | yes, data driven rules |

## Before and After

Examples come from the Golden Voice Anchors in the playbooks, so agents and humans calibrate on the same lines.

| Locale | Source (EN) | Typical MT or LLM output | What this suite expects | Why |
|---|---|---|---|---|
| `tr-TR` A1 Mentor | Start with whatever you can salvage and get the workshop running again. Do that, and I'll send a few contracts your way. | Mevcut malzemeleri geri dönüştürerek atölye operasyonlarını yeniden tesis et; ardından sana sözleşmeler aktaracağım. | Eldeki hurdadan ne çıkarabiliyorsan onunla başla, şu dükkânı yeniden ayağa kaldır. Çarkı bir döndür, kendi işlerimden birkaçını sana paslarım. | Bureaucratic verbs replaced with workshop talk, warm senior register kept |
| `de-DE` A1 Mentor | Same line | Beginne mit der Verwertung verfügbarer Materialien, um den Werkstattbetrieb wiederherzustellen, und ich werde Aufträge an dich übertragen. | Fang mit dem an, was du aus dem Schrott rausholen kannst, und bring den Laden wieder zum Laufen. Dann schieb ich dir ein paar von meinen Aufträgen rüber. | Spoken du register, no nominal style, no calqued future tense |
| `ja-JP` A4 Engineer | The generator's output is unstable. Don't run it above 80% until I've recalibrated the coils. | 発電機の出力は不安定です。私がコイルを再調整するまで、それを80%以上で稼働させないでください。 | 発電機の出力が安定してません。コイルを調整し直すまで、80%以上は出さないでくださいね。 | Redundant 私 and それ dropped, conversational 丁寧語 instead of manual speak |

## How It Works (Phase 0 to 3)

| Phase | What happens | Gate |
|---|---|---|
| 0 Preflight | Checksums, concatenation scan, font glyph scan, `glossary.csv`, `<LOCALE>_BIBLE.md`, transcreation ledger, pseudo localization | Seams and collision terms recorded, 0 missing glyphs |
| 1 Clean room Pass 1 | `game-culturalizer` translates clean source batches calibrated on the playbook and archetypes | `lqa_linter.py` exit 0 per batch |
| 2 Blind critique and Pass 2 | `make_blind_slice.py` strips the source, `native-ear-critic` scores every line 1 to 5, `validate_critique.py` checks the schema, `game-culturalizer` rewrites every score below 5 | 95% of lines at 5, 0 lines at 2 or below |
| 3 Automated gate | `lqa_linter.py --fail-on-error`, `ui_expansion_checker.py --fail-on-high`, `font_glyph_scanner.py`, write back, checksum scope check | All exit 0, only target locale files changed |

The five archetypes are A1 Mentor, A2 Hotshot Rival, A3 Rookie, A4 Scientist, and A5 Antagonist. UI text uses the locked UI register of the locale instead. The full runbook with per phase inputs and outputs is in [methodology_and_qa.md](./skills/game-cultural-localization/references/methodology_and_qa.md).

## Install

The skill folder follows the open [Agent Skills](https://agentskills.io/specification) format, so the same `skills/game-cultural-localization/` directory loads in several tools. Paths below come from each vendor's official documentation.

| Tool | Playbooks and scripts (skill) | Agents | Rules | Workflow template |
|---|---|---|---|---|
| Antigravity | yes, plugin install | yes, `agents/*.md` as is | yes, `rules/AGENTS.md` | yes, `/run-workflow` |
| Claude Code | yes, `~/.claude/skills/` or `.claude/skills/` | yes, copy to `.claude/agents/` and set `tools:` to Claude names (`Read, Write, Bash`) | manual, paste into `CLAUDE.md` | no, use `orchestrator_stub.py` |
| Gemini CLI | yes, `~/.gemini/skills/` or `.gemini/skills/` (`.agents/skills/` alias) | manual, as system prompts | manual, paste into `GEMINI.md` | no |
| Cursor | yes, `.agents/skills/` or `.cursor/skills/` (also reads `.claude/skills/`) | manual, as subagent prompts | yes, `AGENTS.md` or `.cursor/rules/` | no |
| OpenAI Codex | yes, `.agents/skills/` in the repo or `~/.agents/skills/` | manual, as system prompts | yes, `AGENTS.md` at the repo root | no |
| Any LLM API | yes, attach files as context | yes, prompt bodies | yes, prepend to the system prompt | `orchestrator_stub.py` |

**Antigravity**

```bash
agy plugin validate --strict ./game-cultural-localization
agy plugin install ./game-cultural-localization
```

Or copy the folder to `~/.gemini/config/plugins/game-cultural-localization/` (global) or `<project>/.agents/plugins/game-cultural-localization/` (workspace). Then type `/game-cultural-localization`, pick a suggested prompt, or select `game-culturalizer` as the main agent (`agy --agent game-culturalizer`). Start a new conversation after updating the plugin.

**Claude Code, Gemini CLI, Cursor, Codex**

```bash
# project scope, pick the directory your tool reads (see the table)
cp -r game-cultural-localization/skills/game-cultural-localization .agents/skills/
cp -r game-cultural-localization/skills/game-cultural-localization .claude/skills/
cat game-cultural-localization/rules/AGENTS.md >> AGENTS.md
```

The skill's `name` and `description` are loaded at session start and the body on demand in every listed tool. Scripts run the same way everywhere with `python`.

**Any LLM API or CAT tool**

1. Use the body of [agents/game-culturalizer.md](./agents/game-culturalizer.md) as the system prompt for Pass 1 and Pass 2, and the body of [agents/native-ear-critic.md](./agents/native-ear-critic.md) for the critique. Attach [SKILL.md](./skills/game-cultural-localization/SKILL.md) and one playbook as context.
2. Send `in_<locale>_<batch>.json` and save the reply as `pass1_<locale>_<batch>.json`.
3. Run `make_blind_slice.py`, send only the slice to the critic in a fresh conversation, save `critique_<locale>_<batch>.json`, and run `validate_critique.py`.
4. Send the Pass 1 file plus the validated critique for Pass 2, then run the Phase 3 gate.

`scripts/orchestrator_stub.py` runs the same loop against any provider that implements `complete(system, user) -> str` (start with `--dry-run`).

## CLI Summary

Run from `skills/game-cultural-localization/`. Every flag is documented in [CLI_REFERENCE.md](./skills/game-cultural-localization/scripts/CLI_REFERENCE.md).

```bash
python scripts/font_glyph_scanner.py --input strings.en.json --dst-field en --font ./Fonts/UI.ttf --font ./Fonts/Fallback.ttc
python scripts/lqa_linter.py --input pass1_de-DE_01.json --locale de-DE --src-field en --dst-field dst --glossary glossary.csv --glossary-severity ERR --fail-on-error
python scripts/make_blind_slice.py pass1_de-DE_01.json --locale de-DE --out blind_de-DE_01.json --key-col key --target-col dst --context-cols category,speaker,archetype
python scripts/validate_critique.py critique_de-DE_01.json --slice blind_de-DE_01.json
python scripts/lqa_linter.py --input final_de-DE.json --locale de-DE --src-field en --dst-field dst --glossary glossary.csv --glossary-severity ERR --json lqa_de-DE.json --fail-on-error
python scripts/ui_expansion_checker.py --input final_de-DE.json --locale de-DE --src-field en --dst-field dst --json ui_de-DE.json --fail-on-high
```

## Specification

| Item | Value |
|---|---|
| Locales | 15 (table above), aliases mapped (`de` to `de-DE`, `pt_BR` to `pt-BR`, `zh-TW` and `zh-HK` to `zh-Hant`), unknown locale exits 2 |
| Input formats | JSON list, JSON dict, CSV, TSV, Gettext PO (multi line and plural `msgstr`), Unity Localization StringTable `.asset` |
| Placeholder styles | `auto`, `unity` (`{0}`, `{name}`, Smart Strings), `unreal` (`{Name}`, `\|hpp`), `godot` (`%s`, `{name}`), `icu` (plural and select), `printf`, `python` |
| Tag styles | `tmp` (`<b> <color=> <sprite=> <style=> <link=>`), `html`, `bbcode` (`[b] [color=] [url=]`) |
| Runtime | Python 3.9 or newer, standard library only, UTF-8 in and out, BOM tolerant |
| Exit codes | 0 clean, 1 findings (errors, or warnings with `--fail-on-warn`, HIGH with `--fail-on-high`), 2 usage or input error |
| Glossary | `glossary.csv` with header `term_en,<locale>[,<locale>...],notes`, enforced by `--glossary` |
| Critique file | `critique_<locale>_<batch>.json`, naturalness score 1 to 5 plus an issue type, only scores below 5 listed |

Input row example (only `key` and `en` are required) and critique entry example.

```json
{"key": "dlg.mentor.intro_01", "en": "Take your time, kid. The {itemName} isn't going anywhere.", "category": "dialogue", "speaker": "Mentor", "archetype": "A1"}
```

```json
{"locale": "de-DE", "source_file": "blind_de-DE_01.json",
 "entries": [{"key": "dlg.mentor.intro_01", "score": 3, "issue_type": "translationese",
              "reason": "Calqued English word order.", "suggested": "Lass dir Zeit. Der {itemName} läuft dir nicht weg."}],
 "summary": {"total": 120, "flagged": 1, "critical": 0}}
```

Issue types are `translationese`, `register`, `tense`, `regional_leak`, `gender_leak`, `ui_verb`, `placeholder_grammar`, `terminology`, and `other` (with optional `needs_source_check`).

### File layout

```
plugin.json                 Antigravity manifest (version lives here)
rules/AGENTS.md             always on rules, also usable as AGENTS.md or CLAUDE.md content
agents/                     game-culturalizer.md, native-ear-critic.md
skills/game-cultural-localization/
  SKILL.md                  Agent Skills entry point, archetypes, 8 laws, minimal instructions
  references/               15 playbooks, methodology_and_qa.md, transcreation_ledger_guide.md
  scripts/                  CLI tools, rules/<locale>.json, CLI_REFERENCE.md, workflow template, orchestrator stub
tests/                      python -m unittest discover tests
.github/                    CI workflow, issue and PR templates
```

## Contributing

Pull requests are welcome. Run `python -m unittest discover tests` and `agy plugin validate --strict .` if you have the CLI. Keep playbooks on the 12 section template, keep examples project independent, and add a line to [CHANGELOG.md](./CHANGELOG.md). Templates live in [.github](./.github/).

## License

[MIT](./LICENSE). Maintained by Rysesoft.

## Türkçe Özet

Bu eklenti, yapay zekâ kodlama ajanları ve LLM araçları için bir oyun yerelleştirme aracıdır. Makine ya da LLM taslaklarını 15 dilde doğal ve yerli ses veren metne dönüştürür. İçinde beş ses arketipiyle etiketlenmiş 15 dil rehberi, İngilizceyi hiç görmeden değerlendiren kör denetçi ajanı, konuşma dili editörü ve sıfır bağımlılıkla çalışan Python kapıları vardır. Antigravity birincil hedeftir. Aynı skill klasörü Claude Code, Gemini CLI, Cursor ve Codex tarafından da okunur. Rehberler ve ajan promptları herhangi bir LLM ile düz sistem promptu olarak kullanılabilir.

Hızlı kullanım için üç adım yeter. Önce `agy plugin install ./game-cultural-localization` ile kur ya da skill klasörünü aracının okuduğu dizine kopyala. Sonra dizgileri `[{"key", "en", "category", "speaker", "archetype"}]` biçiminde JSON olarak dışa aktar ve `/game-cultural-localization` komutuyla dört fazlı akışı başlat. En sonda `lqa_linter.py --fail-on-error`, `ui_expansion_checker.py --fail-on-high` ve `font_glyph_scanner.py` üçü de 0 ile çıkmadan dili bitmiş sayma. Çıkış kodu 2 komut ya da girdi hatası demektir ve asla sessiz geçilmez. Türkçe rehber [tr-TR.md](./skills/game-cultural-localization/references/tr-TR.md) dosyasındadır.
