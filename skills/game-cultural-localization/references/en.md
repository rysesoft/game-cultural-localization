# English (`en`) Source-Polish & Internationalization Playbook

Use this playbook when authoring, auditing, or polishing the **source English** of a game (UI, tutorials, toasts, items, lore, dialogue) before or alongside localization into the 14 target locales. Clean source saves every downstream language the same bug fourteen times.

## 1. Anti-Translationese Ban List

In the source language the enemy is not translationese but **"developer placeholder English"**. Stiff, abstract, manual-style strings written by engineers in a hurry. Replace them before they are frozen.

| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `In order to proceed with the operation, utilize the panel.` | `Use the panel to get started.` | `in order to`, `utilize`, `operation` are paperwork words. Nobody says them. |
| `Item placement failed in current area.` | `That doesn't fit here.` | Toasts are spoken feedback, not log lines. |
| `An item is already located here!` | `This spot's already taken!` | Passive "is located" reads like a police report. |
| `Insufficient stamina to perform this action.` | `Not enough stamina!` | Short, direct, immediate. |
| `Please note that the order cannot be cancelled.` | `You can't cancel this order.` | `Please note that` is filler. Players never read it. |
| `Prior to upgrading, cancel the active order.` | `Cancel the active order before you upgrade.` | `prior to` -> `before`. Verb first. |
| `You have acquired 3 item(s).` | ICU plural. `You got {count, plural, one {# item} other {# items}}.` | `item(s)` is unlocalizable in every target language. |
| `Acquire` / `Obtain` / `Commence` | `Get` / `Take` / `Start` | Latinate verbs become bureaucratese in every target. |
| `It is not possible to` / `is unable to` | `can't` | Contractions are the default register of games. |
| `Lorem ipsum` / `TODO text` / `TBD` / `XXX` | Real final copy | Placeholder text leaks into builds and into translation memories. |

## 2. Register, Address & Character Voice

* **Contractions define warmth.** Mentors, rivals, teens, and everyday people use `don't`, `can't`, `would've`, `it's`, `you'll`. Reserve uncontracted speech (`I did not`, `it is not`) for guarded officials, cold antagonists, or stoic masterminds, so the contrast means something.
* **Spoken rhythm.** Short punchy sentences, fragments (`Good enough for now.`, `Lesson learned.`), concrete workshop verbs (`patch up`, `rig up`, `strip out`, `slap a quick fix on`) rather than abstract nouns.
* **Second person is universal.** UI, tutorials, and toasts address the player as `you`. Never `the user`, `the player`, or passive agentless constructions.
* **Vocatives (how NPCs call the player).** `kid`, `pal`, `friend`, `rookie`, `boss`, `captain` are gender-neutral and must be tagged `[player-addr, keep neutral]` in the context field. Avoid `man`, `dude`, `bro`, `sir/ma'am`, `boy`, `son`, `girl`, `lady` for an unspecified-gender player. If an NPC voice *needs* a vocative, pick one from the neutral list.
* **Register metadata.** Every dialogue string carries a `speaker` field and the speaker's archetype (A1 to A5, see §11). Target languages derive T/V address (`du/Sie`, `tu/vous`, `sen/siz`, `ты/вы`) from this metadata, not from guesswork.

## 3. Spoken vs. Literary Tense

English hides a distinction that most target languages must make explicit. Help them with context notes.

* **Simple past in dialogue and letters** (`He wrecked everything and ran.`, `I tried a test flight.`) is fine in English, but it will become *Perfekt / passé composé / passato prossimo / pretérito perfecto* in spoken-register targets. Tag the string `register: spoken` so translators do not reach for a literary tense.
* **Lore, codex, and third-person narration** may use narrative past deliberately. Tag `register: narrative` so targets may use *Präteritum / passé simple / passato remoto* where that is natural.
* **Hearsay vs. witnessed.** Turkish (-di / -miş), and partly Bulgarian/Balkan languages, must choose. When an NPC reports something they did not see (`I hear the VP contacted you.`), say so in the context note (`speaker reports hearsay`).
* **Recent vs. remote past.** Spanish (Spain) picks *he hecho* vs *hice* by time distance. Write `just now / today` into the line or the note when relevant.

## 4. Player Gender Neutrality

The player's gender is unknown unless the design doc says otherwise. Source strings must make neutrality *possible* for every target.

