# Italian (`it-IT`) Game Localization & Culturalization Playbook

> **Scope note:** `it-IT` = standard Italian for Italy (PEGI territory). Swiss Italian (`it-CH`) differs only in currency (`CHF`) and a few administrative terms; no separate bible is needed unless the project ships Swiss store pages.

Target feel: **italiano parlato vivo, fluido e naturale, con vero lessico gamer italiano** — zero *burocratese*, zero calques from English, zero literary tense in dialogue. Every ✓ example must read as if an Italian player wrote it.

## 1. Anti-Translationese Ban List
| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `Effettuare la riparazione` / `Procedere allo smantellamento` | `Riparare` / `Smontare` | Nominalised verb → plain verb. |
| `Focalizzare` / `Mettere a fuoco` (interact prompt) | `Usa` / `Interagisci` | Literal *focus*. |
| `Questo oggetto non può essere posizionato qui.` | `Qui non ci va.` / `Non puoi metterlo qui.` | English passive + *posizionato*. |
| `Un oggetto è già presente in questa posizione!` | `Questo posto è già occupato!` / `C'è già qualcosa qui!` | *È presente* + *posizione* = municipal notice. |
| `Possiedi già questo strumento!` | `Hai già questo attrezzo!` | *Possedere* is bookish; spoken Italian says *avere*. |
| `La tua resistenza è troppo bassa!` | `Non hai più fiato!` / `Energia esaurita!` | Stat report → player line; never `Sei esausto` (gendered, §4). |
| `La durata del sonno è troppo breve.` | `Non vale la pena dormire così poco.` | Report phrasing. |
| `OTTIENI OGGETTI` | `PRENDI TUTTO` / `RITIRA` | Literal *GET ITEMS*. |
| `Muovi in avanti / Muovi a sinistra` | `Avanti` / `Indietro` / `Sinistra` / `Destra` | Keybinding labels are one word. |
| `Gli oggetti sono stati trasferiti nel magazzino.` | `Pezzi spostati in magazzino.` / `Tutto in magazzino.` | Passive + *trasferiti* calque. |
| `Salvataggio effettuato con successo.` | `Partita salvata.` / `Salvataggio completato.` | *Con successo* is a calque of *successfully*. |
| `mediante` / `tramite` in dialogue | `con` | Legalese preposition. |
| `esso / essa / essi / esse` | drop the pronoun | Dead in spoken Italian. |
| `laggiù` for a vague *out there* | drop it, or `da quelle parti` / `in giro` | *Laggiù* points to a real place. |
| `Per favore, attendere prego.` | `Attendi…` / `Un attimo…` | Doubled politeness; Italian UI rarely says *per favore*. |

## 2. Register, Address & Character Voice
* **Pronoun set:** `tu` (singular, default), `Lei` (singular formal, verb in 3rd person singular), `voi` (plural, neutral). `Ella` and formal `Voi` are 19th-century / southern-dialect only — never in a modern UI.
* **Layers, locked in `IT-IT_BIBLE.md`; never mix inside one layer:**
  1. **Buttons / menu labels:** 2nd-person singular **imperative** (§7) — the Italian platform standard (`Continua`, `Salva`, `Applica`). Infinitive buttons (`Continuare`) read as old office software.
  2. **System prose & tutorials:** `tu` (`Vuoi davvero uscire?`, `Premi per continuare`).
  3. **Character dialogue:** register belongs to the speaker. A1 Mentor → `tu`; A2 Rival → `tu`; A3 Rookie → `tu`; A4 Scientist → `Lei` toward a stranger/client, `tu` with colleagues; A5 Antagonist → cold `Lei`.
* **`Lei` mechanics:** verb in 3rd singular (`Spero che stia bene`), object clitics `La` / `Le`, possessive `Suo/Sua`. Capitalising `Lei / Le / La / Suo` is standard in letters and e-mails and optional in spoken dialogue — lock one choice per project.
* **Pro-drop is mandatory:** `Tu hai`, `Io sono`, `Lui ha` ✗ unless contrastive (`Io non c'entro`).
* **Spoken rhythm:** `senti`, `guarda`, `insomma`, `comunque`, `dai`, `mica`, `un bel guaio`, `rimettere in sesto`, `tirare avanti`, `roba`. Avoid regional-only slang (`daje` is Roman; `figo` is fine nationally) unless the bible assigns it to a character.

