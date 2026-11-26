# German (`de-DE`) Game Localization & Culturalization Playbook

Target feel. **Lebendiges Alltagsdeutsch & echtes Spieler-Deutsch**, ZERO *Übersetzungsdeutsch*, ZERO *Beamtendeutsch*, ZERO novelistic *Präteritum* in personal speech.

## 1. Anti-Translationese Ban List

| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `Fokussieren` (interact prompt) | `Benutzen` / `Bedienen` | Mistranslated "Focus". Germans never "fokussieren" a terminal. |
| `KONSTRUIEREN` (build an item) | `BAUEN` / `FERTIGEN` | *Konstruieren* = CAD design, not crafting. |
| `Vorwärts bewegen` / `Nach links bewegen` | `Vorwärts` / `Nach links` | Keybinding labels are nouns/adverbs. |
| `GEGENSTÄNDE ENTNEHMEN` | `ALLES NEHMEN` / `ABHOLEN` | *Entnehmen* is pharmacy/bank language. |
| `Hier befindet sich bereits ein Gegenstand!` | `Der Platz ist schon belegt!` / `Hier liegt schon was!` | *Befindet sich* is a police report. |
| `Dieser Gegenstand kann hier nicht platziert werden.` | `Das passt hier nicht hin.` | Passive + modal = appliance manual. |
| `Du besitzt dieses Werkzeug bereits!` | `Das Werkzeug hast du schon!` | *Besitzen* is notary German. |
| `Deine Ausdauer ist zu niedrig!` | `Dir geht die Puste aus!` / `Nicht genug Ausdauer!` | Stat name stays `Ausdauer`. The toast speaks. |
| `veräußern` / `ins Lager übertragen` | `verkaufen` / `ins Lager gebracht` · `im Lager gelandet` | Legal/IT verbs for physical items. |
| `Halte X im Lager bereit, indem du...` | `Leg X ins Lager, selbst gebaut oder am Terminal gekauft.` | Manual-speak "by doing". |
| `ehe` / `sofern` / `sämtliche` / `verfügt über` | `bevor` / `wenn · solange` / `alle` / `hat · bietet` | Written-register connectors. |
| `hege eine Leidenschaft` / `bekleide ein Amt` | `sammle leidenschaftlich gern` / `habe eine hohe Position` | 19th-century phrasing. |
| `ICH BIN GESCHWINDIGKEIT!` | `ICH BIN SPEED!` | Pop-culture nod. The German dub keeps the English word (verify per project, log in ledger). |
| `Das ist kosmischer Schwachsinn!` | `So ein Quatsch!` / `Totaler Blödsinn!` | Calqued exclamation. Write the German one. |

## 2. Register, Address & Character Voice

| Speaker | Address | Notes |
|---|---|---|
| UI, tutorials, toasts | `du` (lowercase) | Industry default on PC/console. `Sie` only in explicitly corporate/serious products. Lock in `DE-DE_BIBLE.md`. |
| A1 Mentor, A2 Rival, A3 Rookie | `du` | Warm particles. `mal`, `ja`, `eben`, `schon`, `bloß`, `halt`. |
| A4 Scientist (colleague) | `du`. `Sie` if the character is a formal official | Precise vocabulary, spoken syntax. |
| A5 Outlaw / Antagonist, officials | `Sie` (cold) or `du` (contemptuous) | Decide per character, never per line. |

* **Never mix** `du` and `Sie` between the same two characters. One NPC = one form for the whole game, unless a scripted relationship shift is logged in the ledger.
* **Capitalization.** `Sie / Ihnen / Ihr` are always capitalized. `du / dich / dein` are lowercase in games (the letter-style capital `Du` is optional and must be consistent if used).
* **Regional color.** `Grüß dich`, `Servus` mark the south/Austria. Neutral de-DE uses `Hallo`, `Na?`, `Hi`. Use regionalisms only for a deliberately regional character.
* **Anglicisms.** `Loot`, `Skill`, `Quest`, `Crafting`, `Boss` are accepted gamer German. `Beute`, `Fähigkeit`, `Auftrag` work in more serious tones. Pick per product, not per line.

