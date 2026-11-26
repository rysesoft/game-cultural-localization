# Brazilian Portuguese (`pt-BR`) Game Localization & Culturalization Playbook

> **Scope note:** `pt-BR` = Brazilian Portuguese, the largest Portuguese-speaking game market and a **ClassInd** territory (§10). European Portuguese is a separate locale with its own playbook (`pt-PT.md`); the two must never share a string table. Cross-contamination from Spanish (same team, same day) is a real risk — see the `tenho feito` warning in §3.

Target feel: **português brasileiro falado, caloroso, fluido e natural, com vocabulário gamer do Brasil** — never `pt-PT` Lusitanisms, never stiff corporate/legal Portuguese, never a calque of the English rhythm.

## 1. Anti-Translationese Ban List
| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `Definições` / `Guardar` / `Ecrã` / `A carregar` | `Configurações` / `Salvar` / `Tela` / `Carregando` | `pt-PT` leakage. |
| `Focar` (interact prompt) | `Usar` / `Interagir` | Literal *focus*. |
| `Este item não pode ser colocado neste local.` | `Isso não encaixa aqui.` / `Não dá para colocar isso aqui.` | English passive + *neste local*. |
| `Já existe um item neste local!` | `Esse espaço já está ocupado!` / `Já tem algo aqui!` | *Existe* + *local* = notice board. |
| `Você já possui esta ferramenta!` | `Você já tem essa ferramenta!` | *Possuir* is formal; spoken Brazilian says *ter*. |
| `Sua resistência está muito baixa!` | `Você está sem fôlego!` / `Sem energia!` | Stat report → player line (`Falta disposição` ✗ — *disposição* is mood, not stamina). |
| `OBTER ITENS` | `PEGAR TUDO` / `COLETAR` | Literal *GET ITEMS*. |
| `Mover para a frente / para a esquerda` | `Avançar` / `Recuar` / `Esquerda` / `Direita` | Keybinding labels are one word. |
| `Efetuar o reparo` / `Comercializar` | `Consertar` / `Vender` | Nominalised or corporate verb. |
| `Salvo com sucesso.` / `exitosamente` | `Jogo salvo.` / `Salvo!` | *Com sucesso* is a calque of *successfully*; *exitosamente* is Spanish. |
| `Por favor, aguarde por favor.` | `Aguarde…` / `Um momento…` | Doubled politeness. |
| `aí fora` for a vague *out there* | drop it, or `por aí` | *Aí fora* is literal and needs a real "outside". |
| `Realizar a compra` / `Efetuar login` | `Comprar` / `Entrar` | Corporate verbs. |
| `Tenho tentado…` for *I have tried* (once) | `Tentei…` | Spanish-perfect contamination (§3). |

## 2. Register, Address & Character Voice
* **`você` + 3rd-person verb is the universal standard** (`você faz`, `você tem`, `seu/sua`): UI, tutorials, friends, family, rivals, officials. It is warm **and** gender-safe. `a gente` = *we* in speech (`A gente dá um jeito`).
* **`tu`** exists regionally (South, North-east, North; usually with 3rd-person verb: `tu vai`). In game text it is allowed **only** as a locked voice trait for one character (e.g. a *gaúcho*), never in UI.
* **Colloquial imperative in dialogue:** spoken Brazilian uses the indicative form as imperative (`Pega isso`, `Bota aí`, `Deixa comigo`) even while saying `você` — this is authentic, not a register error, and is **allowed in NPC dialogue**. In UI, tutorials and system prose use the grammatical `você` imperative: `Pegue`, `Coloque`, `Deixe`. Lock this split in `PT-BR_BIBLE.md` so the blind critic does not flag it.
* **`o senhor / a senhora`** only when the gender of the addressee is known (NPC → NPC). Toward the player, respectful `você` with clean framing (`Olá`, `Agradeço sua ajuda`) replaces it — never `Prezado(a)`.
* **Layers, locked in the bible:**
  1. **Buttons / menu labels:** infinitive (§7).
  2. **System prose & tutorials:** `você` with grammatical imperative (`Deseja sair?` / `Quer sair?`, `Pressione para continuar`).
  3. **Character dialogue:** A1 Mentor → colloquial `você`; A2 Rival → colloquial `você`; A3 Rookie → colloquial `você`, short sentences; A4 Scientist → clean `você`; A5 Antagonist → cold, formal `você`.