## 3. Spoken vs. Literary Tense
* **Dialogue, letters, chat, UI:** **passato prossimo** (`ha distrutto tutto ed è sparito`, `ho provato a tappare la perdita`) + **imperfetto** (`era`, `aveva`). Never *passato remoto* (`distrusse`, `fuggì`, `tentai`) in anything a modern character says or writes.
* **Third-person lore, codex, item histories, narrator:** **passato remoto is legitimate and expected** (`Il regno cadde nel 2140.`); forcing passato prossimo there reads like a diary. Lock it in the bible.
* **Regional note:** southern speakers use passato remoto in conversation; the localization default is still passato prossimo. A southern character may be given remoto **only** as a locked voice trait.
* **Future:** spoken Italian often uses the present for near future (`Domani ci vediamo`); futuro semplice is fine for promises and UI (`Verrà applicato al riavvio`). Congiuntivo imperfetto (`se fosse`) is normal spoken Italian — do not avoid it.

## 4. Player Gender Neutrality
Italian marks gender on **adjectives, participles with `essere` (including reflexives), participles with a preceding direct-object clitic, role nouns, and articles**. The player's gender is unknown.

| Leaks ✗ | Neutral ✓ | Strategy |
|---|---|---|
| `Sei pronto?` | `Tutto pronto?` / `Si parte?` | Move the adjective to a thing. |
| `Sei diventato un vero meccanico.` | `Ormai il mestiere lo conosci davvero.` | Active verb, no role noun. |
| `Sei stato selezionato.` | `Hai superato la selezione.` / `Selezione completata.` | `avere` + participle with no preceding clitic **never agrees**. |
| `Ti sei costruito qualcosa di prezioso.` | `Hai messo in piedi qualcosa di prezioso.` | Reflexive = `essere` = agreement. |
| `Il vicepresidente L'ha contattata.` | `Il vicepresidente Le ha scritto / Le ha parlato.` / `…si è messo in contatto con Lei.` | Direct-object clitic (`La / ti / mi`) forces agreement; indirect `Le / ti` with *scrivere, parlare, telefonare* does not. |
| `Benvenuto!` | `Ti diamo il benvenuto!` / `Benvenuto a bordo!` ✗ → `Ti diamo il benvenuto a bordo!` | *Benvenuto* as a **noun** (after *dare*) is invariant; as an interjection it agrees. |
| `Alleato` / `Alleati` | `Alleanza` | Masculine plural is **not** neutral. |
| `Sei esausto.` | `Sei senza fiato.` / `Energia esaurita.` | Prepositional phrase. |
| `Ciao, ragazzo / figliolo / amico` | `Ciao, capo` / `Ehi` / nickname from the bible | *Capo, collega* are invariant; `caro/cara` is not. |

* **The `Lei` + participle trap (corrected):** with `Lei`, participles and adjectives agree with the **real gender of the person addressed** — `Lei è stato gentile` to a man, `Lei è stata gentile` to a woman. Feminine agreement for a male addressee (`L'ho vista, dottore`) is old bureaucratic usage, not a neutral option. `la Sua officina` is feminine because *officina* is feminine, not because of `Lei`. The only safe route is the same as with `tu`: **no participle or adjective about the player** — rewrite with `avere` + object (`Ha fatto un ottimo lavoro`), nouns, or indirect objects.
* **Invariant adjectives:** `abile`, `capace`, `forte`, `grande`, `veloce`, `in gamba`, `eccezionale`, `imbattibile`, `affidabile`.
* Typographic hacks (`pront*`, `prontə`, `pronto/a`) are banned in dialogue and UI; `(a)` only in legal text if the bible allows it.

## 5. Plurals, Numbers & ICU
* **CLDR categories for `it`:** `one` (exactly 1), `many` (compact millions: `1 milione di`), `other` (everything else, **including 0 and decimals**).

