# French (`fr`) Game Localization & Culturalization Playbook

> **Scope note.** In this suite `fr` = **France French (`fr-FR`)**, the default for PEGI-territory PC/console builds. Canadian French (`fr-CA`) is **not** covered by these defaults. The short delta table in §2 and §8 lists what changes. A Québec build needs its own `FR-CA_BIBLE.md`.

Target feel. **Français parlé naturel, vrai langage joueur PC/console**, zero *français traduit*, zero *style administratif*, zero literary tense in dialogue. Every ✓ example below must read as if a French player wrote it, not as if it was translated.

## 1. Anti-Translationese Ban List
| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `Procéder à la réparation / à la fabrication` | `Réparer` / `Fabriquer` | *Procéder à* + noun is administrative filler. Games use the bare verb. |
| `Effectuer une sauvegarde` | `Sauvegarder` | Nominalised verb → plain verb. |
| `Cet objet ne peut pas être placé à cet endroit.` | `Impossible de poser ça ici.` / `Ça ne rentre pas ici.` | Passive + *à cet endroit* = police report. |
| `Un objet se trouve déjà à cet emplacement !` | `La place est déjà prise !` / `Il y a déjà quelque chose ici !` | *Se trouver* + *emplacement* is manual-speak. |
| `Vous possédez déjà cet outil !` | `Outil déjà en poche !` / `Tu as déjà cet outil !` | *Posséder* is notarial. Spoken French says *avoir*. |
| `Votre endurance est trop faible !` | `Plus assez d'endurance !` / `À bout de souffle !` | Stat report → player-facing exclamation. |
| `Les objets ont été transférés vers l'entrepôt.` | `Pièces envoyées à l'entrepôt.` / `Tout est parti en réserve.` | *Transférés vers* is a calque of *transferred to*. |
| `Focuser` (interact prompt) | `Utiliser` / `Interagir` | *Focuser* does not exist in French. |
| `OBTENIR LES OBJETS` | `TOUT PRENDRE` / `RÉCUPÉRER` | Literal *GET ITEMS*. French loot UI says *Tout prendre*. |
| `Déplacer vers l'avant / vers la gauche` | `Avancer` / `Reculer` / `Gauche` / `Droite` | Keybinding labels are one word. |
| `Sauvegarde effectuée avec succès.` | `Sauvegarde réussie.` / `Partie sauvegardée.` | *Avec succès* is a calque of *successfully*. |
| `Veuillez patienter s'il vous plaît.` | `Veuillez patienter…` / `Un instant…` | *Veuillez* already means *please*. |
| `Il est recommandé de sauvegarder.` | `Pense à sauvegarder.` / `Sauvegarde conseillée.` | Impersonal notice-in-a-lift tone. |
| `là-bas` for a vague *out there* | drop it, or `de ton côté` / `dans le coin` | *Là-bas* needs a real place in French. *out there* is a calque. |
| `Vous avez été déconnecté.` | `Déconnexion terminée.` / `Connexion perdue.` | Passive about the player also leaks gender (§4). |

## 2. Register, Address & Character Voice
* **Three layers, locked in `FR_BIBLE.md`. Never mix inside one layer.**
  1. **Buttons / menu labels.** Infinitive, no pronoun at all (§7). Avoids *tu/vous* entirely.
  2. **System prose & tutorials (toasts, confirmations, tooltips).** Choose **one** of *impersonal* (`Quitter la partie ?`, `Sauvegarde impossible.`) or `tu`. Suite default = **impersonal first, `tu` when a pronoun is unavoidable** (indie/mentor-voiced games). AAA sims that follow platform convention may lock `vous` instead, but then *every* system string uses `vous`.
  3. **Character dialogue.** Register belongs to the speaker, not to the UI layer. A1 Mentor → `tu`. A2 Rival → `tu`. A3 Rookie → `tu`. A4 Scientist → `vous` (professional, still conversational). A5 Antagonist → cold `vous`.
