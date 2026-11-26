# European Portuguese (`pt-PT`) Game Localization & Culturalization Playbook

> **Scope note.** `pt-PT` = Portuguese for Portugal (PEGI territory). Brazilian Portuguese is a separate locale with its own playbook (`pt-BR.md`). The two must never share a string table. Portuguese players notice a single Brazilianism instantly and rate the build down for it.

Target feel. **Português europeu autêntico, natural e coloquial, com terminologia gamer de Portugal**, zero `pt-BR` leakage, zero bureaucratic prose, zero calques from English.

## 1. Anti-Translationese Ban List
| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `Carregando` / `Montando` / `Salvando` | `A carregar` / `A montar` / `A guardar` | Progressive is `a` + infinitive in Portugal. The gerund is `pt-BR`. |
| `Configurações` / `Salvar` / `Tela` / `Usuário` / `Controle` | `Definições` / `Guardar` / `Ecrã` / `Utilizador` / `Comando` | `pt-BR` lexicon. |
| `Me ajuda` / `Te mandei` / `Consertar ela` | `Ajuda-me` / `Mandei-te` / `Repará-la` | Clitic placement (§2). `consertar` is markedly `pt-BR`, Portugal says *reparar / arranjar*. |
| `Você tem` (casual) | `Tens` | Casual *you* is `tu`, verb in 2nd person. |
| `Você` written out (formal) | implicit 3rd person. `Tem`, `Pode`, `A sua oficina` | Explicit `você` sounds blunt or condescending in Portugal (§2). |
| `Focar` (interact prompt) | `Usar` / `Interagir` | Literal *focus*. |
| `Este item não pode ser colocado aqui.` | `Isto não encaixa aqui.` / `Não podes pôr isto aqui.` | English passive. |
| `Já se encontra um objeto neste local!` | `Este lugar já está ocupado!` / `Já está aqui uma peça!` | *Encontra-se* + *local* = notice board. |
| `Já possuis esta ferramenta!` | `Já tens esta ferramenta!` | *Possuir* is formal. Spoken says *ter*. |
| `OBTER ITENS` | `RECOLHER TUDO` | Literal *GET ITEMS*. |
| `Guardado com sucesso.` | `Jogo guardado.` / `Guardado!` | *Com sucesso* is a calque of *successfully*. |
| `Por favor, aguarde por favor.` | `Aguarde…` / `Um momento…` | Doubled politeness. |
| `aí fora` for a vague *out there* | drop it, or `por aí` | Literal. Needs a real "outside". |
| `Realizar a compra` / `Efetuar login` | `Comprar` / `Iniciar sessão` | Corporate verbs. |

## 2. Register, Address & Character Voice
* **Casual `tu`** (verb in 2nd person singular, pronoun usually omitted `Tens`, `Podes`, `O teu`). Mentor, rival, rookie, friends, and mentor-voiced tutorials if the bible says so.
* **Formal address = implicit 3rd person, never the word `você`.** In Portugal, writing `você` sounds stiff or condescending, and `o senhor / a senhora` forces a gender guess. The native solution is **dropping the subject and using 3rd-person singular verb + `o seu / a sua`**. `Espero que esteja tudo bem consigo`, `Envio-lhe o esquema`, `A sua oficina tem boa fama`. This is 100 % authentic polite `pt-PT` **and** 100 % gender-neutral. `o senhor / a senhora` only when the addressee's gender is known (NPC → NPC).
* **Plural `vocês`** is the normal, neutral plural (`Vocês conseguem`). `vós` is regional/liturgical, never in UI.
* **Clitic placement (enclisis / proclisis).** Affirmative main clause → **enclisis** (`Mandei-te`, `Ajuda-me`, `Dá-me isso`). After negation, question words, subordinators and some adverbs → **proclisis** (`Não te mandei`, `Já te disse`, `Quando me ajudares`). Never start a sentence with a clitic (`Me ajuda` = `pt-BR`). Infinitive + `-lo/-la`: `repará-la`, `fazê-lo`. Mesoclisis (`dir-te-ei`) is literary, use `vou dizer-te`.
* **Layers, locked in `PT-PT_BIBLE.md`. Never mix inside one layer.**
  1. **Buttons / menu labels.** Infinitive (§7), no pronoun at all.
  2. **System prose & tutorials.** **Impersonal 3rd person** is the platform default (`Tem a certeza de que pretende sair?`, `Prima para continuar`). A mentor-voiced tutorial may use `tu` (`Carrega em…`) if locked. Either way, the word `você` never appears.
  3. **Character dialogue.** A1 Mentor → `tu`. A2 Rival → `tu`. A3 Rookie → `tu`. A4 Scientist → implicit 3rd person toward a client. A5 Antagonist → cold implicit 3rd person.