| `{0}` | Italian | Category |
|---|---|---|
| 0 | `0 oggetti` (better: `Nessun oggetto`) | other |
| 1 | `1 oggetto` | one |
| 2 | `2 oggetti` | other |
| 5 | `5 oggetti` | other |
| 21 | `21 oggetti` | other |
| 1,5 | `1,5 oggetti` | other |

* **ICU:** `{count, plural, one {# oggetto} other {# oggetti}}`; `=0 {Nessun oggetto}` is the natural override.
* `oggetto/i` or `oggetto(i)` is banned in UI. Watch invariant nouns (`1 città / 2 città`, `1 film / 2 film`) and irregulars (`uovo / uova`, `braccio / braccia`).
* **Numbers as words:** zero to nine in letters inside dialogue, digits in UI. Ordinals: `1º`, `2ª`, or `1°` — never `1st`-style.

## 6. Placeholder & Rich-Text Grammar Traps
* **Article + `{0}` breaks on gender, initial sound and elision:** `il {0}` → `il scudo` ✗ (`lo scudo`), `il elmo` ✗ (`l'elmo`), `il spada` ✗ (`la spada`). Same for `un/uno/una/un'` and articulated prepositions `del/dello/della/dell'`, `nel/nello/nella/nell'`, `al/allo/alla/all'`. **Never glue any of these to a placeholder.** Use a classifier noun or a colon: `l'oggetto {0}`, `la ricetta {0}`, `Ottenuto: {0}`, `Equipaggia: {0}`.
* **Adjective / participle after placeholder:** `{0} equipaggiato` ✗ → `Hai equipaggiato: {0}` ✓ (`avere`, invariant) or `Equipaggiamento: {0}`.
* **Number placeholders** follow §5 ICU; `%d oggetti` is the same trap in printf form.
* **Rich text:** the elided article stays inside the tag with its word: `l'<b>elmo</b>` ✗ → `<b>l'elmo</b>` ✓. Never split a word at an accent (`<color=red>perch</color>é` ✗). Tags must nest; the linter checks parity.
* **Concatenation ban:** `"Hai " + n + " oggetti"` cannot be pluralised or reordered; demand one string with placeholders.
* **Leading/trailing spaces** required by the source (`"Premi "` + key) must be preserved; run `lqa_linter.py --strict-whitespace`.
* **Engine-agnostic note:** the rules apply identically to Unity `{0}` / `{itemName}` + `<b>`/`<color=>`/`<sprite>`, Unreal `{Name}` / `|hpp(…)` / `<tag>…</>`, Godot `%s` / `%d` / BBCode `[b]…[/b]`, printf `%s %1$s`, Python-style `{name}` and ICU `{count, plural, …}`. Treat every placeholder syntax as an opaque token that cannot take an article, elision or agreement; Unreal `|plural(one=…, other=…)` and Godot `tr_n()` follow the same one/other split as §5.

## 7. Core UI Glossary
Button format: **2nd-person singular imperative** for actions, **noun** for screens, **sentence case** (`Nuova partita`, never `Nuova Partita`), ALL CAPS only if the source is caps and the font has `À È É Ì Ò Ù`. Keybinding labels: nouns or short imperatives (`Avanti`, `Salta`, `Accovacciati`).

| English | `it-IT` (market standard) | Note |
|---|---|---|
| Save | `Salva` | `Salvataggio…` for the progress state. |
| Load | `Carica` | `Caricamento…` for loading screens. |
| Quit | `Esci` | `Esci dal gioco` / `Torna al menu`. |
| Settings / Options | `Impostazioni` / `Opzioni` | Pick one per project. |
| OK / Confirm | `OK` / `Conferma` | |
| Cancel | `Annulla` | |
| Back | `Indietro` | |
| Continue | `Continua` | |
| New Game | `Nuova partita` | `Nuovo gioco` ✗. |
| Apply | `Applica` | |
| Delete | `Elimina` | `Cancella` also common for saves. |
| Yes / No | `Sì` / `No` | `Sì` always with the accent; `Si` is the reflexive pronoun. |
| Pause | `Pausa` | Noun as menu title. |
| Resume | `Riprendi` | |
| Retry | `Riprova` | |
| Skip | `Salta` | `Ignora` for optional steps. |
| Inventory | `Inventario` | |
| Equip | `Equipaggia` | |
| Craft | `Crea` / `Fabbrica` | `Creazione` for the menu. |
| Upgrade | `Potenzia` / `Migliora` | `Potenziamento` (noun). |
| Level | `Livello` | `Liv.` abbreviation. |
| Health | `Salute` / `Vita` (`PV`) | Pick one per bible. |
| Stamina | `Resistenza` / `Energia` | `Resistenza` is the stat standard; `fiato` is the spoken word. |
| Damage | `Danni` | Usually plural on stat screens; `Danno` for a single hit. |
| Buy / Sell | `Compra` / `Vendi` | `Acquista` on shop headers. |