* **Flag every string that addresses or describes the player** with the context tag `[player]`. Target languages with gendered past tense (pl, ru), participles (lt, fr, it, es, pt), or titles (de `Herr/Frau`) rewrite these with their playbook strategies.
* **Never write gendered descriptions of the player** (`a true craftsman`, `good man`, `our best guy`). Use `a real pro`, `good work`, `our best`.
* **Ships, vehicles, and machines as "she".** `Patch her up` is idiomatic English but needs a decision in every target. Record each such string in the transcreation ledger with `ship-as-she: target may use a neutral nickname or "it"`.
* **Named NPCs may be gendered freely** (`the Rival` can say `I've lost my edge` as a man or woman). Give the NPC's gender in the speaker metadata so targets conjugate correctly.
* **Avoid `he/she`, `(s)he`, `him/her` hacks.** Rewrite in plural or second person.

## 5. Plurals, Numbers & ICU

English has two CLDR plural categories, **one** and **other**. Most targets have three or four. Write plurals so that targets can expand them.

| Count | English | Rule |
|---|---|---|
| 0 | 0 items | `other` (English uses the plural for zero) |
| 1 | 1 item | `one` |
| 2 | 2 items | `other` |
| 5 / 21 / 22 / 25 | 5 items / 21 items / 22 items / 25 items | `other` (targets like pl/ru/lt split 21 vs 22 vs 25 here) |

* **Always use ICU MessageFormat for any count**, never `item(s)`, never `{0} item` + `s` concatenation.

```text
You crafted {count, plural, =0 {nothing} one {# item} other {# items}}.
{count, plural, one {{count} reactor is} other {{count} reactors are}} in storage.
```

* Provide **all four categories as room** in the string table schema (`one`, `few`, `many`, `other`) even though the English file fills only `one` and `other`.
* Spell out small numbers in dialogue (`a couple of days`, `three tries`), use digits in UI and stats (`3 tries left`).
* Never bake a number into a sentence as a separate key (`"Reactors: "` + `3`). Use a placeholder.

## 6. Placeholder & Rich-Text Grammar Traps

* **String ID management.** Keys are stable, descriptive, and scoped. `ui.inventory.button.equip`, `dlg.mentor.intro.03`, `toast.storage.slot_taken`. Never reuse a key for a different meaning. Never let the key be the only context.
* **Named placeholders.** Prefer `{itemName}`, `{count}`, `{stationName}` over `{0}`, `{1}`. A named placeholder tells the translator the grammatical type (noun phrase, number, proper name), which decides article, case, and suffix choices in de/pl/ru/lt/tr/fr/es/it/pt.
* **Engine-neutral placeholder forms.** The rules in this suite apply to every syntax. Unity/.NET `{0}` / `{itemName}` and `<b>`, `<color=#fff>`, `<sprite=1>`. Unreal `{Name}`, `|hpp(...)` plural helpers and `<>` styles. Godot `%s` / `%d` and `[b]…[/b]` BBCode. ICU `{count, plural, …}`. Printf `%1$s`. Python-style `{name}`. Record the engine's syntax once in the localization bible. Never hand-translate placeholder names, never reorder printf tokens without positional indices (`%1$s`), and treat BBCode/markup exactly like XML tags for parity checks.
* **No runtime concatenation for new strings.** `"Move " + itemName + " to Storage"` is forbidden. Word order differs in every target (`{itemName} Depoya taşınıyor`). Use one full sentence with placeholders. For legacy seams that cannot be removed, document the exact leading/trailing spaces and the slot type (`noun phrase`, `verb phrase`, `status adjective`) in the context field, and run `lqa_linter.py --strict-whitespace`.
* **Keep articles and prepositions out of the placeholder.** Write `Move {itemName} to {targetName}`, not `Move the {itemName}`. Targets need to choose `the/a/l'/der/die/das` themselves. If a noun phrase truly needs a category word for grammar, give it in the source. `the {itemName} item`.
* **Rich-text tags wrap whole words.** `<b>{itemName}</b>` is fine. `<b>Reac</b>tor` is not. Never split a word or a placeholder across tags, and never nest `<color>` inside a placeholder value.
* **Context notes are mandatory for.** Overloaded verbs (`APPLY` settings vs `APPLY` for a loan), single words (`Load` verb vs noun, `Close` verb vs adjective), strings shown in ALL CAPS by the engine, strings with max length, and any string addressing the player.
* **Do-Not-Translate list.** Maintain `dnt.txt` with brand names, placeholder tokens, and key names. Link it from the localization bible.