## 3. Spoken vs. Literary Tense

English uses Simple Past everywhere (*"He destroyed everything and ran"*). In spoken/everyday German (conversation, email, chat, personal letters) Germans use **Perfekt** for action verbs.

* **Use `Perfekt` in character speech, messages, letters.** *"Er hat alles kurz und klein geschlagen und ist untergetaucht."*, *"Ich bin eine Runde Probe geflogen."*, *"Unterwegs haben wir für Messungen angehalten."*
* **Keep `Präteritum` on auxiliaries, modals, and core state verbs**, where real spoken German uses it. `war`, `hatte`, `wollte`, `konnte`, `musste`, `sollte`, `durfte`, `wusste`, `dachte`. `stand`, `lag`, `saß`, `gab`, `kam`, `ging`, `sah`, `blieb`, `schien` are **optional**. Common in northern/central spoken German, replaced by Perfekt in the south and Austria. Either is acceptable. Keep one character consistent.
* **Narrative `Präteritum` is correct** (with `Konjunktiv I` for indirect speech) in news articles, codex/lore entries, third-person narration, and item descriptions with a historical voice, still free of archaic vocabulary.
* **Plusquamperfekt** for "before that" in speech. *"Als ich ankam, hatte er schon alles abgebaut."*, natural, not literary.

## 4. Player Gender Neutrality

German leaks gender mainly through **role nouns and titles**, not verbs. Verbs, predicate adjectives, and `Willkommen` are neutral (unlike es/pt).

| Leaks ✗ | Neutral ✓ |
|---|---|
| `Du bist ein echter Mechaniker.` | `Du bist ein echter Profi.` / `Du kannst das richtig gut.` |
| `Sieger!` / `Held des Tages` | `Gewonnen!` / `Sieg!` / `Das war heldenhaft.` |
| `Junge`, `Sohn`, `Kleiner`, `Mann`, `Alter` (to player) | `Neuling`, `Kleines` (only playful mentor), `Chef`, `Kumpel` (neutral in practice) |
| `Sehr geehrter Herr {playerName}` | `Hallo {playerName}` / `Guten Tag, {playerName}` |
| `Spieler*in`, `SpielerInnen`, `Spieler:in` | Rewrite. `Wer spielt, ...`, `du`, plural `alle` |

* **Predicate adjectives are safe.** `Du bist bereit`, `Du bist schnell`, `Willkommen`, no agreement to worry about.
* **Avoid role nouns about the player** (`Mechaniker`, `Pilot`, `Händler`). Use verbs or `Profi`. Named NPCs may use gendered forms about themselves.
* **No Gendersternchen / Binnen-I / Doppelpunkt** in game text unless the publisher mandates it. It breaks fonts, voice-over, and immersion.
* **Participles are neutral.** `Du hast gewonnen`, `Du wurdest befördert`, German participles do not inflect for the subject.

## 5. Plurals, Numbers & ICU

CLDR categories. **One** (1) and **other** (everything else, including 0).

| Count | German | ICU |
|---|---|---|
| 0 | `0 Reaktoren` / `keine Reaktoren` | `=0` / `other` |
| 1 | `1 Reaktor` | `one` |
| 2 | `2 Reaktoren` | `other` |
| 5 / 21 / 22 / 25 | `5 Reaktoren` / `21 Reaktoren` / `22 Reaktoren` / `25 Reaktoren` | `other` |

```text
{count, plural, =0 {Kein Reaktor im Lager.} one {{count} Reaktor im Lager.} other {{count} Reaktoren im Lager.}}
```

