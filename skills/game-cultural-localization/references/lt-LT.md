# Lithuanian (`lt-LT`) Game Localization & Culturalization Playbook

Target feel: **Gyva, šilta šnekamoji lietuvių kalba + tikras žaidėjų žodynas** — ZERO *kanceliarinės kalbos* (Soviet/municipal bureaucracy), ZERO stiff literal English syntax.

## 1. Anti-Translationese Ban List

| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `Atlikti remontą` / `Vykdyti gamybą` | `Sutaisyti` / `Gaminti` | Verbal-noun chain = kanceliarinė kalba. |
| `Fokusuoti` (interact) | `Naudoti` / `Valdyti` | Calque of "Focus". |
| `Šis daiktas negali būti čia padėtas.` | `Čia netinka.` / `Čia šito nepadėsi.` | English passive. |
| `Šioje vietoje jau yra daiktas!` | `Ši vieta jau užimta!` / `Čia jau kažkas padėta!` | |
| `Jūs jau turite šį įrankį!` (in `tu` UI) | `Šį įrankį jau turi!` | Register leak. |
| `Tavo ištvermė per žema!` | `Trūksta jėgų!` / `Pritrūko ištvermės!` | Stat stays `Ištvermė`; toast speaks. |
| `GAUTI DAIKTUS` | `PAIMTI VISKĄ` / `ATSIIMTI` | |
| `Judėti į priekį / Judėti į kairę` | `Pirmyn` / `Kairėn` | Keybinding labels are adverbs. |
| `Perduota į sandėlį` / `Realizuoti rinkoje` | `Nugabenta į sandėlį` / `Parduoti turguje` | *Realizuoti* = accounting. |
| `Siekiant tęsti, paspauskite` | `Norėdami tęsti, paspauskite` / `Spausk, kad tęstum` | *Siekiant* is officialese. |
| `Operacija sėkmingai įvykdyta.` | `Atlikta!` / `Išsaugota.` | System jargon. |
| `išsilaikyti ant vandens` (*stay afloat*) | `išsilaikyti` / `išgyventi` / `nenueiti į dugną` | Lithuanian idiom means literal swimming. |
| `Kosminės nesąmonės!` | `Nesąmonė!` / `Tuščios kalbos!` | Calqued exclamation. |

## 2. Register, Address & Character Voice

| Speaker | Address | Notes |
|---|---|---|
| UI, tutorials, toasts | `tu` (imperative `spausk`, `pasirink`) **or** impersonal infinitive/`Jūs` (`spauskite`) | Lithuanian storefronts and MS/Google UI use `Jūs`; indie/console games use `tu`. Lock one in `LT-LT_BIBLE.md`. |
| A1 Mentor, A2 Rival, A3 Rookie | `tu` | Particles: `na`, `štai`, `visgi`, `juk`, `šiaip ar taip`, `klausyk`, `žinai`. |
| A4 Scientist (colleague) | `tu`; `Jūs` for a formal official | |
| A5 Outlaw / Antagonist | `tu` (contempt) or cold `Jūs` | One form per character. |

* **Capitalization:** `Jūs / Jums / Jūsų` capitalized in letters and formal in-game messages; lowercase `jūs` in spoken dialogue and UI. Decide per text type in the bible.
* **Never mix** `tu` and `Jūs` between the same two characters.
* **Vocative (šauksmininkas):** every address uses the vocative: `Dėde!`, `Mechanike!`, `Jonai!`, `Rūta!`, `Vade!`, `Naujoke!`. Fixed NPC names are declined in the script. A `{playerName}` placeholder **cannot** be declined — never place it in vocative position; restructure: `Sveiki, čia {playerName}`, `Žaidėjas: {playerName}`, or drop the name.
* **Pronoun drop:** drop redundant `tu / aš`; verb endings carry person.
* **Anglicisms:** `lootas`, `skillas`, `questas` exist in gamer slang (A2/A3 dialogue only); UI uses `grobis`, `įgūdis`, `užduotis`, `gamyba`.

## 3. Spoken vs. Literary Tense

N/A — Lithuanian uses the same simple past (`padariau`, `sutaisei`) in speech and prose; the literary feel comes from vocabulary and from heavy participle constructions, not from tense. Avoid **compound tenses with participles** in speech (`esu padaręs`, `buvo sutaisyta`) — they are both bookish and gendered (see §4). Frequentative past (`darydavau`) is natural in reminiscing dialogue (A1 Mentor).

