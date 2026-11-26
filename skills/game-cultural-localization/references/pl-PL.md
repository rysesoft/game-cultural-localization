# Polish (`pl-PL`) Game Localization & Culturalization Playbook

Target feel: **Żywa, naturalna polszczyzna potoczna + autentyczny język polskich graczy** — ZERO *stylu kancelaryjnego*, ZERO clumsy English calques.

## 1. Anti-Translationese Ban List

| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `Ty masz` / `Twój warsztat posiada` | `Masz` / `W warsztacie jest` | Pro-drop; *posiadać* is office-speak, use *mieć*. |
| `Skupienie` / `Fokusuj` (interact) | `Użyj` / `Obsłuż` | Calque of "Focus". |
| `Ten przedmiot nie może zostać umieszczony tutaj.` | `To tu nie pasuje.` / `Nie położysz tego tutaj.` | Passive + modal = manual. |
| `W tym miejscu znajduje się już przedmiot!` | `To miejsce jest już zajęte!` / `Już coś tu leży!` | *Znajduje się* = police report. |
| `Posiadasz już to narzędzie!` | `Masz już to narzędzie!` | |
| `Twoja wytrzymałość jest zbyt niska!` | `Brakuje ci sił!` / `Nie masz siły!` | Stat stays `Wytrzymałość`; toast speaks. |
| `UZYSKAJ PRZEDMIOTY` | `WEŹ WSZYSTKO` / `ODBIERZ` | |
| `Poruszaj się do przodu / w lewo` | `Do przodu` / `W lewo` | Keybinding labels are adverbs. |
| `Dokonać naprawy` / `Zbyć na rynku` | `Naprawić` / `Sprzedać na rynku` | *Dokonać X* verbal-noun chain. |
| `W celu kontynuowania naciśnij` | `Aby kontynuować, naciśnij` / `Naciśnij, żeby przejść dalej` | *W celu* is bureaucratese. |
| `Operacja zakończona sukcesem.` | `Gotowe!` / `Zapisano.` | System jargon. |
| `Kosmiczne bzdury!` | `Bzdura!` / `Gadanie!` / `Co za brednie!` | Calqued exclamation. |
| `postawić coś z powrotem na nogi` (every line) | `uruchomić` / `rozkręcić` / `doprowadzić do porządku` | Fine once; repeated it reads as a translated tic. |

## 2. Register, Address & Character Voice

| Speaker | Address | Notes |
|---|---|---|
| UI, tutorials, toasts | `ty` (lowercase) | Polish PC/console default. Lock in `PL-PL_BIBLE.md`. |
| A1 Mentor, A2 Rival, A3 Rookie | `ty` | Particles: `no`, `przecież`, `w ogóle`, `spoko`, `jasne`, `dobra`. |
| A4 Scientist (colleague) | `ty`; `Pan/Pani` only if the character is formal **and** the player's gender is known | Otherwise use the indirect forms from §4. |
| A5 Outlaw / Antagonist, officials | indirect/`wy` forms or contemptuous `ty` | Never guess `Pan` vs `Pani` for the player. |

* **Capitalization of `Ty / Ci / Twój`:** capital in letters, emails, and in-game messages written *as* letters; lowercase in UI, tutorials, and spoken dialogue. One rule per text type, logged in the bible.
* **Never mix** `ty` and `Pan/Pani` between the same two characters within the game.
* **Vocative (wołacz):** Polish addresses people in the vocative: `Wujku!`, `Mechaniku!`, `Szefie!`, `Mistrzu!`. Fixed NPC names are declined in the script (`Marku!`, `Aniu!`). A `{playerName}` placeholder **cannot** be declined — never put it in vocative position; restructure: `Hej, {playerName}, …` is acceptable in casual speech (nominative is tolerated after `hej`), or drop the name.
* **Anglicisms:** `loot`, `skill`, `quest`, `craftować` exist in gamer Polish but official UI uses `łup`, `umiejętność`, `zadanie`, `wytwarzanie`. Dialogue may use slang for A2/A3 only.

## 3. Spoken vs. Literary Tense

N/A — Polish has a single past tense used in speech and prose alike; the register difference lies in vocabulary and aspect, not tense. See §4 for the gender problem of the past tense and §7 for aspect in buttons (perfective for one-shot actions: `Zapisz`, `Zbuduj`; imperfective for ongoing modes: `Śledź`, `Pokazuj`).

## 4. Player Gender Neutrality