* The ban-list ✓ column uses the impersonal form first and marks a `tu` variant. A `vous`-locked project rewrites those as `vous` and nothing else changes.
* **Spoken rhythm for `tu` characters.** `on` instead of stiff `nous` (`On a réussi`, `On va leur montrer`). Connectors `bon`, `bah`, `écoute`, `franchement`, `quand même`, `du coup`, `bref`, `histoire de`. Polite `vous` characters write crisp modern French, not 19th-century notary prose.
* **Capitalisation.** `vous`, `votre` are **lowercase** in French (no German-style *Sie*). `Monsieur / Madame` only when gender is known (§4).
* **fr-CA delta (not covered by defaults).**

| Topic | `fr-FR` (this playbook) | `fr-CA` (lock separately) |
|---|---|---|
| Save | `Sauvegarder` | `Enregistrer` (OQLF) |
| E-mail / chat | `e-mail` / `chat` | `courriel` / `clavardage` |
| Weekend | `week-end` | `fin de semaine` |
| Anglicisms in slang | tolerated (`cool`, `le boss`) | avoided. OQLF terminology preferred |
| Space before `? ! ;` | yes (U+00A0) | **no** (only before `:`) |
| Register default | `tu` in casual dialogue | `tu` more widespread, incl. tutorials |

## 3. Spoken vs. Literary Tense
* **Dialogue, letters, e-mails, chat logs, UI.** **Passé composé** (`il a tout détruit et il a filé`, `on s'est arrêtés en route`) + **imparfait** (`c'était`, `il avait`). **Never** passé simple (`il détruisit`, `nous partîmes`) and never subjonctif imparfait (`qu'il fût`) in anything a character says or writes.
* **Third-person narration, lore, codex, item histories, narrator voice-over.** **Passé simple is legitimate and expected** (`Le roi fonda la cité en 1012.`). Forcing passé composé there reads like a diary. Modern press and novels still use passé simple in narrative. The old "even newspapers never use it" claim is wrong, the rule is *who speaks*, not *where it is printed*.
* **Future.** Spoken = `on va + inf.` (`On va voir`). Futur simple stays fine in both layers (`Je reviendrai`).
* Lock the narrative tense in `FR_BIBLE.md` (`dialogue = PC + imparfait; lore = passé simple`).

## 4. Player Gender Neutrality
French marks gender on **adjectives, past participles with `être`, participles with a preceding direct object (`vous a contacté(e)`), and role nouns**. The player's gender is unknown, so none of these may refer to the player.

| Leaks ✗ | Neutral ✓ | Strategy |
|---|---|---|
| `Tu es prêt ?` | `Tout est prêt ?` / `On y va ?` | Move the adjective to a thing or drop it. |
| `Vous êtes devenu un vrai mécanicien.` | `Vous maîtrisez vraiment le métier.` | Active verb instead of *devenir* + role noun. |
| `Le vice-président vous a contacté.` | `Le vice-président a pris contact avec vous.` / `…vous a parlé / vous a écrit.` | Preceding direct object (`vous`, `te`) forces agreement. Use a noun phrase or an indirect-object verb (*parler à, écrire à, répondre à, faire confiance à* never agree). |
| `Vous avez été sélectionné.` | `Votre candidature est retenue.` / `Sélection confirmée.` | Passive = `être` + participle. |
| `Tu es sûr ?` | `Vraiment ?` / `Confirmer ?` | Invariant word or infinitive. |
| `Bienvenu !` | `Bienvenue !` | *Bienvenue* (interjection) is invariant, **safe** and standard, unlike es/pt. |
| `Allié` badge | `Alliance` | Abstract noun. `Allié·e` (median dot) is banned in immersive text. |
| `Salut mon gars / fiston / ma belle` | `Salut toi` / `Salut chef` / bible nickname | Drop gendered vocatives. `chef` is used for anyone in workshop talk. |

* **Invariant adjectives you can always use.** `habile`, `fiable`, `capable`, `efficace`, `rapide`, `solide`, `calme`, `tranquille`, `exemplaire`, `hors pair`, `brave`.
* **Safe compound tenses.** `avoir` + participle **without** a preceding direct object never agrees, `Tu as gagné`, `Vous avez réussi`, `Tu as tout réparé` are always safe.
* Typographic workarounds (`prêt·e`, `prêt(e)`, `prêt/e`) are **banned** in dialogue and UI. `(e)` only in EULA/legal text if the bible allows it.

## 5. Plurals, Numbers & ICU
* **CLDR categories for `fr`.** `one` (**0 and 1**, plus decimals below 2 `1,5 jour`), `many` (only the compact million/billion forms `1 million de joueurs`), `other` (everything else). For game UI, treat it as **one / other** and remember **0 takes the singular**.