## 4. Player Gender Neutrality

**Advantage:** finite verbs in all tenses (`darai`, `padarei`, `padarysi`, `galėtum`) are gender-neutral. **Trap:** participles, half-participles, adjectives, and nouns are gendered.

| Leaks ✗ | Neutral ✓ |
|---|---|
| `Esi pasiruošęs?` / `pasiruošusi` | `Viskas paruošta?` / `Pradedam?` |
| `Tapai tikru mechaniku.` | `Dabar jau tikrai išmanai šį amatą.` |
| `Sąjungininkas` / `Sąjungos narys` | `Sąjunga` / `Sąjungos dalis` / `Esi su mumis.` |
| `Esi padaręs daug.` | `Daug padarei.` |
| `Pagamindamas reaktorių, sutaupysi laiko.` (`-damas/-dama`) | `Jei pasigaminsi reaktorių, sutaupysi laiko.` |
| `Jūs esate įtrauktas į sąrašą.` | `Įtraukėme jus į sąrašą.` / `Įtraukėme jūsų dirbtuves į sąrašą.` |
| `Buvai pakviestas.` | `Gavai kvietimą.` / `Tave pakvietė.` |
| `Gerbiamas pone` (to player) | `Sveiki` / `Laba diena` |

* **Safe tools:** finite active verbs in any tense, imperative, impersonal passive of the **neuter** form (`Išsaugota`, `Atlikta`, `Paruošta`), nouns of result, conditional with `jei + verb`.
* **Traps:** active participles `-ęs/-usi`, half-participles `-damas/-dama`, passive participles `-tas/-ta` about the player, predicate nouns and adjectives, `ponas/ponia`.
* Named NPCs with known gender use their own forms freely.

## 5. Plurals, Numbers & ICU

Lithuanian has **four** CLDR categories: **one** (1, 21, 31 … ending in 1 but not 11), **few** (2–9, 22–29 … but not 12–19), **many** (fractions), **other** (0, 10–20, 30, 40 … and 11–19).

| Count | Lithuanian | ICU |
|---|---|---|
| 0 | `0 reaktorių` | `other` |
| 1 | `1 reaktorius` | `one` |
| 2 | `2 reaktoriai` | `few` |
| 5 | `5 reaktoriai` | `few` |
| 10 / 11 / 15 / 20 | `10 reaktorių` / `11 reaktorių` / … | `other` |
| 21 | `21 reaktorius` | `one` |
| 22 | `22 reaktoriai` | `few` |
| 25 | `25 reaktoriai` | `few` |
| 1,5 | `1,5 reaktoriaus` | `many` |

```text
{count, plural, one {{count} reaktorius} few {{count} reaktoriai} many {{count} reaktoriaus} other {{count} reaktorių}} sandėlyje
```

* Feminine nouns: `1 dalis / 2 dalys / 10 dalių`; `1 detalė / 2 detalės / 10 detalių`.
* Verbs agree in number: `Liko 1 reaktorius`, `Liko 2 reaktoriai`, `Liko 10 reaktorių` — keep the whole clause inside each branch.
* Without ICU support, avoid the noun: `Reaktoriai: {count}`, `Reaktorių skaičius: {count}`.

## 6. Placeholder & Rich-Text Grammar Traps

* **Case after prepositions:** `iš {0}`, `į {0}`, `su {0}`, `nuo {0}` require genitive/accusative/instrumental; a nominative item name breaks. Insert a declined classifier: `"Detalių gabenimas iš stoties {0} į sandėlį"`, `"Daiktas {0} perkeltas į sandėlį"`, or a colon: `"Perkelta į sandėlį: {0}"`.
* **Vocative placeholder:** never `{playerName}!`; see §2.
* **Adjective agreement:** `Naujas {0}` fails for feminine nouns; use `Naujiena: {0}`.
* **Numerals + noun:** never `{count} reaktorius(-iai)`; use ICU (§5).
* **Rich-text tags wrap whole words:** `<b>reaktoriaus</b>` (ending inside), never `<b>reaktor</b>iaus`; same for `[b]…[/b]` BBCode and Unreal `<>` styles.
* **Engine equivalents:** Unity `{0}`, Unreal `{Name}`, Godot `%s`, ICU, printf `%1$s` — the Lithuanian case lives on the classifier noun, never inside the placeholder.
* **Concatenation:** word order differs (`Atnaujinimo kaina: {0}`); report seams; keep legacy leading/trailing spaces exactly (`--strict-whitespace`).
* **Separate** `Sutartis / Kontraktas` (customer contract) from `Užsakymas` (workstation order) when a game has both.