## 7. Core UI Glossary

Pick **one** English term per concept and never alternate between synonyms across screens. This is source polish for English only. Target languages choose their words per place from the project's context map, never by locking a list.

| Concept | Canonical source | Avoid | Note |
|---|---|---|---|
| Save / Load | Save · Load | Store · Restore | `Load` also means "cargo": add `verb` in context |
| Quit | Quit | Exit · Leave | `Quit to Desktop` vs `Quit to Menu` |
| Settings | Settings | Options · Preferences · Config | pick one for the whole product |
| OK / Confirm | Confirm (dialogs) · OK (system) | Accept · Proceed | |
| Cancel / Back | Cancel · Back | Abort · Return | `Cancel` ends an action. `Back` navigates |
| Continue / Resume | Continue (menu) · Resume (pause) | Proceed | |
| New Game | New Game | Start Game · Begin | |
| Apply | Apply | Set · Commit | mark settings vs loan in context |
| Delete | Delete | Remove · Erase | `Remove` only for equipment slots |
| Yes / No | Yes · No | Okay · Nope | |
| Pause | Pause | Hold | |
| Retry / Skip | Retry · Skip | Try again · Pass | |
| Inventory / Equip | Inventory · Equip | Bag · Wear | |
| Craft / Upgrade | Craft · Upgrade | Make · Improve | |
| Level / Health / Stamina / Damage | Level · Health · Stamina · Damage | Tier · HP · Energy · DMG (unless abbreviated by design) | abbreviations need their own keys |
| Buy / Sell | Buy · Sell | Purchase · Vend | |

* **Button form.** Imperative verb or noun, 1 to 2 words. Source is written in **Title Case** for buttons and **sentence case** for everything else. The engine applies ALL CAPS when a style demands it. If ALL CAPS is baked into the source string, say so in context (targets with `İ/ı` or `ß/SS` rules depend on it).
* **Character budget.** Every button/tab/badge key carries `max_chars` metadata (typical button 12, tab 10, badge 6). Without it, `ui_expansion_checker.py` cannot judge the target.

## 8. Typography, Numbers & Formatting

* **Quotes & apostrophes.** Use typographic `“ ”` and `’` in final copy, or straight quotes consistently if the font lacks curly glyphs. Never mix. Nested quotes. `‘ ’`.
* **Ellipsis.** One character `…`, never `...`. **Dash.** Em dash `—` without spaces (US) or spaced en dash `–` (UK). Pick one.
* **Numbers.** `1,234.56` (en-US). Never hard-code separators into strings that targets will reformat. Pass numbers as `{count, number}` placeholders.
* **Dates/times.** Never bake `11/26/2026` into a string. Use `{date, date, medium}` / `{time, time, short}` placeholders so targets get `26.11.2026`, `2026-11-26`, `14:30`.
* **Currency.** `{amount, number, currency}` placeholder. Never `$` + number.
* **Percent.** `50%` without a space in English. Targets reorder (`%50` tr, `50 %` fr/de). Use `{pct, number, percent}`.
* **Capitalization.** Sentence case for toasts and tutorials. Title Case only for button labels and proper names. No ALL CAPS in dialogue.
* **Line breaks.** No manual `\n` inside sentences. Let the engine wrap. Mark unbreakable spans (`Level 3`) with `U+00A0`.

## 9. Text Expansion & UI Fit

English is usually the **shortest** language in the table. Budget for growth at source time.

* **Typical expansion from en.** De +30 to 35 %, fr/es/it/pt +20 to 30 %, pl/lt/ru +15 to 30 %, tr +10 to 25 %, ja/zh −10 to 30 % in characters but wider glyphs. Short strings expand the most (`ON` -> `EINGESCHALTET`).
* **Design UI for the longest locale**, not for English. Buttons should fit 2× the English width or support auto-shrink.
* **Pseudo-localization gate.** Before handing off, run a pseudo-locale (`[!!! Ŝàvé Ġàmé !!!]`, 35 % padding) through the UI. Clipping found here is a source/engine bug, not a translation bug.
* **Abbreviation policy.** If the source abbreviates (`DMG`, `HP`, `LVL`), add a separate full-form key. Targets may not have a standard abbreviation.
* **Tool.** `ui_expansion_checker.py --locale <loc>` compares each target against its locale factor. Keep `max_chars` metadata current so the checker reports real overflow.