* `1` with a feminine/neuter noun. `1 Platine`, `1 Werkzeug`, the article form `eine/ein` is only needed in prose (`eine Platine`), never after a digit.
* Decimals always take **other** (`1,5 Reaktoren`, CLDR also files `1,0` under `other`). Avoid fractional counts of countable items.
* Spelled-out small numbers in dialogue. `ein paar Tage`, `drei Versuche`. Digits in UI.

## 6. Placeholder & Rich-Text Grammar Traps

* **Article and case before `{0}`.** German needs `der/die/das` and a case (`mit dem Reaktor` dative, `des Reaktors` genitive). Never write `mit {0}` or `den {0}`. Add a classifier noun that carries article and case. `"Gegenstand {0} ins Lager verschieben"`, `"Transport von Station {0} ins Lager"`, or restructure with a colon. `"Ins Lager verschoben: {0}"`.
* **Compound nouns with placeholders.** German compounds are written together. A placeholder forces a hyphen. `{0}-Upgrade`, `{0}-Bauplan`. Never `{0} Upgrade` (English spacing) and never `{0}Upgrade`.
* **Verb-final and separable verbs.** An English sentence that ends with a placeholder (`Move to {0}`) may need the verb or prefix *after* the placeholder in German (`Nach {0} verschieben`, `Lege {0} ab`). Concatenated fragments break this. Report seams to the lead.
* **Rich-text tags wrap whole words.** `<b>Reaktor</b>` yes, `<b>Reak</b>tor` no. Case endings stay inside. `<b>des Reaktors</b>`. Same rule for BBCode (`[b]…[/b]`) and Unreal `<>` styles.
* **Engine equivalents.** Unity `{0}` / `{itemName}`, Unreal `{Name}` and `|hpp`, Godot `%s`, ICU `{count, plural, …}`, printf `%1$s`, same rule in each. The German article and case live on the classifier noun next to the placeholder, not inside it.
* **Mandatory spaces.** Keep leading/trailing spaces of legacy seams exactly. German puts a space before `%` (`40 %`) and between number and unit (`3 min`), ideally `U+00A0`.
* **Long words.** Insert soft hyphens (`U+00AD`) in words longer than ~14 characters used in narrow UI (`Energie\u00ADversorgung`) if the engine honors them. Otherwise shorten.

## 7. Core UI Glossary

Buttons, keybindings, hotkeys, crosshair prompts. Concise **Infinitiv**. Tutorials and toasts. `du`-Imperativ (`Schalte den Hauptschalter aus`, `Räum erst die Sachen aus dem Aufzug!`).

| EN | de-DE | Note |
|---|---|---|
| Save / Load | `Speichern` / `Laden` | |
| Quit | `Beenden` (program) · `Verlassen` (session) | `Spiel beenden` / `Zum Hauptmenü` |
| Settings / Options | `Einstellungen` / `Optionen` | one per product |
| OK / Confirm | `OK` / `Bestätigen` | |
| Cancel / Back | `Abbrechen` / `Zurück` | |
| Continue / Resume | `Weiter` / `Fortsetzen` | |
| New Game | `Neues Spiel` | |
| Apply | `Übernehmen` | never `Anwenden` for settings |
| Delete | `Löschen` | |
| Yes / No | `Ja` / `Nein` | |
| Pause | `Pause` | |
| Retry / Skip | `Erneut versuchen` / `Überspringen` | |
| Inventory / Equip | `Inventar` / `Ausrüsten` | |
| Craft / Upgrade | `Herstellen` (`Bauen`) / `Verbessern` (`Aufwerten`) | |
| Level / Health / Stamina / Damage | `Stufe` (`Level` accepted) / `Leben` (`LP`) / `Ausdauer` / `Schaden` | |
| Buy / Sell | `Kaufen` / `Verkaufen` | |
| Take All | `Alles nehmen` | |

* Separate `Auftrag` (customer contract) from `Bestellung` (machine/queue order) when a game has both.
* Capitalization. German nouns capitalized always (`Neues Spiel`, not `neues spiel`). No English Title Case on verbs (`Erneut versuchen`, not `Erneut Versuchen`). Typical limits. Button 12 to 14, tab 10, badge 6 characters.