## 8. Typography, Numbers & Formatting
* **Accent direction is the #1 Italian typo:** `perché`, `poiché`, `né`, `sé` (acute); `è`, `cioè`, `caffè` (grave). `perchè` ✗, `pò` ✗ (`po'` with apostrophe), `E'` ✗ (`È` — a capital accented letter, never apostrophe-as-accent). `sì` (yes) always accented.
* **Quotes:** publishing uses `«…»` (often without inner space) or `“…”`; games mostly lock `“ ”` for fonts. Lock one; never straight `"` in dialogue. Apostrophe `’` or `'` — lock one, never mix.
* **Numbers:** decimal comma, thousands point: `1.234,56`; currency after the number with a space: `12,50 €`; percent **without** space: `50%`.
* **Date / time:** `26/11/2026` or `26 novembre 2026` (month lowercase); time `14:30`.
* **Case:** sentence case; **no Title Case**; days, months, languages, nationalities lowercase (`lunedì`, `novembre`, `italiano`). Accented capitals mandatory (`È`, `PERCHÉ`, `PIÙ`).
* **Ellipsis:** single `…`, no space before. **Dashes:** `–` for dialogue dashes in narrative prose; no space before `? ! : ;` (unlike French).
* **Line breaking:** never break after an elided article (`l'` / `un'`) or before `12,50 €`; disable hyphenation in UI.

## 9. Text Expansion & UI Fit
* **Typical expansion vs. English: +10 % to +25 %** for sentences; short labels can double (`ON` → `ATTIVO`, `Craft` → `Fabbrica`, `Load` → `Carica`). Industry rule of thumb (IBM/W3C): the shorter the source, the higher the ratio.
* **Shortening, in order:** drop articles in labels (`Livello`, not `Il livello`) → shorter synonym (`Esci` vs `Abbandona la partita`, `Crea` vs `Fabbrica`) → standard abbreviations in tooltips only (`Liv.`, `PV`, `Impost.`) → never cut a word mid-way or drop an accent to save space.
* Run `ui_expansion_checker.py --locale it-IT --fail-on-high`; the checker's locale table must carry the same +25 % ceiling as this section.

## 10. Ratings, Legal & Sensitive Content
* **Rating board:** **PEGI** (Italy, via the industry association IIDEA); AGCOM oversees minors' protection in media. *Bad Language* thresholds decide which words survive.
* **Profanity ladder (lock in bible):** `accidenti / cavolo / mannaggia` (PEGI 3–7) → `merda`, `cazzo` (12–16, very common in speech) → `stronzo`, `vaffanculo`, `figlio di puttana` (16–18) → slurs never.
* **Blasphemy is a separate, harder taboo:** *bestemmie* (`porco D…`, `D… cane`) are **never** acceptable in any build at any rating — they trigger complaints and store removals far beyond a swear word. The linter should flag them.
* **Sensitive topics:** Fascism and its symbols (Legge Scelba / Legge Mancino), the Mafia as a comic stereotype, the Church, North–South jokes, and recent political figures need lead sign-off.
* **Legal:** gambling-like mechanics (loot boxes) fall under ADM scrutiny — keep odds factual (`probabilità`), never `gratis` for anything with a cost; consumer law requires Italian on store pages and manuals.

## 11. Golden Voice Anchors (A1–A5)
Each pair keeps the **same meaning**; only the voice changes. Roles are generic (the Mentor, the Rival…) — never project names.

