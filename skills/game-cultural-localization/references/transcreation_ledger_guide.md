# Transcreation, Pop-Culture & Narrative Nuance Ledger Guide

Literal translation destroys jokes, famous quotes, plot twists, hidden plurals, and concatenated UI templates. Before starting any locale on any game, create a project **Transcreation & Nuance Ledger**. It is a machine-readable table (CSV or JSON) that the culturalizer reads in Pass 1 and Pass 2 and that the bible (`<LOCALE>_BIBLE.md`) links to. The ledger is project-specific; this guide only defines its shape and the rules per row type. Examples below use generic roles and items (the Mentor, the Rival, `{itemName}`, a generator) — replace them with your project's cast and glossary.

---

## 1. Ledger Schema

File: `transcreation_ledger.csv` (UTF-8, header row) or `transcreation_ledger.json` (list of objects with the same field names). One row per key (or per key group) that needs a non-literal decision.

| Column | Required | Meaning |
|---|---|---|
| `key` | yes | String-table key (or `group:<name>` when a rule covers several keys, e.g. a whole letter). |
| `source` | yes | The source text or the relevant fragment. |
| `type` | yes | One of `pop-culture` · `idiom` · `spoiler-guard` · `plurality` · `concat`. |
| `decision` | yes | The locale-independent rule: what every translator must do (keep English, transcreate by function, delay the reveal word, treat as 3 items, keep trailing space…). |
| `rationale` | yes | Why (official dub exists, joke relies on X, code appends Y). Include the verification source URL for `pop-culture`. |
| `<locale>` columns | one per target locale, optional | The approved rendering or locale-specific note (`de-DE`, `fr`, `ja-JP`, …). Empty = not decided yet. |
| `status` | yes | `open` · `verified` · `locked`. Only `locked` rows are enforced; `open` rows must be closed before Phase 3. |
| `owner`, `updated` | recommended | Who decided, ISO date. |

### CSV example

```csv
key,source,type,decision,rationale,de-DE,fr,ja-JP,status,owner,updated
ach.speed_demon.title,"I am speed!",pop-culture,"Use the official local dub line of the Cars quote if one is attested; otherwise transcreate the boast, never translate literally.","Famous Lightning McQueen line; literal renderings sound robotic. Verify dub per locale (see §2).","ICH BIN SPEED! (verify against the German dub before locking)","Je suis la vitesse ! (verify)","僕は速い！ (unverified fan rendering; verify before locking)",open,l10n-lead,2026-11-26
dlg.rival.taunt_03,"That's total solar-wash!",idiom,"Translate by emotional function (= nonsense / hogwash) with an optional sci-fi twist; never literal.","In-world slang; the joke is the 'wash' pun, not the word solar.","Was für ein kosmischer Schwachsinn!","C'est du vent cosmique !","そんなの宇宙規模のデタラメだ！",locked,l10n-lead,2026-11-26
group:letter_antagonist_02,"A weapon, the kind that disintegrates whatever it touches!!!",spoiler-guard,"Do not use the word 'weapon' earlier in this letter; the reveal sentence must start with the target word for 'weapon'; keep !!! (full-width in CJK).","Delayed reveal; the player must not guess the object before this line.","Eine Waffe, …!!!","Une arme, …!!!","武器だ——触れたものを消し去る武器！！！",locked,narrative,2026-11-26
quest.find_parts.desc,"Find something to hide me.",plurality,"'something' = 3 separate items in the quest item list; translate as plural / countable where the language requires it.","Quest data lists 3 items; singular sounds like one object.","ein paar Dinge","de quoi me cacher (pluriel)","隠れるための道具を集める（複数）",locked,design,2026-11-26
ui.status.assigned_suffix," is assigned.",concat,"Keep the leading space; code builds <name> + this key; the subject is any worker or item, so use a construction that does not inflect for gender or number.","Concatenation seam found in Phase 0 scan.",", zugewiesen"," : affecté·e → avoid; use ' : en poste'","は配置済み",locked,eng,2026-11-26
```

### JSON equivalent (one row)

```json
{
  "key": "dlg.rival.taunt_03",
  "source": "That's total solar-wash!",
  "type": "idiom",
  "decision": "Translate by emotional function (= nonsense / hogwash) with an optional sci-fi twist; never literal.",
  "rationale": "In-world slang; the joke is the 'wash' pun, not the word solar.",
  "de-DE": "Was für ein kosmischer Schwachsinn!",
  "fr": "C'est du vent cosmique !",
  "ja-JP": "そんなの宇宙規模のデタラメだ！",
  "status": "locked",
  "owner": "l10n-lead",
  "updated": "2026-11-26"
}
```

Rules for every row type follow.

---

## 2. `pop-culture` — Quotes, Memes & Homages (research official local dubs)

Whenever a quest title, achievement, or graffiti nods to a famous movie, anime, meme, or game:

* **Never translate it word-for-word.** Search the web for how the official dub or subtitles in that country rendered the iconic line and record the source URL in `rationale`. If no official rendering can be attested, mark the cell **"unverified"** and transcreate the *function* (a boast, a threat, a catchphrase) in natural speech; never lock an unverified quote.
* *Example — Lightning McQueen's `"I am speed!"` (Cars):* the German literal *"Ich bin Geschwindigkeit!"* is robotic; the widely cited dub line is **"ICH BIN SPEED!"**, and fan transcripts of the Japanese release give **「僕は速い！」** — both are **unverified fan renderings** until someone checks the actual release. The `ja-JP` playbook's own natural boast (e.g. a 俺-register line such as 「最速は俺だ！」) is the fallback when the dub cannot be confirmed; do not invent a "dub line".
* *Example — memes such as `"This is Fine"`:* check whether gamers in that locale keep the English meme text as-is (common in `de-DE`, `pl-PL`, `tr-TR`, `ja-JP` internet culture) or use an established local meme name; record the decision, because mixed handling across achievements looks like a bug.