* **Spoken warmth.** `Olha`, `Pá` (lightly), `Então`, `Pois`, `desenrascar` / `um desenrascanço` (*improvised fix*, quintessential), `aguentar o barco`, `pôr isto a andar`, `dar cabo de`, `uma treta`, `fixe` (casual only).

## 3. Spoken vs. Literary Tense
* **No spoken/literary split like French or Italian.** The **pretérito perfeito simples** (`fiz`, `tentei`, `desapareceu`) covers recent and distant past, in dialogue and in lore.
* **Spanish contamination trap.** `tenho feito` ≠ `he hecho`. It means a repeated/ongoing action (`Tenho trabalhado muito`). One completed event is `Tentei`, never `Tenho tentado`.
* **Pluperfect.** Spoken = `tinha feito`. The simple `fizera` only in lore/narration.
* **Progressive = `estar a` + infinitive.** `Estou a fazer`, `A carregar…`, the gerund (`fazendo`) is `pt-BR` (and Alentejo/Algarve dialect, never in UI).
* **Future.** Spoken = `vou fazer`. `farei` in formal letters/UI (`A alteração será aplicada ao reiniciar`). Futuro do conjuntivo is alive and required. `quando chegares`, `se puder`.

## 4. Player Gender Neutrality
Portuguese marks gender on **adjectives, participles with `ser/estar/ficar`, role nouns, articles, and the player's own `obrigado/obrigada`**. The player's gender is unknown.

| Leaks ✗ | Neutral ✓ | Strategy |
|---|---|---|
| `Bem-vindo!` | `Boas-vindas!` / `É bom ter-te cá!` (`tu`) | Noun, or `te` (no agreement). `tê-lo / tê-la` would leak. |
| `Estás pronto?` | `Tudo pronto?` / `Vamos a isto?` | Move the adjective to a thing. |
| `Tornaste-te um verdadeiro mecânico.` | `Já dominas o ofício.` / `Já não há quem te bata na oficina.` | No role noun with an article (`um ás`, `um mecânico`). |
| `Foste selecionado.` | `Passaste na seleção.` / `Seleção concluída.` | `ter` + participle never agrees. `ser/estar` does. |
| `Obrigado!` (player-voiced) | `Agradeço!` / `Fico a dever-te uma!` | The player never says *obrigado/a*. |
| `Estás cansado.` | `Estás sem fôlego.` / `Energia esgotada.` | Prepositional phrase. |
| `Jogador` / `Aliado` | `Perfil` / `Aliança` | Abstract nouns. |
| `Então, rapaz / miúdo / filho / querido` | `Então, pá` / `Então, chefe` / nickname from the bible | *Pá* and *chefe* are invariant in address. `miúdo/a`, `querido/a` are not. |
| `Caro(a) utilizador(a)` | `Olá!` | Never `(a)`, `x`, `@`, `e` endings in UI or dialogue. |

* **Safe compound tenses.** `ter` + participle is invariant, `Ganhaste`, `Reparaste tudo`, `Tinhas avisado` are safe. So are indirect objects (`Enviei-lhe`, `Deu-me`). The trap is `ser/estar/ficar/andar` + participle/adjective.
* **Invariant adjectives.** `capaz`, `forte`, `ágil`, `incrível`, `imbatível`, `de confiança`, `impecável`, `fixe`. Nouns with an article (`um ás`, `uma fera`) leak gender through the article, avoid.

## 5. Plurals, Numbers & ICU
* **CLDR categories for `pt-PT`.** `one` (**exactly 1**), `many` (compact millions `1 milhão de`), `other` (everything else, **including 0 and decimals**). **Note the difference from `pt-BR`, where 0 and 1,5 are `one`.**