## 10. Ratings, Legal & Sensitive Content

Source writers decide what the whole product can be rated. Write rating-aware.

* **Know the target rating** (ESRB E/E10+/T/M, PEGI 3/7/12/16/18) before writing profanity, gore, drug, or gambling references. Tag strings that are rating-sensitive (`[rating: profanity-strong]`) so targets can match the tier (and so RU/CN/DE constraints can be checked).
* **Profanity tiers.** Mild (`damn`, `hell`), moderate (`crap`, `bastard`), strong (`f-word`). Targets map to their own tier, never word-for-word.
* **Legal and cultural flags to record in the ledger.** Real-brand names, real political figures, religious texts, flags and maps, Nazi/Soviet symbolism (DE §86a StGB, LT ban on Soviet symbols), LGBTQ+ content (RU 2022 law), depictions of China's borders and politics, alcohol/tobacco in minors' content, loot boxes (BE/NL gambling law).
* **Accessibility.** No meaning carried by color alone in text (`the red button`), screen-reader friendly symbols (`+5` -> `plus five` in alt text).
* **Licensing.** Quoted lyrics, film lines, and memes need clearance. Log them in the transcreation ledger (`pop-culture nod`) so targets can substitute legally.

## 11. Golden Voice Anchors (A1 to A5)

Five project-independent archetypes. Each pair keeps the **same meaning**. Only the register changes. Targets calibrate their own anchors against these.

1. **A1 Mentor / Veteran** (warm, senior, gives advice)
   * **✗ Stiff.** "Begin by salvaging available materials in order to restore workshop operations, and I will transfer contracts to you."
   * **✓ Living.** "Start with whatever you can salvage and get the place running again. Do that, and I'll send a few of my contracts your way."
2. **A2 Hotshot Rival** (cocky, fast, competitive)
   * **✗ Stiff.** "Critics state that my abilities have declined, which is completely false. Repair the vehicle rapidly."
   * **✓ Living.** "People keep saying I've lost my edge. Total hogwash. Patch the rig up quick — I'm taking that podium back."
3. **A3 Rookie / Teen** (excited, everyday slang, short sentences)
   * **✗ Stiff.** "I attempted to seal the leak utilizing industrial sealant; however, it failed immediately upon liftoff."
   * **✓ Living.** "I tried patching the leak with industrial sealant, and the second we lifted off, it just smoked and peeled right off."
4. **A4 Scientist / Engineer** (precise, technical, but spoken)
   * **✗ Stiff.** "The generator's output has decreased to forty percent of nominal value due to insufficient cooling."
   * **✓ Living.** "Generator's down to 40% — cooling can't keep up. Swap the fan first, then we'll measure again."
5. **A5 Outlaw / Antagonist** (threatening, cold, short)
   * **✗ Stiff.** "Should you continue your activities in this area, you will encounter negative consequences."
   * **✓ Living.** "Keep working this area and it ends badly. Last warning."

## 12. Linter Coverage Note

`lqa_linter.py --locale en` runs a **minimal source-polish set** (not a translationese set). Placeholder/tag parity is skipped because there is no source to compare against. The rules below target developer-placeholder English and unlocalizable constructs.

### Suggested linter patterns

| Severity | Pattern | Message |
|---|---|---|
| ERR | `\(s\)\b` | `item(s)`-style optional plural. Use ICU plural |
| ERR | `\b(?:Lorem ipsum\|TODO\|TBD\|FIXME\|XXX)\b` | placeholder text in source |
| WARN | `^\s\|\s$` (value starts or ends with whitespace) | concatenation seam. Document slot type. Enforced by `--strict-whitespace` |
| WARN | `\bin order to\b` | filler. Use `to` |
| WARN | `\b(?:utilize\|utilise\|commence\|acquire\|obtain)\b` | Latinate verb. Use `use / start / get` |
| WARN | `\bPlease note that\b` | filler |
| WARN | `\bprior to\b` | use `before` |
| WARN | `\bis (?:unable\|not possible) to\b` | use `can't` |
| WARN | `\b(?:he/she\|\(s\)he\|him/her\|his/her)\b` | pronoun hack. Rewrite neutral |
| WARN | `\b(?:dude\|bro\|sir\|ma'am\|boy\|son\|girl)\b` in `[player]`-tagged strings | gendered vocative toward the player |
| WARN | `\d+%` without placeholder | hard-coded percent. Use `{pct, number, percent}` |