Past-tense 2nd-person verbs (`zrobiłeś` / `zrobiłaś`), conditionals (`chciałbyś` / `chciałabyś`), **compound future with the l-participle** (`będziesz robił` / `robiła`), and adjectives (`gotowy` / `gotowa`) all reveal gender.

| Leaks ✗ | Neutral ✓ |
|---|---|
| `Udowodniłeś, że potrafisz.` | `Widać, że potrafisz.` / `Umiesz wyprodukować każdą część.` |
| `Zrobiłeś kawał dobrej roboty.` | `Świetna robota!` / `Kawał dobrej roboty.` |
| `Będziesz musiał to naprawić.` | `Będziesz musieć to naprawić.` (stiff) → better `Trzeba to naprawić.` / `Napraw to.` |
| `Chciałbyś spróbować?` | `Masz ochotę spróbować?` / `Spróbujesz?` |
| `Jesteś gotowy?` | `Gotowe?` / `Zaczynamy?` |
| `Zapisałeś grę.` | `Zapisano grę.` / `Gra zapisana.` |
| `Szanowny Panie` (to player) | `Dzień dobry` / `Witamy` / `Słyszałem wiele dobrego o tym warsztacie` |

* **Safe tools:** present tense, **simple perfective future** (`zrobisz`, `naprawisz`, `zobaczysz`), imperative, impersonal `-no/-to` (`Zapisano`, `Ukończono`), nouns and short exclamations, `Państwo`/`wasz` plural forms for formal register (`Państwa warsztat`, `z waszym warsztatem`).
* **Traps:** `będziesz + -ł/-ła` (use perfective or `będziesz + infinitive` sparingly), conditional `-byś`, past tense of any kind, predicate adjectives, `Pan/Pani`.
* Named NPCs with known gender conjugate freely about themselves (the Rival may say `wypadłem z formy` if male).

## 5. Plurals, Numbers & ICU

Polish has **four** CLDR categories: **one** (1), **few** (2–4, 22–24, 32–34 … but not 12–14), **many** (0, 5–21, 25–31, 12–14 …), **other** (fractions).

| Count | Polish | ICU |
|---|---|---|
| 0 | `0 reaktorów` | `many` |
| 1 | `1 reaktor` | `one` |
| 2 | `2 reaktory` | `few` |
| 5 | `5 reaktorów` | `many` |
| 12 | `12 reaktorów` | `many` |
| 21 | `21 reaktorów` | `many` |
| 22 | `22 reaktory` | `few` |
| 25 | `25 reaktorów` | `many` |
| 1,5 | `1,5 reaktora` | `other` |

```text
{count, plural, one {{count} reaktor} few {{count} reaktory} many {{count} reaktorów} other {{count} reaktora}} w magazynie
```

* Feminine/neuter nouns follow the same pattern with their own endings: `1 część / 2 części / 5 części`, `1 narzędzie / 2 narzędzia / 5 narzędzi`.
* The verb agrees too: `Został 1 reaktor`, `Zostały 2 reaktory`, `Zostało 5 reaktorów` — put the whole clause inside each ICU branch.
* A string without ICU support must avoid the noun: `Reaktory: {count}`, `Liczba reaktorów: {count}`.

## 6. Placeholder & Rich-Text Grammar Traps

* **Case after prepositions:** `z {0}`, `do {0}`, `w {0}` require genitive/locative; a nominative item name (`Standardowe stanowisko`) breaks. Insert an inflected classifier noun: `"Transport części ze stanowiska {0} do magazynu"`, `"Przedmiot {0} przeniesiono do magazynu"`, or use a colon: `"Przeniesiono do magazynu: {0}"`.
* **Vocative placeholder:** never `{playerName}!` as a call; see §2.
* **Adjective agreement with `{0}`:** `Nowy {0}` fails for feminine/neuter nouns; write `Nowość: {0}` or `{0} (nowe)`.
* **Numerals + noun:** never `{count} reaktor(ów)`; use ICU (§5).
* **Rich-text tags wrap whole words:** `<b>reaktora</b>` (ending inside the tag), never `<b>reaktor</b>a`; same for `[b]…[/b]` BBCode and Unreal `<>` styles.
* **Engine equivalents:** Unity `{0}`, Unreal `{Name}`, Godot `%s`, ICU, printf `%1$s` — identical rule: the Polish case and gender are carried by the classifier noun next to the placeholder.
* **Concatenation:** word order changes (`Koszt ulepszenia: {0}` vs English `{0} Upgrade Cost`); report seams to the lead; keep legacy leading/trailing spaces exactly (`--strict-whitespace`).
* **Separate** `Zlecenie / Kontrakt` (customer contract) from `Zamówienie` (workstation order) when a game has both.