| `{0}` | pt-PT | Category |
|---|---|---|
| 0 | `0 itens` (better `Nenhum item`) | other |
| 1 | `1 item` | one |
| 2 | `2 itens` | other |
| 5 | `5 itens` | other |
| 21 | `21 itens` | other |
| 1,5 | `1,5 itens` | other |

* **ICU.** `{count, plural, one {# item} other {# itens}}`. `=0 {Nenhum item}` is the natural override.
* `item(ns)` with brackets is banned in UI. Spelling. `item / itens`. `nível / níveis`. `mão / mãos`. `cão / cães`.
* **Numbers as words.** Zero to nine in letters inside dialogue, digits in UI. Ordinals. `1.º`, `2.ª` (with the period, Portuguese norm), never `1o`.

## 6. Placeholder & Rich-Text Grammar Traps
* **Article + `{0}` breaks on gender and contraction.** `o {0}` → `o espada` ✗. `de o {0}` ✗ (`do`), `em a {0}` ✗ (`na`), `a a {0}` ✗ (`à`), `por o {0}` ✗ (`pelo`). **Never glue `o/a/um/uma/do/da/no/na/ao/à/pelo/pela` to a placeholder.** Use a classifier noun or a colon. `o item {0}`, `a peça {0}`, `Obtido: {0}`, `Equipar: {0}`.
* **Adjective / participle after placeholder.** `{0} equipado` ✗ → `Equipaste: {0}` ✓ (invariant) or `Equipamento: {0}`.
* **Clitic + placeholder.** `Repará-{0}` is impossible. Restructure (`Reparar: {0}`).
* **Number placeholders** follow §5 ICU. `%d itens` is the same trap in printf form.
* **Rich text.** Keep hyphenated verbs whole inside a tag (`<b>Ajuda-me</b>`, never `<b>Ajuda</b>-me`). Never split at an accent. Tags must nest. The linter checks parity.
* **Concatenation ban.** `"Tens " + n + " itens"` cannot be pluralised or reordered. Demand one string with placeholders.
* **Leading/trailing spaces** required by the source (`"Prime "` + key) must be preserved. Run `lqa_linter.py --strict-whitespace`.
* **Engine-agnostic note.** The rules apply identically to Unity `{0}` / `{itemName}` + `<b>`/`<color=>`/`<sprite>`, Unreal `{Name}` / `|hpp(…)` / `<tag>…</>`, Godot `%s` / `%d` / BBCode `[b]…[/b]`, printf `%s %1$s`, Python-style `{name}` and ICU `{count, plural, …}`. Treat every placeholder syntax as an opaque token that cannot take an article, contraction or agreement. Unreal `|plural(one=…, other=…)` and Godot `tr_n()` follow the same one/other split as §5.

## 7. Core UI Glossary
Button format. **Infinitive** for actions, **noun** for screens, **sentence case** (`Novo jogo`, never `Novo Jogo`), ALL CAPS only if the source is caps and the font has `Ã Ç É Ú`. Never the `tu` imperative on buttons (`Guarda` ✗), that is for mentor dialogue only.

| English | `pt-PT` (market standard) | Note |
|---|---|---|
| Save | `Guardar` | `Salvar` ✗ (`pt-BR`). |
| Load | `Carregar` | `A carregar…` for the progress state. |
| Quit | `Sair` | `Sair do jogo` / `Voltar ao menu`. |
| Settings / Options | `Definições` / `Opções` | Pick one. `Configurações` ✗. |
| OK / Confirm | `OK` / `Confirmar` | |
| Cancel | `Cancelar` | |
| Back | `Voltar` / `Retroceder` | `Voltar` is shorter. |
| Continue | `Continuar` | |
| New Game | `Novo jogo` | `Jogar` for the main Play button. |
| Apply | `Aplicar` | |
| Delete | `Eliminar` | `Apagar` also common. `Deletar` ✗. |
| Yes / No | `Sim` / `Não` | |
| Pause | `Pausa` | Noun as menu title. |
| Resume | `Retomar` | `Continuar` on the pause menu is also standard. |
| Retry | `Tentar novamente` | `Repetir` for levels. |
| Skip | `Saltar` / `Ignorar` | `Saltar` for cutscenes. |
| Inventory | `Inventário` | |
| Equip | `Equipar` | |
| Craft | `Criar` / `Fabricar` | `Criação` for the menu. |
| Upgrade | `Melhorar` | `Melhoria` (noun). |
| Level | `Nível` | `Nv.` abbreviation. |
| Health | `Vida` / `Saúde` (`PV`) | Pick one per bible. |
| Stamina | `Energia` / `Resistência` | Lock one. `fôlego` is the spoken word. |
| Damage | `Dano` | Singular. |
| Buy / Sell | `Comprar` / `Vender` | |