| `{0}` | French | Category |
|---|---|---|
| 0 | `0 objet` (better `Aucun objet`) | one |
| 1 | `1 objet` | one |
| 2 | `2 objets` | other |
| 5 | `5 objets` | other |
| 21 | `21 objets` | other |
| 1,5 | `1,5 objet` | one |

* **ICU.** `{count, plural, one {# objet} other {# objets}}`, note. `=0 {Aucun objet}` is the natural override.
* `{0} objet(s)` with brackets is **banned** in UI. Use ICU or two keys.
* **Numbers as words.** In dialogue, zero to ten in letters (`trois pièces`), digits above. In UI always digits. Ordinals. `1er`, `1re`, `2e`, `3e`, never `2ème`, `2nd` (unless exactly two).

## 6. Placeholder & Rich-Text Grammar Traps
* **Article + `{0}` = broken 50 % of the time.** `le {0}` fails on gender (`le épée`) and on elision (`le outil` → should be `l'outil`). `de {0}` → `d'`. `que {0}` → `qu'`. `à le {0}` → `au`. **Never attach an article, `de`, `que` or `à` directly to a placeholder.** Fix with a classifier noun or a colon. `l'objet {0}`, `la pièce {0}`, `Obtenu : {0}`, `{0} ajouté à l'inventaire` ✗ → `Ajouté à l'inventaire : {0}` ✓.
* **Adjective after placeholder.** `{0} équipé` ✗ (agreement unknown) → `Équipement : {0}` / `{0} — équipé` only if the bible fixes all items to one gender (it rarely can).
* **Number placeholders** follow §5 ICU. `%d objets` is the same trap in printf form.
* **Rich text.** The apostrophe belongs **inside** the tag with its word. `l'<b>outil</b>` ✗ → `<b>l'outil</b>` ✓. Keep the no-break space before `!?:;` **inside** the same tag as the punctuation's host word or outside both, never split `<b>Attention</b> !` across a line break. Tags must nest (`<b><color=red>x</color></b>`). The linter checks tag parity.
* **Concatenation ban.** `"Vous avez " + n + " objets"` cannot be reordered or pluralised in French. Demand a single string with placeholders.
* **Mandatory leading/trailing spaces** in the source (`"Appuyez sur "` + key) must be preserved exactly. Run `lqa_linter.py --strict-whitespace`.
* **Capitalised placeholder at sentence start.** `{0} est prêt` cannot be capitalised or agreed. Restructure (`Prêt : {0}`).
* **Engine-agnostic note.** Every rule above applies identically to Unity `{0}` / `{itemName}` + `<b>`/`<color=>`/`<sprite>`, Unreal `{Name}` / `|hpp(…)` / `<tag>…</>`, Godot `%s` / `%d` / BBCode `[b]…[/b]`, printf `%s %d %1$s`, Python-style `{name}` and ICU `{count, plural, …}`. The article/elision trap is about French, not about the brace style. Treat every placeholder syntax the project uses as an opaque token that cannot take an article, elision or agreement. Unreal `|plural(one=…, other=…)` and Godot `tr_n()` follow the same one/other split as §5.

## 7. Core UI Glossary
Button format. **Infinitive** for actions, **noun** for screens, **sentence case** (`Nouvelle partie`, never `Nouvelle Partie`), ALL CAPS only if the source is caps and the font has accented capitals. Keep buttons ≤ 12 characters where the layout is tight.