## 7. Core UI Glossary

Buttons: short **2nd-person imperative** (gender-neutral, standard in Polish PC games). Infinitive is acceptable in settings lists (`Pokaż napisy` vs `Pokazywanie napisów`); one convention per screen type.

| EN | pl-PL | Note |
|---|---|---|
| Save / Load | `Zapisz` / `Wczytaj` | never `Załaduj` for saves |
| Quit | `Wyjdź` · `Wyjście` (menu heading) | `Wyjdź do pulpitu` / `Wyjdź do menu` |
| Settings / Options | `Ustawienia` / `Opcje` | |
| OK / Confirm | `OK` / `Potwierdź` | |
| Cancel / Back | `Anuluj` / `Wstecz` | |
| Continue / Resume | `Kontynuuj` / `Wznów` | |
| New Game | `Nowa gra` | lowercase `gra` |
| Apply | `Zastosuj` | |
| Delete | `Usuń` | |
| Yes / No | `Tak` / `Nie` | |
| Pause | `Pauza` | |
| Retry / Skip | `Spróbuj ponownie` / `Pomiń` | |
| Inventory / Equip | `Ekwipunek` / `Wyposaż` (`Załóż` for wearables) | |
| Craft / Upgrade | `Wytwórz` (`Stwórz`) / `Ulepsz` | tab: `Wytwarzanie` |
| Level / Health / Stamina / Damage | `Poziom` / `Zdrowie` (`PŻ`) / `Wytrzymałość` (`Kondycja`) / `Obrażenia` | |
| Buy / Sell | `Kup` / `Sprzedaj` | |
| Take All | `Weź wszystko` | |

* Capitalization: sentence case (`Nowa gra`, `Spróbuj ponownie`); never English Title Case. ALL CAPS only if the engine applies it. Typical limits: button 12, tab 10, badge 6.

## 8. Typography, Numbers & Formatting

* **Quotes:** `„…”` (low opening, high closing — note the closing `”`, not `“`); inner `«…»`.
* **Numbers:** `1 234,56` (thin/non-breaking space as thousands separator, comma decimal); percent without space in common usage `50%` (`50 %` also seen; pick one).
* **Currency:** `1 234,56 zł` (symbol after, with space); `PLN` only in finance UI.
* **Date/time:** `26.11.2026` or `26 listopada 2026`; `14:30`.
* **Dashes:** dialogue dash `–` (en dash with spaces), hyphen in compounds; ellipsis `…`.
* **Capitalization:** sentence case everywhere; nationality adjectives lowercase (`polski`), months lowercase (`listopad`).
* **Diacritics in caps:** keep `Ą Ć Ę Ł Ń Ó Ś Ź Ż` in ALL CAPS; never strip them.
* **Line breaks:** `U+00A0` after single-letter prepositions (`w`, `z`, `i`, `o`, `u`, `a`) — a line never ends with them.

## 9. Text Expansion & UI Fit

* **Typical expansion from en:** +20–30 %; short strings more (`OK` fine, `APPLY` → `ZASTOSUJ`, `RETRY` → `SPRÓBUJ PONOWNIE`, `SETTINGS` → `USTAWIENIA`).
* **Shortening strategies:** drop the object (`Zapisz grę` → `Zapisz`), use nouns in tabs (`Wytwarzanie`), accepted abbreviations (`PŻ`, `poz.`, `min`, `s`), avoid double-word verbs (`Spróbuj ponownie` → `Ponów` where design allows).
* `ui_expansion_checker.py --locale pl-PL` uses the pl factor; keep `max_chars` metadata current.

## 10. Ratings, Legal & Sensitive Content

* **Rating body:** **PEGI** (no mandatory Polish board). Tiers 3/7/12/16/18.
* **Profanity:** Polish gamers accept strong language at PEGI 18 (the *Wiedźmin* standard: `kurwa`, `cholera`, `skurwysyn` in dialogue); at PEGI 12–16 keep to `cholera`, `do diabła`, `kurczę`. Match the source tier, not the words.
* **Sensitive:** religious symbols and the Catholic Church (Art. 196 KK — offending religious feelings is a criminal offense), Nazi and communist symbolism (Art. 256 KK), WWII and Katyń references, Polish–Russian/Ukrainian politics, real politicians. Flag in the ledger with `[sensitive]`; never improvise.
* **Gambling:** loot boxes are legal but under regulatory watch; keep probability wording honest.
* **Alcohol:** advertising restrictions do not apply to fiction, but avoid real brands.