## 8. Typography, Numbers & Formatting

* **Quotes.** `„…“` (low-high), inner `‚…‘`. `"…"` and `« »` (Swiss) are wrong for de-DE.
* **Numbers.** `1.234,56`. Percent with space `40 %`. Units with space `3 min`, `5 km/h`.
* **Currency.** `1.234,56 €` (symbol after, with space). In-game fictional currency. `1.250 Credits`.
* **Date/time.** `26.11.2026`, `26. November 2026`, time `14:30 Uhr` (`14:30` in UI).
* **ALL-CAPS.** Write **`SS`** for `ß` by default (`SCHLIESSEN`, `GROSSMEISTER`). `ẞ` (U+1E9E) is official since 2017 but only safe when every game font has the glyph (verify with `font_glyph_scanner.py`). Keep `Ä Ö Ü`. Watch `Massen/Maßen` ambiguity in caps.
* **Genitive of names.** `{playerName}s Helm` is impossible with a placeholder (names ending in -s need an apostrophe `Klaus' Helm`). Restructure. `Helm von {playerName}`.
* **Dashes/ellipsis.** Spaced en dash `–` for breaks. Hyphen `-` in compounds. `…` single character.
* **Line breaks.** No break between number and unit, between `{0}` and `-Upgrade`. Prefer `U+00A0`.

## 9. Text Expansion & UI Fit

* **Typical expansion from en.** +30 to 35 % on average. Short strings far more (`ON` → `EIN` is fine, but `APPLY` → `ÜBERNEHMEN`, `OK` → `BESTÄTIGEN`, `SETTINGS` → `EINSTELLUNGEN`). German is the usual worst case for Western UI width.
* **Shortening strategies.** Drop the auxiliary (`Spiel speichern` → `Speichern`), use the noun (`Wird geladen…` → `Laden…`), accepted abbreviations (`Std.`, `Min.`, `Sek.`, `LP`, `Lvl` only if the product uses them), hyphenation with soft hyphens, two-line buttons where design allows.
* **Never abbreviate** by cutting letters mid-word (`Einstell.`) in player-facing UI.
* `ui_expansion_checker.py --locale de-DE` uses the de factor. Keep `max_chars` metadata current.

## 10. Ratings, Legal & Sensitive Content

* **Rating body.** **USK** (mandatory for physical release, IARC/USK for digital storefronts). Tiers 0/6/12/16/18. Profanity. Mild at 12, strong at 16+. Match the source tier, not the words.
* **§86a StGB.** Nazi symbols (swastika, SS runes, Hitler salute) were effectively banned in games until 2018. Now allowed only under the *Sozialadäquanz* clause (clear artistic/historical context). Still a legal and store risk. Log every occurrence in the ledger, never add them in translation, and expect publisher review.
* **Violence.** USK is stricter on realistic violence against humans than PEGI. "low-violence" German builds exist. Avoid adding violent imagery in text that the source does not have.
* **Jugendschutz / NetzDG.** Hate speech, glorification of violence, and extremist slogans can trigger indexing (BzKJ). Historic slogans and song lines need legal review.
* **Loot boxes / gambling.** No legal ban in Germany, but USK applies a gambling descriptor. Keep wording honest (`Chance`, not `Gewinn garantiert`).
* **Other sensitive items.** Real brands, real politicians, religious mockery, references to WWII victims, flag, do not improvise.

## 11. Golden Voice Anchors (A1 to A5)

Each pair keeps the **same meaning**. Only register changes. Generic roles, no project names.

1. **A1 Mentor / Altmechaniker** (`du`, Perfekt)
   * **✗ Robotisch.** "Beginne mit der Verwertung verfügbarer Materialien, um den Werkstattbetrieb wiederherzustellen, und ich werde Aufträge an dich übertragen."
   * **✓ Alltagsdeutsch.** "Fang mit dem an, was du aus dem Schrott rausholen kannst, und bring den Laden wieder zum Laufen. Dann schieb ich dir ein paar von meinen Aufträgen rüber."