| English | `fr` (market standard) | Note |
|---|---|---|
| Save | `Sauvegarder` | `Enregistrer` = fr-CA / office software. |
| Load | `Charger` | `Chargement…` for the progress state. |
| Quit | `Quitter` | `Quitter la partie` / `Quitter le jeu`. |
| Settings / Options | `Paramètres` / `Options` | Pick one per project. |
| OK / Confirm | `OK` / `Confirmer` | `Valider` on forms. |
| Cancel | `Annuler` | |
| Back | `Retour` | Noun. Never `Revenir en arrière`. |
| Continue | `Continuer` | `Reprendre` = resume a saved game. |
| New Game | `Nouvelle partie` | |
| Apply | `Appliquer` | |
| Delete | `Supprimer` | `Effacer` for save slots is also common. |
| Yes / No | `Oui` / `Non` | |
| Pause | `Pause` | Noun on the menu title. `Mettre en pause` as action. |
| Resume | `Reprendre` | |
| Retry | `Réessayer` | |
| Skip | `Passer` | `Ignorer` for optional steps. |
| Inventory | `Inventaire` | |
| Equip | `Équiper` | Keep the accented capital. |
| Craft | `Fabriquer` | `Artisanat` for the menu/skill name. |
| Upgrade | `Améliorer` | `Amélioration` (noun). |
| Level | `Niveau` | `Niv.` abbreviation. |
| Health | `Santé` / `Vie` (`PV`) | `PV` = points de vie. |
| Stamina | `Endurance` | |
| Damage | `Dégâts` | Always plural. |
| Buy / Sell | `Acheter` / `Vendre` | |

## 8. Typography, Numbers & Formatting
* **Quotes.** `« … »` with a no-break space inside (`« Bonjour »`). Nested quotes `“ ”`. Fallback `“ ”` only if the font lacks guillemets, verify with `font_glyph_scanner.py`. Never straight `"` in dialogue.
* **Space before `? ! : ;` and before `%`, `€`.** Use **U+00A0 (no-break space)**. U+202F (narrow no-break) is typographically nicer but renders as tofu in many game fonts, only after a font check. A plain breaking space is **banned** (a line can start with `?`). No space before `,` `.` `…`.
* **Numbers.** Decimal comma, thousands no-break space. `1 234,56`. Currency after the number. `12,50 €`. Percent. `50 %`.
* **Date / time.** `26/11/2026` or `26 novembre 2026` (month lowercase). Time `14 h 30` in prose, `14:30` in UI.
* **Case.** Sentence case everywhere. **No Title Case**. Days, months, languages, nationalities-as-adjectives lowercase (`lundi`, `novembre`, `français`). Accented capitals are **mandatory** (`ÉQUIPER`, `À`, `PARAMÈTRES`, `REÇU`).
* **Apostrophe.** Lock one (`’` typographic preferred, `'` acceptable). Never mix. **Ellipsis.** Single `…` character. **Dashes.** `–` for ranges, `—` only for dialogue dashes in narrative prose.
* **Line breaking.** Never break before `?!:;»` (that is what U+00A0 is for). Disable hyphenation in UI. Long compounds may use a soft hyphen (U+00AD) only if the font supports it.

## 9. Text Expansion & UI Fit
* **Typical expansion vs. English. +15 % to +30 %** for sentences. Short labels can double (`ON` → `ACTIVÉ`, `Apply` → `Appliquer`, `Craft` → `Fabriquer`). Industry rule of thumb (IBM/W3C guidance). The shorter the source, the higher the ratio.
* **Shortening strategies, in order.** Drop articles in labels (`Niveau`, not `Le niveau`) → choose the shorter synonym (`Stock` vs `Inventaire`, `Retour` vs `Revenir`) → standard abbreviations with a period in tooltips only (`Param.`, `Niv.`, `PV`) → never abbreviate a button to a lone period or cut a word mid-way.
* Run `ui_expansion_checker.py --locale fr --fail-on-high`. The checker's locale table must carry the same +30 % ceiling as this section.

## 10. Ratings, Legal & Sensitive Content
* **Rating board.** **PEGI** (France applies PEGI via SELL, the label is required on retail and store pages). Descriptors matter for text. *Bad Language* at PEGI 12/16/18 depends on which words appear.
* **Loi Toubon (1994).** Every consumer-facing text for a product sold in France must exist in French, store page, manual, in-game UI and subtitles. Untranslated English UI is a legal risk, not just a quality one.
* **Profanity ladder (lock in bible).** `zut / mince` (PEGI 3 to 7) → `merde`, `bordel`, `con` (12) → `putain`, `foutre`, `connard` (16) → slurs never, at any rating.
* **Sensitive topics.** Blasphemy is neither a legal nor a rating issue in France, but religious mockery still needs lead sign-off for a global build. Political references (parties, 2005 riots, *gilets jaunes*) and Algeria/colonial history need lead sign-off. Drug references push to PEGI 16. Gambling mechanics (loot boxes) are watched by ANJ, keep *"chance de gain"* wording factual.
* **fr-CA.** ESRB applies, plus Québec consumer-protection rules on contests/loot boxes. Not covered here.

