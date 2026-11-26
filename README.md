# Game Cultural Localization

**AI translated game text usually reads correct and still sounds translated. This plugin makes it sound native.** It is a game localization suite for AI coding agents and LLM tools. It turns machine or LLM first drafts into natural game text in 15 locales, and a jury of three model families checks the result line by line without a human native reviewer in the loop. Built for localization leads, narrative teams and indie developers who ship with AI assisted translation and refuse to ship translationese. Antigravity is the primary target. Claude Code, Gemini CLI, Cursor, Codex and any plain LLM API are supported through the open Agent Skills format.

[![CI](https://github.com/rysesoft/game-cultural-localization/actions/workflows/tests.yml/badge.svg)](https://github.com/rysesoft/game-cultural-localization/actions/workflows/tests.yml) [![License MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE) [![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB.svg)](#specification) [![Languages 15](https://img.shields.io/badge/languages-15-success.svg)](#supported-languages) [![Zero dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#specification)

[Türkçe README](./README_TR.md). Maintained by [Rysesoft](https://github.com/rysesoft).

## The Problem

Machine and LLM drafts get the meaning right and the voice wrong. They keep English word order, reach for bureaucratic verbs and repeat pronouns the target language would drop. Players hear it within one line. The examples below come from the Golden Voice Anchors in the playbooks, so agents and humans calibrate on the same lines.

| Locale | Source (EN) | Typical MT or LLM output | What this suite expects | Why |
|---|---|---|---|---|
| `tr-TR` A1 Mentor | Start with whatever you can salvage and get the workshop running again. Do that, and I'll send a few contracts your way. | Mevcut malzemeleri geri dönüştürerek atölye operasyonlarını yeniden tesis et, ardından sana sözleşmeler aktaracağım. | Eldeki hurdadan ne çıkarabiliyorsan onunla başla, şu dükkânı yeniden ayağa kaldır. Çarkı bir döndür, kendi işlerimden birkaçını sana paslarım. | Bureaucratic verbs replaced with workshop talk, warm senior register kept |
| `de-DE` A1 Mentor | Same line | Beginne mit der Verwertung verfügbarer Materialien, um den Werkstattbetrieb wiederherzustellen, und ich werde Aufträge an dich übertragen. | Fang mit dem an, was du aus dem Schrott rausholen kannst, und bring den Laden wieder zum Laufen. Dann schieb ich dir ein paar von meinen Aufträgen rüber. | Spoken du register, no nominal style, no calqued future tense |
| `ja-JP` A4 Engineer | The generator's output is unstable. Don't run it above 80% until I've recalibrated the coils. | 発電機の出力は不安定です。私がコイルを再調整するまで、それを80%以上で稼働させないでください。 | 発電機の出力が安定してません。コイルを調整し直すまで、80%以上は出さないでくださいね。 | Redundant 私 and それ dropped, conversational 丁寧語 instead of manual speak |

The fourth column is what the suite aims for. The rest of this page shows how it gets there and how it proves it.

## How It Fixes It

| Layer | What it does |
|---|---|
| Craft | 15 culturalization playbooks with Golden Voice Anchors and five voice archetypes. A culturalizer agent writes Pass 1 and Pass 2, and a native ear critic scores a blind slice that never shows the English |
| Gates | Linter, UI overflow checker, font glyph scanner and critique validator in pure Python with exit codes 0, 1 and 2. A broken placeholder, a clipped button or a missing glyph never reaches the build |
| Measurement (2.2) | Claude, Gemini and DeepSeek judge every line blind in three tiers, a professional reference calibrates them, and every change arrives with a reason, evidence, confidence and a trust level |

## Multi-Family Jury (2.2)

Version 2.2 replaces the single critic with a jury of three model families and measures how native the result sounds, without a human native reviewer in the loop. A family that likes its own style is outvoted by the two others.

| Step | What happens |
|---|---|
| Language pack | `build_language_pack.py` builds `langpack/<locale>/` from licensed game and UI corpora plus the studio's own translation. Copyleft sources stay on the local machine |
| Warm-up and pairs | `warmup_loader.py` puts 30 to 50 native lines into every prompt, `build_contrastive_set.py` pairs native lines with deliberately literal robot lines |
| Calibration | `eval_critic.py` checks that every juror prefers the native line in at least 85% of the pairs |
| Jury | `jury.py` runs three tiers of Claude, Gemini and DeepSeek on a blind slice. Clear lines settle early, critical lines go straight to the strongest tier, disagreements go through anonymous deliberation |
| Rewrite | `pass2_rewrite.py` writes three candidates, the cheapest tier picks one blind, `validate_critique` checks it |
| Report | `report_changes.py` lists every change with old and new text, reason, evidence, confidence and votes. The developer accepts or rejects, `tm.py` remembers the decision |

**Agreement.** Every tier holds one model from each family. A line passes when all three scores are 4 or 5 and differ by at most 1. Any score of 3 or lower, or a spread of 2 or more, moves the line to the next tier. Any score of 2 or lower sends it straight to J3. When J3 still disagrees, the jurors read each other's reasons without model names and vote again. A majority settles the line, otherwise it goes to the developer as unresolved.

**Budget caps.** When more than 30% of a batch would go to J2, or more than 10% to J3, the run stops and writes the report. At that point the problem is in Pass 1 or in the prompt, not in single lines.

**Trust levels.** Every change report says how far its verdicts can be trusted.

| Level | When | Meaning of a verdict |
|---|---|---|
| measured | professional reference and a passing calibration | measured against the professional translation |
| estimated | a language pack is installed | estimated from proxy signals |
| rule based | no language pack | only the rule based gates speak for the line |

### Turkish language pack

`langpack/tr-TR/` ships with the plugin. Its warm-up corpus holds 7054 lines. About 1400 of them come from the professional Turkish translation of a Rysesoft game, the rest from the Godot editor and Pixelorama translations (MIT). Copyleft corpora such as Wesnoth, OpenTTD and KDE feed the pack only on the machine that builds it and are never distributed. The studio reference wins over every filter heuristic. When a rule keeps flagging the professional translation, the rule is narrowed and the line stays.

Live calibration of the jury against this reference is the next milestone. Until it passes, reports mark Turkish as estimated. Any other locale gets its pack from `build_language_pack.py`, and a studio reference table with `key`, `en`, `<locale>`, `category` and `speaker` columns puts it on the path to measured.

**Try it without a key.** Every tool runs offline with `--dry-run`. Run this from `skills/game-cultural-localization/` to see the whole flow.

```bash
python scripts/orchestrator_stub.py --dry-run --locale tr-TR --input strings.json --workdir out/
```

API keys come only from `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` and `DEEPSEEK_API_KEY`, model ids from `scripts/providers.config.json`. `--live` runs the same flow with the real APIs, and `budget_report.py` turns the logged calls into a cost estimate for a full project. Details are in [methodology_and_qa.md](./skills/game-cultural-localization/references/methodology_and_qa.md) and [CLI_REFERENCE.md](./skills/game-cultural-localization/scripts/CLI_REFERENCE.md).

## What You Get

1. **15 culturalization playbooks** with Golden Voice Anchors tagged with five voice archetypes (A1 to A5).
2. **Two agent prompts.** A culturalizer for Pass 1 and Pass 2, and a blind native ear critic that only ever reads a target only slice.
3. **Native jury prompts in all 15 languages.** Every locale has its own critic and Pass 2 prompt, written in that language with a local player or writer persona.
4. **Deterministic gates.** Linter, UI overflow checker, font tofu scanner, blind slice generator and critique validator, all pure Python with zero dependencies.
5. **Mixed-family LLM jury.** Claude, Gemini and DeepSeek judge every line blind in three tiers, settle disagreements by anonymous deliberation and hand the developer a change report with reasons, evidence and confidence.
6. **A Turkish language pack** built from a professional game translation, ready for the jury to calibrate on.

## Supported Languages

| Locale | Playbook | Notes |
|---|---|---|
| `en` | [en.md](./skills/game-cultural-localization/references/en.md) | Source polish only (placeholder English, concatenation hygiene) |
| `tr-TR` | [tr-TR.md](./skills/game-cultural-localization/references/tr-TR.md) | Suffix and apostrophe rules for placeholders, built language pack |
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
| Native quality measured by a calibrated jury of three model families | no | no | yes, `jury.py` with `eval_critic.py` calibration |
| Per language culturalization playbook and five voice archetypes | no | partial (style guides) | yes, 15 playbooks on one template |
| Deterministic gates with exit codes 0/1/2 | no | partial (QA checks) | yes, linter, UI, font, critique schema |
| Engine independent tokens (Unity, Unreal, Godot, ICU, printf) | partial | partial | yes, parity checked per style |
| API independent (any LLM, plain system prompts) | yes | no (vendor bound) | yes |
| Zero dependencies | n/a | no | yes, Python 3.9+ stdlib only |
| Gender neutral player voice per language | no | no | yes, playbook section 4 |
| Plural and ICU categories (few, many) | no | partial | yes, playbook section 5 |
| Regional leak detection (pt-BR in pt-PT, zh-CN in zh-Hant) | no | partial | yes, data driven rules |

## How It Works (Phase 0 to 3)

| Phase | What happens | Gate |
|---|---|---|
| 0 Preflight | Checksums, concatenation scan, font glyph scan, `glossary.csv`, `<LOCALE>_BIBLE.md`, transcreation ledger, pseudo localization | Seams and collision terms recorded, 0 missing glyphs |
| 1 Clean room Pass 1 | `game-culturalizer` translates clean source batches calibrated on the playbook and archetypes | `lqa_linter.py` exit 0 per batch |
| 2 Blind critique and Pass 2 | `make_blind_slice.py` strips the source, `native-ear-critic` scores every line 1 to 5, `validate_critique.py` checks the schema, `game-culturalizer` rewrites every score below 5 | 95% of lines at 5, 0 lines at 2 or below |
| 3 Automated gate | `lqa_linter.py --fail-on-error`, `ui_expansion_checker.py --fail-on-high`, `font_glyph_scanner.py`, write back, checksum scope check | All exit 0, only target locale files changed |

The five archetypes are A1 Mentor, A2 Hotshot Rival, A3 Rookie, A4 Scientist and A5 Antagonist. UI text uses the locked UI register of the locale instead. With `--dry-run` or `--live` the orchestrator runs Phase 2 as the jury flow described above. The full runbook with per phase inputs and outputs is in [methodology_and_qa.md](./skills/game-cultural-localization/references/methodology_and_qa.md).

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

`scripts/orchestrator_stub.py` runs the same loop. `--provider module:function` takes any `complete(system, user) -> str` callable, `--dry-run` runs the multi-family jury offline and `--live` runs it with the real APIs.

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

Issue types are `translationese`, `register`, `tense`, `regional_leak`, `gender_leak`, `ui_verb`, `placeholder_grammar`, `terminology` and `other` (with optional `needs_source_check`).

### File layout

```
plugin.json                 Antigravity manifest (version lives here)
README.md, README_TR.md     this page in English and in Turkish
rules/AGENTS.md             always on rules, also usable as AGENTS.md or CLAUDE.md content
agents/                     game-culturalizer.md, native-ear-critic.md
skills/game-cultural-localization/
  SKILL.md                  Agent Skills entry point, archetypes, 8 laws, minimal instructions
  references/               15 playbooks, methodology_and_qa.md, transcreation_ledger_guide.md
  scripts/                  CLI tools, rules/<locale>.json, CLI_REFERENCE.md, workflow template, orchestrator, providers/ and the jury tools
  prompts/                  native critic and Pass 2 prompts for 15 locales, literal.md
  langpack/                 sources.manifest.json and the built language packs (local/ stays on the machine)
tests/                      python -m unittest discover tests
.github/                    CI workflow, issue and PR templates
```

## Contributing

Pull requests are welcome. Run `python -m unittest discover tests` and `agy plugin validate --strict .` if you have the CLI. Keep playbooks on the 12 section template, keep examples project independent, and add a line to [CHANGELOG.md](./CHANGELOG.md). README.md and README_TR.md move together, a test checks that both have the same sections. Templates live in [.github](./.github/).

## License

[MIT](./LICENSE). Maintained by Rysesoft.