1. **A1 Mentor / Veteran (`tu`, warm, passato prossimo):**
   * *Robotic ✗:* `"A metà della produzione comprese cosa stava costruendo. Distrusse ogni cosa e fuggì."`
   * *Natural ✓:* `"A metà del lavoro ha capito cosa stava costruendo davvero. Ha fatto a pezzi tutto quanto ed è sparito."`
2. **A2 Hotshot Rival (`tu`, cocky, fast):**
   * *Robotic ✗:* `"Le persone continuano ad affermare che ho perso il mio vantaggio. Effettua subito la riparazione del veicolo."`
   * *Natural ✓:* `"In giro continuano a dire che ho perso lo smalto. Tutte balle! Sistemami la macchina, e subito."`
3. **A3 Rookie / Teen (`tu`, short, everyday slang):**
   * *Robotic ✗:* `"Ho tentato di sigillare la perdita mediante un sigillante, ma esso si è staccato al decollo."`
   * *Natural ✓:* `"Ho provato a tappare la perdita con dello stucco, ma appena è decollata si è staccato tutto."`
4. **A4 Scientist / Engineer (`Lei` toward a client, precise but spoken):**
   * *Robotic ✗:* `"Si rende necessario procedere alla sostituzione del generatore prima del successivo utilizzo dell'apparecchio."`
   * *Natural ✓:* `"Sostituisca il generatore prima di riaccendere l'apparecchio."`
5. **A5 Outlaw / Antagonist (cold `Lei`, short, gender-safe):**
   * *Robotic ✗:* `"Mi è stato riferito che Lei ha preso contatto con le autorità. Sarebbe spiacevole se la Sua situazione divenisse complessa."`
   * *Natural ✓:* `"Mi hanno detto che ha parlato con le autorità. Sarebbe un peccato se le cose si complicassero, per Lei."`

## 12. Linter Coverage Note
Currently in `lqa_linter.py` for `it-IT`: `effettuare` (WARN), `esso/essa/essi/esse` (ERR), `possiedi` (WARN), `procedere a` (WARN). Note: the `esse` alternative also matches the plural of the letter name and some surnames — keep it but scope it to dialogue/UI categories. Everything else in §1, §4, §6 and §8 is **not** yet enforced.

**Suggested linter patterns (regex-friendly, low false-positive risk, for the scripts owner):**
* ERR `\b(?:il|lo|la|i|gli|le|un|uno|una|un'|del|dello|della|dell'|nel|nello|nella|nell'|al|allo|alla|all')\s*\{\w+\}` — article/articulated preposition glued to a placeholder (§6).
* ERR `\bE'\b` — apostrophe used as accent (→ `È`).
* ERR `\b(?:perchè|poichè|affinchè|nè|pò)\b` — wrong accent direction / missing apostrophe.
* ERR `\bOTTIENI OGGETTI\b`, `\bMuovi (?:in|a) \w+\b`, `\bFocalizz\w+\b|\bMettere a fuoco\b`.
* WARN `\bnon può essere \w+at[oa]\b` — English passive.
* WARN `\bmediante\b|\btramite\b` in dialogue categories — legalese preposition.
* WARN `\bcon successo\b` — calque of *successfully*.
* WARN `\b(?:Sei|È|Siete) (?:pronto|sicuro|certo|diventato|stato|esausto|stanco)\b` and `\bTi sei \w+at[oa]\b` — gendered predicate / reflexive about the player.
* WARN `\bL'ha \w+at[oa]\b` — direct-object clitic with `Lei` forces agreement.
* WARN `\bBenvenut[oa]\b` (case-sensitive, so `il benvenuto` does not match) — use `Ti diamo il benvenuto`; WARN `\bAlleat[oi]\b` — use `Alleanza`.
* WARN `\b\w{3,}(?:arono|irono|erono)\b` scoped to dialogue categories — passato remoto 3rd-plural endings. Singular `-ò / -ì` endings are too noisy to automate (`però`, `così`, `può`); leave those to the native-ear critic.
* ERR `\b(?:porco|porca)\s+(?:dio|madonna)\b|\bdio\s+(?:cane|porco)\b` (case-insensitive) — bestemmie (§10).