2. **A2 Hotshot Rival / Rennpilot** (`du`)
   * **✗ Robotisch.** "Kritiker behaupten, meine Fähigkeiten hätten nachgelassen, was vollkommen unzutreffend ist. Repariere das Fahrzeug schnellstmöglich."
   * **✓ Alltagsdeutsch.** "Alle reden davon, ich hätte meinen Biss verloren. So ein Quatsch. Mach die Kiste schnell wieder flott – das Podium hol ich mir zurück."
3. **A3 Rookie / Teen** (`du`, jung, kurze Sätze)
   * **✗ Robotisch.** "Ich versuchte, das Leck mit Industriekitt abzudichten, jedoch versagte die Abdichtung unmittelbar beim Abheben."
   * **✓ Alltagsdeutsch.** "Ich hab das Leck mit Industriekitt zugeschmiert, aber kaum waren wir in der Luft, hat's geraucht und das Zeug ist abgeblättert."
4. **A4 Scientist / Ingenieurin** (`du` unter Kollegen)
   * **✗ Robotisch.** "Die Ausgangsleistung des Generators ist infolge unzureichender Kühlung auf vierzig Prozent des Nennwerts abgesunken."
   * **✓ Alltagsdeutsch.** "Der Generator läuft nur noch auf 40 % – die Kühlung kommt nicht hinterher. Tausch erst den Lüfter, dann messen wir noch mal."
5. **A5 Outlaw / Antagonist** (`Sie` oder `du`, kalt, kurz)
   * **✗ Robotisch.** "Sollten Sie Ihre Tätigkeit in diesem Gebiet fortsetzen, werden Sie mit negativen Konsequenzen konfrontiert."
   * **✓ Alltagsdeutsch.** "Wer hier weitermacht, kriegt Ärger. Letzte Warnung."

## 12. Linter Coverage Note

`lqa_linter.py --locale de-DE` currently catches. `Fokussieren` (ERR), `KONSTRUIEREN` (ERR), `veräußer*` (ERR), `ehe` (ERR, must be **case-sensitive lowercase** to avoid the false positive `Ehe` "marriage"), `befindet sich` (WARN), `Halte … bereit, indem` (WARN), capital `ẞ` (ERR).

### Suggested linter patterns

| Severity | Pattern | Message |
|---|---|---|
| ERR | `\behe\b` without `re.I` (replace current rule) | archaic `ehe`. Keeps `Ehe` legal |
| ERR | `\{\w+\}(?:Upgrade\|Bauplan\|Rezept\|Modul)\b` | compound with placeholder needs hyphen `{0}-Upgrade` |
| ERR | `\b(?:den\|dem\|des\|der\|die\|das\|mit\|von\|zum\|zur)\s+\{\w+\}` | article/case directly before placeholder |
| ERR | `\w+(?:\*\|:\|_)innen\b` or `\b[a-zäöüß]+Innen\b` | Gendersternchen / Binnen-I |
| WARN | `\b(?:sämtliche\|sofern\|verfügt über\|entnehmen\|platziert werden)\b` | written-register connector / passive |
| WARN | `\b(?:besitzt\|besitzen)\b` | notary `besitzen`: use `haben` |
| WARN | `\b(?:hege\|bekleide\|bekleiden)\b` | 19th-century phrasing |
| WARN | `\bkosmische[rn]? (?:Schwachsinn\|Unsinn)\b` | calqued exclamation |
| WARN | `\d+%` (no space) | German percent needs `40 %` |
| WARN | `\b(?:Junge\|Sohn\|Kleiner\|Mann)\b` in `[player]`-tagged strings | gendered address of the player |
| WARN | `\bAnwenden\b` in button keys | settings button is `Übernehmen` |