Other high-frequency `pt-BR` → `pt-PT` swaps. `Tela` → `Ecrã`, `Mouse` → `Rato`, `Arquivo` → `Ficheiro`, `Time` → `Equipa`, `Usuário` → `Utilizador`, `Controle` → `Comando`, `Fazer login` → `Iniciar sessão`, `Celular` → `Telemóvel`, `Ônibus` → `Autocarro`.

## 8. Typography, Numbers & Formatting
* **Quotes.** `«…»` is the primary quotation mark in Portuguese publishing. `“…”` nested, and many games lock `“ ”` as primary for font reasons, lock one. Never straight `"` in dialogue.
* **Numbers.** Decimal comma, thousands no-break space (`1 234,56`, a point `1.234,56` is also seen, lock one). Currency after the number with a space. `12,50 €`. Percent. `50%` (no space) is the common game convention.
* **Date / time.** `26/11/2026` or `26 de novembro de 2026` (month lowercase). Time `14h30` in prose, `14:30` in UI.
* **Case.** Sentence case. **No Title Case**. Days, months, languages lowercase (`segunda-feira`, `novembro`, `português`). Accented capitals mandatory (`AÇÃO`, `ÚLTIMO`, `É`).
* **Spelling, AO90 (in force in Portugal).** `ação`, `ótimo`, `elétrico`, `económico` (PT keeps the open vowel `ó`, not BR `ô`), `receção`, `espetador`, `aspeto`, `húmido`. Consonants that are **pronounced** stay. `facto`, `contacto`, `pacto`, `compacto`. `fato` in Portugal means *suit*, not *fact*.
* **Ellipsis.** Single `…`. **Dashes.** `—` (travessão) for dialogue in narrative prose. No space before `? ! : ;`.
* **Line breaking.** Keep `12,50 €` and `1 234` together with no-break spaces. Never break a hyphenated clitic verb at the hyphen.

## 9. Text Expansion & UI Fit
* **Typical expansion vs. English. +15 % to +30 %**. Short labels can double (`ON` → `LIGADO`, `Retry` → `Tentar novamente`, `Settings` → `Definições`). Industry rule of thumb (IBM/W3C). The shorter the source, the higher the ratio.
* **Shortening, in order.** Drop articles in labels (`Nível`, not `O nível`) → shorter synonym (`Voltar` vs `Retroceder`, `Repetir` vs `Tentar novamente`) → standard abbreviations in tooltips only (`Nv.`, `PV`, `Defin.`) → never cut a word mid-way or drop an accent.
* Run `ui_expansion_checker.py --locale pt-PT --fail-on-high`. The checker's locale table must carry the same +30 % ceiling as this section.

## 10. Ratings, Legal & Sensitive Content
* **Rating board.** **PEGI** (Portugal applies PEGI, IGAC handles film/other media classification). *Bad Language* thresholds decide which words survive.
* **Profanity ladder (lock in bible).** `bolas / raios / chiça` (PEGI 3 to 7) → `merda`, `porra` (milder in Portugal than in Brazil, 12 to 16), `foda-se` (16) → `caralho`, `filho da puta`, `cabrão` (16 to 18) → slurs never.
* **Sensitive topics.** The Estado Novo and Salazar, the Colonial War and decolonisation, Fátima/Catholic imagery, Lisbon to Porto rivalry (fine in jest), Spain jokes (fine in jest). Avoid presenting Brazilian speech as "wrong" inside the game world, a `pt-BR` character may speak `pt-BR`.
* **Legal.** Consumer law requires Portuguese on store pages and manuals. Gambling-like mechanics fall under the SRIJ (Serviço de Regulação e Inspeção de Jogos), keep odds wording factual (`probabilidade`).

## 11. Golden Voice Anchors (A1 to A5)
Each pair keeps the **same meaning**. Only the voice changes. Roles are generic (the Mentor, the Rival…), never project names.