---

## 3. `idiom` — Idioms, In-World Slang & Metaphors

Map fictional sci-fi/fantasy slang by **emotional function**, not dictionary words:

* *"That's total solar-wash!"* (= "hogwash / complete nonsense") → punchy local idiom plus optional sci-fi twist (*"Was für ein kosmischer Schwachsinn!"*, *"C'est du vent cosmique !"*, *"¡Menuda chorrada cósmica!"*), never literal "solar laundry". Each locale should pick its **own** idiom; do not translate one master rendering into 14 languages.
* *"Duct-tape fix"* (= improvised temporary bodge) → each culture's beloved workshop word. All 15 locales:

| Locale | Rendering | Note |
|---|---|---|
| `en` | duct-tape fix / bodge / jury-rig | source polish: keep one term per project |
| `tr-TR` | derme çatma yama / idare eder çözüm | colloquial; *geçici çözüm* is too formal |
| `de-DE` | Notlösung / Pfusch / Klebeband-Provisorium | *Pfusch* when the speaker is dismissive |
| `fr` | bricolage de fortune / rafistolage / système D | *système D* for a proud improviser |
| `es-ES` | chapuza / apaño | *apaño* is neutral, *chapuza* is pejorative |
| `it-IT` | rattoppo / soluzione arrangiata / all'italiana | *arrangiarsi* register |
| `pt-BR` | gambiarra | iconic, always understood |
| `pt-PT` | desenrascanço / remendo | *gambiarra* is a pt-BR leak |
| `pl-PL` | prowizorka / na taśmę | *na taśmę* literal but idiomatic in workshops |
| `lt-LT` | laikinas lopas / sulipdyta ant greitųjų | *lopas* = patch; avoid calque *lipni juosta* |
| `ru-RU` | на соплях / на скорую руку / костыль | *костыль* for software/mechanic jokes |
| `ja-JP` | 応急処置 / 間に合わせ / その場しのぎ | *応急処置* neutral, *その場しのぎ* dismissive |
| `ko-KR` | 임시방편 / 땜질 / 땜빵 | *땜빵* is slang (dialogue only, not UI) |
| `zh-CN` | 凑合 / 土办法 / 临时凑合 | *土办法* for homemade fixes |
| `zh-Hant` | 土法煉鋼 / 將就 / 權宜之計 | *土法煉鋼* idiomatic in Taiwan |

---

## 4. `spoiler-guard` — Plot-Twist & Spoiler Guards

Document any narrative reveal where wording order matters.

* *Delayed reveal rule:* if a character secretly built something for months and the shock sentence reveals *"A weapon, the kind that disintegrates whatever it touches!!!"*:
  * Never use the word *weapon* in earlier sentences of that letter (use *"something built in secret"*).
  * Start the reveal sentence with the target word for *weapon* wherever the language allows; in SOV languages (`ja-JP`, `ko-KR`) front the noun with a topic / dash construction (「武器だ——」, 「무기였어 —」) rather than forcing English word order.
  * Preserve the dramatic punctuation: `!!!` in Latin/Cyrillic scripts, full-width `！！！` in `ja-JP` / `zh-CN` / `zh-Hant` (half-width in `ko-KR`).

---

## 5. `plurality` — Hidden Plurality, Gender & Pronoun Facts

English hides gender and sometimes number (*you*, *my mechanic*, *their pilot*, *cousins*, *something to hide me*):

* Record the **true gender** of every named or unnamed third-person NPC from the full story context (is the rival male or female; does *cousins* include both genders; is *something* one item or three in the quest's item list).
* Record that the **player's gender is unspecified** so every locale applies its section-4 gender-neutrality rules consistently, including the player's **own voice**: Japanese first-person pronoun policy (私 vs 俺/あたし), Korean kinship address (형/오빠/누나/언니 forbidden toward the player), Chinese written 他/她 (use the name or 你), Romance/Slavic past participles and adjectives.
* Record speaker → archetype (A1–A5) mappings here or in the bible so plural/gender decisions stay consistent across batches.

---

## 6. `concat` — Engine Concatenation & Shared-Key Constraints

Document every key touched by code concatenation (found in the Phase 0 scan):

* Leading/trailing spaces (`' is assigned.'`, `'Total: '`) — the linter's `--strict-whitespace` enforces parity.
* Keys where code appends `" : "` or `.` automatically (forbid trailing `:` / `.` in translations).
* Prefix templates like `"x3 " + status + " " + itemName` — require short, gender- and case-invariant status badges; CJK locales decide `×3` vs full-width once and record it here.
* Placeholder-adjacent grammar: Korean particles (`{0}을/를` → engine particle support such as Unreal `|hpp` or a fixed-particle construction; see `ko-KR.md` §6), Romance articles/elision before `{0}` (`l'{0}`, `un/una`), Slavic/Baltic case after numbers, CJK counters (助数詞 / 量词 / 단위명사).
* Shared keys displayed on multiple object types (never name one specific object inside a shared key).
* ICU plural slots: when the source uses `{count, plural, one {…} other {…}}`, record which locales need extra categories (`few`, `many`) so the engine table gains them before Pass 1.

The ledger is reviewed at Gate 0 (all `concat` rows exist), Gate 2 (no `open` rows for the batch), and Gate 3 (every `locked` row's rendering appears in the final file — spot-check with the linter's `--glossary` by copying locked single-term rows into `glossary.csv`).