* **Spoken warmth without dated meme slang:** `Olha só`, `Pois é`, `Pra falar a verdade`, `dar um jeito`, `segurar as pontas`, `ficar de olho`, `gambiarra` (*duct-tape fix* — iconic), `tá`, `né`, `a gente`. `pra` / `tá` / `né` only in dialogue, never in UI.

## 3. Spoken vs. Literary Tense
* **No spoken/literary split like French or Italian.** The **pretérito perfeito simples** (`fiz`, `tentei`, `sumiu`) covers recent and distant past alike, in dialogue and in lore. Do not look for a "spoken" alternative.
* **Spanish contamination trap:** `tenho feito` is **not** `he hecho`. The Portuguese *pretérito perfeito composto* means a repeated or ongoing action up to now (`Tenho trabalhado muito` = *I've been working a lot*). A single completed event is `Tentei`, never `Tenho tentado`.
* **Pluperfect:** spoken = `tinha feito`; the simple form `fizera` is literary and belongs only in lore/narration.
* **Future:** spoken = `vou fazer`; `farei` in formal letters and UI promises (`A alteração será aplicada ao reiniciar`). Futuro do subjuntivo is alive and required: `quando você chegar`, `se você puder` — never the indicative there.
* **Progressive = gerúndio:** `Carregando…`, `Montando…`, `Transferindo itens` — never `A carregar` (`pt-PT`).

## 4. Player Gender Neutrality
Portuguese marks gender on **adjectives, participles with `ser/estar/ficar`, role nouns, articles, and the player's own `obrigado/obrigada`**. The player's gender is unknown.

| Leaks ✗ | Neutral ✓ | Strategy |
|---|---|---|
| `Bem-vindo!` | `Boas-vindas!` / `Que bom ter você aqui!` | Noun or clause. |
| `Você está pronto?` | `Tudo pronto?` / `Vamos nessa?` | Move the adjective to a thing. |
| `Você se tornou um verdadeiro mecânico.` | `Você já é fera na oficina.` / `Você já domina o ofício.` | *Fera* is invariant; no role noun. |
| `Você foi selecionado.` | `Você passou na seleção.` / `Seleção concluída.` | `ter` + participle never agrees; `ser/estar` does. |
| `Obrigado!` (player-voiced) | `Valeu!` / `Agradeço!` | The player never says *obrigado/a* (nor *agradecido/a*); use `valeu` or a verb. |
| `Você está cansado.` | `Você está sem fôlego.` / `Energia esgotada.` | Prepositional phrase. |
| `Jogador` / `Aliado` / `Parceiro` | `Perfil` / `Aliança` / `Parceria` | Abstract nouns. |
| `E aí, cara / mano / garoto / filho / campeão` | `E aí, craque` / `E aí` / nickname from the bible | *Craque, fera, gente* are invariant; `parceiro/a` is not. |
| `Prezado(a) jogador(a)` | `Olá!` / `Oi!` | Never `(a)`, `x`, `@`, `e` endings in UI or dialogue. |

* **Safe compound tenses:** `ter` + participle is invariant — `Você ganhou`, `Você consertou tudo`, `Você tinha avisado` are safe. The trap is `ser/estar/ficar/andar` + participle/adjective.
* **Invariant adjectives:** `capaz`, `forte`, `ágil`, `fera`, `incrível`, `imbatível`, `de confiança`, `sensacional`.

## 5. Plurals, Numbers & ICU
* **CLDR categories for `pt` (Brazil):** `one` (**0 and 1**, plus decimals below 2: `1,5 dia`), `many` (compact millions: `1 milhão de`), `other` (everything else). **Note the difference from `pt-PT`, where 0 is `other`.** Many Brazilian studios still write `0 itens` by convention — lock one in the bible; the natural fix is `Nenhum item`.

| `{0}` | pt-BR | Category |
|---|---|---|
| 0 | `0 item` (CLDR) — better: `Nenhum item` | one |
| 1 | `1 item` | one |
| 2 | `2 itens` | other |
| 5 | `5 itens` | other |
| 21 | `21 itens` | other |
| 1,5 | `1,5 item` | one |

* **ICU:** `{count, plural, one {# item} other {# itens}}`; `=0 {Nenhum item}` is the natural override.
* `item(ns)` / `item(s)` with brackets is banned in UI. Spelling: `item / itens` (no accent, `-ns` plural); `nível / níveis`, `mão / mãos`, `cão / cães`, `pão / pães`.
* **Numbers as words:** zero to nine in letters inside dialogue, digits in UI. Ordinals: `1º`, `2ª`, `3º` (with the ordinal indicator) — never `1o`, `2a`.

## 6. Placeholder & Rich-Text Grammar Traps
* **Article + `{0}` breaks on gender and contraction:** `o {0}` → `o espada` ✗; `de o {0}` ✗ (must be `do`), `em a {0}` ✗ (`na`), `a a {0}` ✗ (`à`, crase), `por o {0}` ✗ (`pelo`). **Never glue `o/a/um/uma/do/da/no/na/ao/à/pelo/pela` to a placeholder.** Use a classifier noun or a colon: `o item {0}`, `a peça {0}`, `Obtido: {0}`, `Equipar: {0}`.
* **Adjective / participle after placeholder:** `{0} equipado` ✗ → `Você equipou: {0}` ✓ (`ter`-style, invariant) or `Equipamento: {0}`.
* **Number placeholders** follow §5 ICU; `%d itens` is the same trap in printf form.
* **Rich text:** keep hyphenated words whole inside a tag (`<b>bem-vindas</b>`, never `<b>bem</b>-vindas`); never split at an accent. Tags must nest; the linter checks parity.
* **Concatenation ban:** `"Você tem " + n + " itens"` cannot be pluralised or reordered; demand one string with placeholders.
* **Leading/trailing spaces** required by the source (`"Pressione "` + key) must be preserved; run `lqa_linter.py --strict-whitespace`.
* **Engine-agnostic note:** the rules apply identically to Unity `{0}` / `{itemName}` + `<b>`/`<color=>`/`<sprite>`, Unreal `{Name}` / `|hpp(…)` / `<tag>…</>`, Godot `%s` / `%d` / BBCode `[b]…[/b]`, printf `%s %1$s`, Python-style `{name}` and ICU `{count, plural, …}`. Treat every placeholder syntax as an opaque token that cannot take an article, contraction or agreement; Unreal `|plural(one=…, other=…)` and Godot `tr_n()` follow the same one/other split as §5.

## 7. Core UI Glossary
Button format: **infinitive** for actions, **noun** for screens, **sentence case** (`Novo jogo`, never `Novo Jogo`), ALL CAPS only if the source is caps and the font has `Ã Ç É Ú`. Never the imperative on buttons (`Salve` ✗).

| English | `pt-BR` (market standard) | Note |
|---|---|---|
| Save | `Salvar` | `Guardar` ✗ (`pt-PT`; in Brazil *guardar* = store away). |
| Load | `Carregar` | `Carregando…` for the progress state. |
| Quit | `Sair` | `Sair do jogo` / `Voltar ao menu`. |
| Settings / Options | `Configurações` / `Opções` | Pick one; `Definições` ✗. |
| OK / Confirm | `OK` / `Confirmar` | |
| Cancel | `Cancelar` | |
| Back | `Voltar` | |
| Continue | `Continuar` | |
| New Game | `Novo jogo` | `Jogar` for the main Play button. |
| Apply | `Aplicar` | |
| Delete | `Excluir` | `Apagar` also common; `Deletar` only if the bible allows it. |
| Yes / No | `Sim` / `Não` | |
| Pause | `Pausa` / `Pausar` | Noun as menu title, verb as action. |
| Resume | `Retomar` / `Continuar` | |
| Retry | `Tentar novamente` | `Repetir` for levels. |
| Skip | `Pular` | `Ignorar` for optional steps. |
| Inventory | `Inventário` | |
| Equip | `Equipar` | |
| Craft | `Criar` / `Fabricar` | `Criação` for the menu. |
| Upgrade | `Melhorar` / `Aprimorar` | `Melhoria` (noun). |
| Level | `Nível` | `Nv.` abbreviation. |
| Health | `Vida` / `Saúde` (`HP`) | `HP` is widely understood in Brazil. |
| Stamina | `Fôlego` / `Energia` / `Estamina` | Lock one; `Resistência` is also used as a stat name. |
| Damage | `Dano` | Singular. |
| Buy / Sell | `Comprar` / `Vender` | |

## 8. Typography, Numbers & Formatting
* **Quotes:** `“…”` primary, `‘…’` nested (Brazil does not use `«»`). Never straight `"` in dialogue. Apostrophe `’` or `'` — lock one.
* **Numbers:** decimal comma, thousands point: `1.234,56`; currency **before** the number with a space: `R$ 1.234,56`; percent without space: `50%`.
* **Date / time:** `26/11/2026` or `26 de novembro de 2026` (month lowercase); time `14h30` in prose, `14:30` in UI.
* **Case:** sentence case; **no Title Case**; days, months, languages, nationalities lowercase (`segunda-feira`, `novembro`, `português`). Accented capitals mandatory (`AÇÃO`, `ÚLTIMO`, `É`).
* **Spelling:** AO90 is the law in Brazil since 2016 (`ideia`, `voo`, `autoescola`, `bem-vindo`, `anti-inflamatório`); `tem/têm`, `pôde/pode`, `pôr/por` accents kept. Brazil keeps `fato`, `contato`, `aspecto`, `úmido`, `recepção` (unlike `pt-PT`).
* **Ellipsis:** single `…`. **Dashes:** `—` (travessão) for dialogue in narrative prose; no space before `? ! : ;`.
* **Line breaking:** keep `R$ 1.234,56` together with a no-break space; never break a hyphenated word at the hyphen inside UI labels.

## 9. Text Expansion & UI Fit
* **Typical expansion vs. English: +15 % to +30 %**; short labels can double (`ON` → `ATIVADO`, `Retry` → `Tentar novamente`, `Settings` → `Configurações`). Industry rule of thumb (IBM/W3C): the shorter the source, the higher the ratio.
* **Shortening, in order:** drop articles in labels (`Nível`, not `O nível`) → shorter synonym (`Config.` ✗ on buttons, `Opções` ✓; `Repetir` vs `Tentar novamente`) → standard abbreviations in tooltips only (`Nv.`, `HP`, `Config.`) → never cut a word mid-way or drop an accent.
* Run `ui_expansion_checker.py --locale pt-BR --fail-on-high`; the checker's locale table must carry the same +30 % ceiling as this section.

## 10. Ratings, Legal & Sensitive Content
* **Rating board: ClassInd** (Classificação Indicativa, Ministério da Justiça) is **mandatory** for Brazil even when a PEGI/ESRB rating exists: `L` (livre), `10`, `12`, `14`, `16`, `18`, with descriptors (*violência*, *linguagem imprópria*, *drogas*, *sexo*, *conteúdo sexual*). The current guide is Portaria MJSP nº 502/2021 — check the text in force at release.
* **Profanity ladder (lock in bible):** `droga / caramba / saco` (L–10) → `merda`, `cacete`, `porra` (12–14, *linguagem imprópria*) → `caralho`, `puta que pariu`, `filho da puta` (16–18) → slurs never.
* **Sensitive topics:** the 1964–85 dictatorship, current politics (polarised), race (a legal matter — *injúria racial* is a crime), Afro-Brazilian religions (*umbanda / candomblé* mockery is a hate-speech risk), North-east stereotypes. Keep football rivalries light.
* **Legal:** the Marco Legal dos Games (Lei 14.852/2024) and the Estatuto da Criança e do Adolescente apply; CDC consumer law requires Portuguese on store pages, manuals and in-game text; loot-box odds must be disclosed where the bible flags the mechanic as *gacha*.

## 11. Golden Voice Anchors (A1–A5)
Each pair keeps the **same meaning**; only the voice changes. Roles are generic (the Mentor, the Rival…) — never project names. Dialogue lines use the colloquial imperative allowed by §2.

1. **A1 Mentor / Veteran (colloquial `você`, warm):**
   * *Robotic ✗:* `"Comece com o que puder reciclar e coloque o local em funcionamento novamente. Farei algumas ligações em seu benefício."`
   * *Natural ✓:* `"Começa com o que der pra aproveitar da sucata e bota a oficina pra funcionar de novo. Depois eu dou uns telefonemas por você."`
2. **A2 Hotshot Rival (`você`, cocky, fast):**
   * *Robotic ✗:* `"As pessoas dizem que perdi minha vantagem. Isso é completamente falso. Conserte o veículo rapidamente."`
   * *Natural ✓:* `"Vivem dizendo por aí que eu perdi a mão. Papo furado! Deixa a máquina tinindo, e rápido."`
3. **A3 Rookie / Teen (`você`, short, everyday slang):**
   * *Robotic ✗:* `"Tentei vedar o vazamento utilizando um selante, porém o material soltou-se durante a decolagem."`
   * *Natural ✓:* `"Tentei tapar o vazamento com massa, mas foi só decolar que soltou tudo."`
4. **A4 Scientist / Engineer (clean `você`, precise but spoken):**
   * *Robotic ✗:* `"Faz-se necessário proceder à substituição do gerador anteriormente à próxima utilização do aparelho."`
   * *Natural ✓:* `"Troque o gerador antes de ligar o aparelho de novo."`
5. **A5 Outlaw / Antagonist (cold `você`, short, gender-safe):**
   * *Robotic ✗:* `"Fui informado de que você estabeleceu contato com as autoridades. Eu odiaria ver sua situação tornar-se complicada."`
   * *Natural ✓:* `"Me disseram que você falou com as autoridades. Seria uma pena se as coisas complicassem pro seu lado."`

## 12. Linter Coverage Note
Currently in `lqa_linter.py` for `pt-BR`: `Ecrã|Definições|Utilizador` (ERR, case-sensitive), `A + carregar/guardar/montar/desmontar` (WARN), `possui` (WARN). Everything else in §1, §4, §6 and §8 is **not** yet enforced; the existing term rule should become case-insensitive.

**Suggested linter patterns (regex-friendly, low false-positive risk, for the scripts owner):**
* ERR `\b(?:o|a|os|as|um|uma|do|da|no|na|ao|à|pelo|pela)\s+\{\w+\}` — article/contraction glued to a placeholder (§6).
* ERR `\b(?:Ecrã|Definições|Utilizador|Rato|Ficheiro|Equipa|Guardar jogo)\b` (case-insensitive) — `pt-PT` lexicon; WARN `\bGuardar\b` alone in UI categories.
* ERR `\bOBTER ITENS\b`, `\bMover para\b`.
* WARN `\bnão pode ser \w+ad[oa]s?\b` — English passive.
* WARN `\bcom sucesso\b|\bexitosamente\b` — calque / Spanish.
* WARN `\b(?:Realizar|Efetuar) (?:a|o) \w+\b` — corporate verb.
* WARN `\bBem-vind[oa]s?\b` — use `Boas-vindas`; WARN `\bPrezad[oa]\b`, `\b\w+\([ao]\)\b` — gender hacks.
* WARN `\bObrigad[oa]\b` in player-voiced categories only (NPC speech is fine).
* WARN `\bVocê (?:está|é|foi|ficou) \w+(?:ado|ido|oso)\b` — gendered predicate about the player.
* WARN `\b[Tt]enho \w+(?:ado|ido)\b` — Spanish-perfect contamination (expect legitimate hits in "I've been …" contexts; keep WARN).
* WARN `\b(?:pra|tá|né)\b` in UI categories only — dialogue-only contractions.
* WARN `\bfalta disposição\b` — wrong stamina word.