1. **A1 Mentor / Veteran (`tu`, warm).**
   * *Robotic ✗ (`pt-BR`-contaminated):* `"Comece com o que você puder reciclar e coloque o lugar funcionando novamente. Farei algumas ligações em seu benefício."`
   * *Natural ✓:* `"Começa por aproveitar o que conseguires recuperar da sucata e põe a oficina outra vez a andar. Depois faço uns telefonemas por ti."`
2. **A2 Hotshot Rival (`tu`, cocky, fast).**
   * *Robotic ✗:* `"As pessoas continuam a afirmar que perdi a minha vantagem. Repare o veículo tão rápido quanto possível."`
   * *Natural ✓:* `"Andam para aí a dizer que já não tenho unhas para isto. Que grande treta! Põe-me a máquina impecável, e depressa."`
3. **A3 Rookie / Teen (`tu`, short, everyday slang).**
   * *Robotic ✗:* `"Tentei vedar a fuga utilizando um vedante, porém o material descolou-se durante a descolagem."`
   * *Natural ✓:* `"Ainda tentei tapar a fuga com massa, mas mal a nave levantou, descolou-se tudo."`
4. **A4 Scientist / Engineer (implicit 3rd person toward a client, precise but spoken).**
   * *Robotic ✗:* `"Torna-se necessário proceder à substituição do gerador antes da próxima utilização do aparelho."`
   * *Natural ✓:* `"Substitua o gerador antes de voltar a ligar o aparelho."`
5. **A5 Outlaw / Antagonist (cold implicit 3rd person, short, gender-safe).**
   * *Robotic ✗:* `"Foi-me comunicado que você estabeleceu contacto com as autoridades. Seria lamentável que a sua situação se complicasse."`
   * *Natural ✓:* `"Constou-me que falou com as autoridades. Teria muita pena que as coisas se complicassem."`

## 12. Linter Coverage Note
Currently in `lqa_linter.py` for `pt-PT`: `Configurações|Usuário` (ERR), `Carregando|Salvando|Montando|Desmontando|Transferindo` (ERR), `Você` (WARN, **case-sensitive, `você` escapes, make it `re.I`**). Everything else in §1, §4, §6 and §8 is **not** yet enforced.

**Suggested linter patterns (regex-friendly, low false-positive risk, for the scripts owner).**
* ERR `\b(?:o|a|os|as|um|uma|do|da|no|na|ao|à|pelo|pela)\s+\{\w+\}`, article/contraction glued to a placeholder (§6).
* ERR `\b(?:Tela|Mouse|Arquivo|Deletar|Time|Controle|Salvar|Usuário|Celular|Ônibus)\b` (case-insensitive), `pt-BR` lexicon.
* ERR `^\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇ]\w+(?:ando|endo|indo)\b` in UI categories, a gerund progress label at string start (`Carregando…`, `Transferindo itens`). Plain `\w+ndo` is too noisy (`quando`, `segundo`, `mundo`). Extend the existing explicit list rather than replacing it.
* WARN `^\s*(?:Me|Te|Se|Lhe|Nos)\s+\w+`, sentence-initial clitic (`pt-BR` proclisis).
* WARN `\b\w+(?:ar|er|ir)\s+(?:ele|ela|eles|elas)\b`, object pronoun after infinitive (`consertar ela`).
* ERR `\bcontato\b|\bOBTER ITENS\b|\bMover para\b`. WARN `\baspecto\b` (→ `aspeto`), `\bfato\b` when meaning *fact* (keep WARN *fato* = suit is legitimate).
* WARN `\bnão pode ser \w+ad[oa]s?\b`, English passive. WARN `\bJá se encontra\b`.
* WARN `\bcom sucesso\b`, calque of *successfully*.
* WARN `\bBem-vind[oa]s?\b`, use `Boas-vindas`. WARN `\w\([ao]\)`, bracketed gender hacks (`Caro(a)`, `jogador(a)`).
* WARN `\bObrigad[oa]\b` in player-voiced categories only.
* WARN `\b(?:Estás|És|Foste|Ficaste) \w+(?:ado|ido|oso)\b`, gendered predicate about the player.
* WARN `\b[Tt]enho \w+(?:ado|ido)\b`, Spanish-perfect contamination (expect legitimate "I've been …" hits, keep WARN).