## 11. Golden Voice Anchors (A1–A5)

Each pair keeps the **same meaning**; only the register changes. Generic roles, no project names.

1. **A1 Mentor / Doświadczony mechanik** (`ty`, bez zakładania płci gracza)
   * **✗ Sztuczne:** "Rozpocznij od odzyskania dostępnych materiałów w celu przywrócenia funkcjonowania warsztatu, a przekażę ci zlecenia."
   * **✓ Naturalne:** "Zacznij od tego, co da się wygrzebać ze złomu, i rozkręć ten warsztat na nowo. Jak ruszy, podrzucę ci parę swoich zleceń."
2. **A2 Hotshot Rival / Pilot wyścigowy** (`ty`; NPC o znanej płci)
   * **✗ Sztuczne:** "Krytycy twierdzą, że moje umiejętności uległy pogorszeniu, co jest całkowicie nieprawdziwe. Napraw pojazd w jak najkrótszym czasie."
   * **✓ Naturalne:** "Wszyscy gadają, że wypadłem z formy. Bzdura. Doprowadź mi tę maszynę do porządku, i to szybko – podium jest moje."
3. **A3 Rookie / Młody** (`ty`, krótkie zdania)
   * **✗ Sztuczne:** "Podjąłem próbę uszczelnienia wycieku przy użyciu masy przemysłowej, jednak uszczelnienie zawiodło natychmiast po starcie."
   * **✓ Naturalne:** "Próbowałem załatać wyciek przemysłową masą, ale ledwo oderwaliśmy się od ziemi, cała łata zadymiła się i odpadła."
4. **A4 Scientist / Inżynierka** (`ty` między współpracownikami)
   * **✗ Sztuczne:** "Moc wyjściowa generatora uległa obniżeniu do czterdziestu procent wartości nominalnej wskutek niewystarczającego chłodzenia."
   * **✓ Naturalne:** "Generator chodzi na 40% – chłodzenie nie wyrabia. Najpierw wymień wentylator, potem zmierzymy jeszcze raz."
5. **A5 Outlaw / Antagonista** (chłodno, krótko, bez płci gracza)
   * **✗ Sztuczne:** "W przypadku kontynuowania działalności na tym terenie poniesiesz negatywne konsekwencje."
   * **✓ Naturalne:** "Jeszcze raz tu zajrzysz i będzie z tobą krucho. Ostatnie ostrzeżenie."

## 12. Linter Coverage Note

`lqa_linter.py --locale pl-PL` currently catches: `fokusuj` (ERR), `posiadasz / posiada` (WARN), `dokonać X` (WARN).

### Suggested linter patterns

| Severity | Pattern | Message |
|---|---|---|
| ERR | `\b(?:z\|ze\|do\|w\|we\|na\|od\|przy\|o)\s+\{\w+\}` | preposition directly before placeholder (case trap) |
| ERR | `\{\w+\}\s+(?:reaktor\|przedmiot\|część)\w*\(\w+\)` | `(ów)`-style optional plural: use ICU |
| ERR | `\bbędziesz\s+\w+[łl][aey]?\b` in `[player]`-tagged strings | compound future reveals gender |
| WARN | `\b\w+(?:łeś\|łaś\|byś\|abyś)\b` in `[player]`-tagged strings | gendered 2nd-person past/conditional |
| WARN | `\b(?:znajduje się\|zostać umieszczon\w+\|w celu\|uległ\w*\|w przypadku)\b` | kancelaryjny |
| WARN | `\b(?:Panie\|Pani\|Szanown\w+)\b` in `[player]`-tagged strings | gendered formal address |
| WARN | `\bkosmiczn\w+ bzdur\w*\b` | calqued exclamation |
| WARN | `\b(?:Zapisać\|Wczytać\|Wyjść\|Zastosować)\b` in button keys | infinitive on button; project uses imperative |
| WARN | `\b(?:Załaduj\|Ładuj)\b` in save/load keys | use `Wczytaj` |
| WARN | `\b[wziouaWZIOUA]\s` followed by line end / `\\n` | single-letter preposition at line end (needs NBSP) |