## 7. Core UI Glossary

Standard Lithuanian UI uses the **infinitive** on buttons (MS/Google/Steam convention); toasts and tutorials use `tu`-imperative or impersonal forms per the bible.

| EN | lt-LT | Note |
|---|---|---|
| Save / Load | `Išsaugoti` / `Įkelti` | |
| Quit | `Išeiti` · `Baigti žaidimą` | |
| Settings / Options | `Nustatymai` / `Parinktys` | |
| OK / Confirm | `Gerai` / `Patvirtinti` | |
| Cancel / Back | `Atšaukti` / `Atgal` | |
| Continue / Resume | `Tęsti` / `Tęsti` (`Pratęsti` rare) | |
| New Game | `Naujas žaidimas` | |
| Apply | `Taikyti` | MS standard |
| Delete | `Ištrinti` (`Šalinti`) | |
| Yes / No | `Taip` / `Ne` | |
| Pause | `Pauzė` | |
| Retry / Skip | `Bandyti dar kartą` / `Praleisti` | |
| Inventory / Equip | `Inventorius` / `Apsiginkluoti` (`Užsidėti` for wearables) | |
| Craft / Upgrade | `Gaminti` / `Tobulinti` (`Atnaujinti`) | tab: `Gamyba` |
| Level / Health / Stamina / Damage | `Lygis` / `Gyvybė` (`Sveikata`) / `Ištvermė` / `Žala` | |
| Buy / Sell | `Pirkti` / `Parduoti` | |
| Take All | `Paimti viską` | |

* Capitalization: sentence case (`Naujas žaidimas`), never English Title Case; ALL CAPS only if the engine applies it. Typical limits: button 12–14, tab 10, badge 6.

## 8. Typography, Numbers & Formatting

* **Quotes:** `„…“` (low opening, high-left closing — same shape as German); inner `‚…‘`. `"…"` is wrong in final text.
* **Numbers:** `1 234,56` (space thousands, comma decimal); percent with space `40 %`.
* **Currency:** `1 234,56 €` (symbol after, with space); `Eur` in formal text.
* **Date/time:** ISO **`2026-11-26`** is the Lithuanian standard (also `2026 m. lapkričio 26 d.`); time `14:30`.
* **Dashes:** dialogue and range dash `–` (en dash, spaced); hyphen in compounds; ellipsis `…`.
* **Capitalization:** months, weekdays, nationalities lowercase; sentence case in UI.
* **Diacritics in caps:** keep `Ą Č Ę Ė Į Š Ų Ū Ž`; never strip them (`IŠSAUGOTI`, not `ISSAUGOTI`).
* **Line breaks:** `U+00A0` after one-letter prepositions and conjunctions (`į`, `iš`, `su`, `ir`, `o`) and between number and unit.

## 9. Text Expansion & UI Fit

* **Typical expansion from en:** +20–30 %; short strings more (`APPLY` → `TAIKYTI`, `RETRY` → `BANDYTI DAR KARTĄ`, `SETTINGS` → `NUSTATYMAI`).
* **Shortening strategies:** drop objects (`Išsaugoti žaidimą` → `Išsaugoti`), nouns on tabs (`Gamyba`), accepted abbreviations (`min.`, `sek.`, `lyg.`), shorter synonyms (`Bandyti dar kartą` → `Kartoti` where design allows).
* `ui_expansion_checker.py --locale lt-LT` uses the lt factor; keep `max_chars` metadata current.

## 10. Ratings, Legal & Sensitive Content

* **Rating body:** **PEGI** (no national board). Tiers 3/7/12/16/18.
* **Profanity:** Lithuanian gamers accept mild swearing (`po velnių`, `velniop`) at PEGI 12–16; strong Russian-origin vulgarisms (`blet`, `nachui`) only at PEGI 18 and only if the product's tone allows — they carry a strong class/regional signal.
* **Sensitive:** Soviet and Nazi symbols are **banned** in public display (Law on Meetings, 2008 amendment — hammer-and-sickle, swastika, anthem fragments); Soviet occupation and deportations are a solemn topic; Lithuanian–Russian and Lithuanian–Polish history; religion (Catholic majority). Flag in the ledger with `[sensitive]`.
* **Language law:** the State Language Inspectorate expects correct Lithuanian in commercial products; avoid untranslated English UI where a Lithuanian term exists.
* **Alcohol:** strict advertising law; keep real brands out of fiction.