## 11. Golden Voice Anchors (A1 to A5)
Each pair keeps the **same meaning**. Only the voice changes. Roles are generic (the Mentor, the Rival…), never project names.

1. **A1 Mentor / Veteran (`tu`, passé composé, warm).**
   * *Robotic ✗:* `"Au milieu de la fabrication, il comprit ce qu'il construisait. Il détruisit tout et prit la fuite."`
   * *Natural ✓:* `"En plein montage, il a compris sur quoi il bossait vraiment. Il a tout démoli, jusqu'à la dernière pièce, et il a filé."`
2. **A2 Hotshot Rival (`tu`, cocky, fast).**
   * *Robotic ✗:* `"Les gens affirment que j'ai perdu mon avantage. C'est totalement faux. Répare le véhicule rapidement."`
   * *Natural ✓:* `"Tout le monde raconte que j'ai perdu la main. N'importe quoi ! Remets-moi la bécane d'aplomb, et vite."`
3. **A3 Rookie / Teen (`tu`, short, everyday slang).**
   * *Robotic ✗:* `"J'ai tenté de colmater la fuite à l'aide d'un produit d'étanchéité, cependant cela a fumé dès le décollage."`
   * *Natural ✓:* `"J'ai essayé de boucher la fuite avec du mastic, mais dès que ça a décollé, pouf, ça fumait de partout."`
4. **A4 Scientist / Engineer (`vous`, precise, still spoken).**
   * *Robotic ✗:* `"Il est nécessaire de procéder au remplacement du générateur avant la prochaine utilisation de l'appareil."`
   * *Natural ✓:* `"Changez le générateur avant de relancer l'appareil."`
5. **A5 Outlaw / Antagonist (cold `vous`, short, gender-safe).**
   * *Robotic ✗:* `"Il m'a été rapporté que vous avez pris contact avec les autorités. Il serait regrettable que votre situation se complique."`
   * *Natural ✓:* `"On m'a dit que vous aviez parlé aux autorités. Ce serait dommage que ça se complique pour vous."`

## 12. Linter Coverage Note
Currently in `lqa_linter.py` for `fr`: `focuser` (ERR), `procéder à` (WARN), `effectuer` (WARN), median dot `·` (ERR). Everything else in §1, §4, §6 and §8 is **not** yet enforced.

**Suggested linter patterns (regex-friendly, for the scripts owner).**
* ERR `\b(?:le|la|les|du|de la|des|un|une|au|aux)\s+\{\w+\}`, article/preposition glued to a placeholder (§6). Extend the brace form to the project's placeholder syntax (`%s`, `%1$s`, `{Name}`).
* WARN `\x20[?!:;]`, ordinary breaking space before `?!:;` (should be U+00A0). Do **not** flag a *missing* space. Keyboard shortcuts like `F1:` are legitimate.
* WARN `\u202F`, narrow no-break space. Only after font verification.
* WARN `\bposs[ée]dez\b|\bpossèdes\b`, *posséder* → *avoir*.
* WARN `\bse trouve (?:déjà )?(?:un|une|à)\b` and `\bà cet (?:endroit|emplacement)\b`, manual-speak.
* WARN `\bavec succès\b`, calque of *successfully*.
* WARN `\bveuillez\b.*\bs'il vous pla[iî]t\b`, doubled politeness.
* WARN `\bil est recommandé de\b`, impersonal notice tone.
* WARN `\b\w+(?:èrent|irent|urent|âmes|îmes|ûmes|âtes|îtes|ûtes)\b`, passé simple endings in dialogue/UI categories only.
* WARN `\b(?:tu es|vous êtes) (?:prêt|sûr|certain|devenu)\b`, gendered predicate about the player.
* WARN `\bBienvenu\b`, missing *-e* on the interjection (`Bienvenue` does not match because of the word boundary).
* ERR `\bOBTENIR LES OBJETS\b`, `\bDéplacer vers\b`, literal keybinding/loot labels.
* WARN `\w\(e\)s?\b|\b\w+/e\b`, bracketed or slashed gender hacks (`prêt(e)`, `prêt/e`) in non-legal categories.
