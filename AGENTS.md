# Agent Guide

Read this file first. It tells an AI agent where to start in this repository and which rules are never optional. `CLAUDE.md` imports it for Claude Code, Codex, Cursor, Copilot and Gemini CLI read it directly.

This repository is the **Game Cultural Localization** plugin. It turns machine or LLM drafts of game text into native sounding text in 15 locales, with a context map of the game, culturalization playbooks, a blind critic, a jury of three model families and deterministic gates.

## Which job are you doing?

### A. Localizing a game with the plugin

1. Read [skills/game-cultural-localization/SKILL.md](./skills/game-cultural-localization/SKILL.md) and the always on rules in [rules/AGENTS.md](./rules/AGENTS.md).
2. **Context map first, every time.** Run [agents/context-cartographer.md](./agents/context-cartographer.md) on Claude Opus with [agents/context-scout.md](./agents/context-scout.md) agents on Claude Sonnet. They study the game's code, scenes, prefabs, data assets and string tables (`scripts/build_context_map.py --scan` gives them the facts), **ask the user whatever stays unclear** and write `CONTEXT_MAP.md`. Nothing is translated or judged before the map exists.
3. Hand the map to every later step. Phase 0 continues with the bible and the ledger, Phase 1 is Pass 1 with [agents/game-culturalizer.md](./agents/game-culturalizer.md), Phase 2 is the blind critique with [agents/native-ear-critic.md](./agents/native-ear-critic.md) or the jury (`scripts/jury.py`) and Pass 2, Phase 3 is the automated gate. The full runbook is [references/methodology_and_qa.md](./skills/game-cultural-localization/references/methodology_and_qa.md).
4. Load only the playbook of the active target locale (`references/<locale>.md`).

### B. Working on the plugin itself

1. Read [CHANGELOG.md](./CHANGELOG.md) (newest entries first) and [scripts/CLI_REFERENCE.md](./skills/game-cultural-localization/scripts/CLI_REFERENCE.md).
2. Run the tests before and after every change, on the oldest and a current Python.
   ```bash
   python -m unittest discover tests
   ```
3. Follow the rules below, then add the change to `CHANGELOG.md` under `[Unreleased]`.

## Rules that are never optional

- **Context decides every word.** Never lock a term in a list. One source word takes different target words depending on where the game uses it (*Play* is *Oyna* for a game and *Çal* for music), so meaning comes from `CONTEXT_MAP.md`. `--glossary` of the linter only checks the spelling of proper names.
- **Ask, do not guess.** When a usage, meaning, tone or audience is unclear, ask the user.
- **Blind critique.** The critic and the jury never see the source column. They read the blind slice and the context map, and the map never quotes source lines.
- **API keys.** Keys live only in the environment variables `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` and `DEEPSEEK_API_KEY`. Never write a key into a file, a commit, a log or a message. Scan the outgoing diff for key values before every push.
- **Tests never call a real API.** Use `--dry-run` and the fake provider (`scripts/providers/fake.py`), `GCL_OFFLINE=1` blocks the network.
- **Never write into a game project.** Read it, write results to `loc_work/` or another folder outside it. Shipped files carry no machine paths.
- **Runtime.** Python 3.9 or newer, standard library only. Every CLI exits 0 for clean, 1 for findings and 2 for usage or input errors.
- **House punctuation style.** README files, docs, prompts, generated reports and commit bodies use no semicolons, no en or em dashes and no colon inside or between sentences (`scripts/text_style.py` checks it). Code, inline code and URLs are exempt.
- **Every new tool** appears in the `SKILL.md` map, gets a `CLI_REFERENCE.md` section, a `CHANGELOG.md` line and tests, and its test module is listed in `tests/README.md`. `README.md` and `README_TR.md` change together.
- **Git.** Commit subjects use `feat(<area>): ...`. Ask the user before every push. Never commit `loc_work/`, `langpack/*/local/` or anything holding a key.

## Repository map

```
AGENTS.md, CLAUDE.md        this guide for AI agents
README.md, README_TR.md     the project page for people, in English and in Turkish
rules/AGENTS.md             always on rules for the projects that use the plugin
agents/                     context-cartographer, context-scout, game-culturalizer, native-ear-critic
skills/game-cultural-localization/
  SKILL.md                  entry point of the skill, archetypes, the 8 laws, minimal instructions
  references/               15 locale playbooks, methodology_and_qa.md, transcreation_ledger_guide.md
  scripts/                  CLI tools, providers/ and providers.config.json (models, roles, jury tiers), rules/<locale>.json
  prompts/                  native critic and Pass 2 prompts for 15 locales, literal.md
  langpack/                 sources.manifest.json and the built language packs (local/ never leaves the machine)
tests/                      python -m unittest discover tests
loc_work/                   per project working files, never committed
```

## Models and roles

`scripts/providers.config.json` maps every role to a model. `context_orchestrator` is Claude Opus and `context_agent` is Claude Sonnet for the context map, `pass1` and `pass2` write the translations, `J1`, `J2` and `J3` are the jury tiers with one Anthropic, one Google and one DeepSeek model each. `scripts/providers_check.py --ping` checks every model with the keys of the environment.