## 11. Golden Voice Anchors (A1–A5)

Each pair keeps the **same meaning**; only the register changes. Generic roles, no project names.

1. **A1 Mentor / Patyręs mechanikas** (`tu`, neutralu lyties atžvilgiu)
   * **✗ Sausai:** "Pradėk nuo turimų medžiagų perdirbimo, siekiant atkurti dirbtuvių veiklą, ir aš perduosiu tau sutartis."
   * **✓ Gyvai:** "Pradėk nuo to, ką pavyks išpešti iš laužo, ir vėl pastatyk dirbtuves ant kojų. Kai viskas užsisuks, numesiu tau porą savo sutarčių."
2. **A2 Hotshot Rival / Lenktynininkas** (`tu`; NPC, kurio lytis žinoma)
   * **✗ Sausai:** "Kritikai teigia, kad mano gebėjimai sumenko, o tai visiškai neatitinka tikrovės. Sutaisyk transporto priemonę kuo greičiau."
   * **✓ Gyvai:** "Visi mala liežuviais, kad nebeturiu parako. Nesąmonė. Sutvarkyk man mašiną kuo greičiau – pakyla mano."
3. **A3 Rookie / Naujokas** (`tu`, trumpi sakiniai)
   * **✗ Sausai:** "Bandžiau užsandarinti nuotėkį naudodamas pramoninį glaistą, tačiau sandarinimas nedelsiant sugedo pakilimo metu."
   * **✓ Gyvai:** "Bandžiau užlipdyti skylę pramoniniu glaistu, bet vos pakilom, glaistas apsipylė dūmais ir nusilupo."
4. **A4 Scientist / Inžinierė** (`tu` tarp kolegų)
   * **✗ Sausai:** "Generatoriaus išėjimo galia dėl nepakankamo aušinimo sumažėjo iki keturiasdešimties procentų nominalios vertės."
   * **✓ Gyvai:** "Generatorius sukasi tik 40 % – aušinimas nespėja. Pirma pakeisk ventiliatorių, tada pamatuosim iš naujo."
5. **A5 Outlaw / Antagonistas** (šaltai, trumpai, be žaidėjo lyties)
   * **✗ Sausai:** "Tęsiant veiklą šioje teritorijoje, tau teks susidurti su neigiamomis pasekmėmis."
   * **✓ Gyvai:** "Dar kartą čia pasirodysi – baigsis blogai. Paskutinis įspėjimas."

## 12. Linter Coverage Note

`lqa_linter.py --locale lt-LT` currently catches: `fokusuoti` (ERR), `atlikti remontą / vykdyti gamybą` (WARN), `negali būti` (WARN).

### Suggested linter patterns

| Severity | Pattern | Message |
|---|---|---|
| ERR | `\b(?:iš\|į\|su\|nuo\|prie\|ant\|be\|dėl)\s+\{\w+\}` | preposition directly before placeholder (case trap) |
| ERR | `\{\w+\}\s*\(-\w+\)` | `(-iai)`-style optional plural: use ICU |
| WARN | `\b\w+(?:damas\|dama)\b` in `[player]`-tagged strings | half-participle reveals gender |
| WARN | `\b(?:esi\|esate\|buvai\|buvote)\s+\w+(?:ęs\|usi\|tas\|ta)\b` in `[player]`-tagged strings | participle predicate reveals gender |
| WARN | `\b(?:siekiant\|vykdyti\|atlikti\|realizuoti\|įvykdyt\w*)\b` | kanceliarinė kalba |
| WARN | `\b(?:pone\|ponia\|gerbiamas\|gerbiama)\b` in `[player]`-tagged strings | gendered formal address |
| WARN | `\bišsilaikyti ant vandens\b` | *stay afloat* calque |
| WARN | `\bkosmin\w+ nesąmon\w+\b` | calqued exclamation |
| WARN | `\d+%` (no space) | Lithuanian percent needs `40 %` |
| WARN | `\b\d{1,2}[./]\d{1,2}[./]\d{4}\b` | non-ISO date; use `YYYY-MM-DD` |
| WARN | `\b(?:Išsaugok\|Įkelk\|Išeik\|Taikyk)\b` in button keys | imperative on button; project uses infinitive |
