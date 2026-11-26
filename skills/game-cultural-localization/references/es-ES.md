# Spanish — Spain (`es-ES`) Game Localization & Culturalization Playbook

> **Scope note:** `es-ES` = Castilian Spanish for Spain (PEGI territory). Latin American builds (`es-419` / `es-MX`) differ in pronouns (`ustedes` as the only plural, no `vosotros`), past tense (indefinido for recent events), lexicon (`computadora`, `celular`, `carro`) and rating boards (ESRB / own systems). They need a separate bible; nothing below should be reused for them unchanged.

Target feel: **español de España vivo, cercano y natural, con jerga gamer peninsular auténtica** — never flat *"español neutro de doblaje"*, never bureaucratic Spanish, never a calque of the English rhythm.

## 1. Anti-Translationese Ban List
| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `Configuraciones` / `Salvar` / `Computadora` | `Ajustes` (or `Opciones`) / `Guardar` / `Ordenador` | LatAm or literal; Spain's UI vocabulary differs. |
| `Enfocar` (interact prompt) | `Usar` / `Interactuar` | Literal *focus*; nobody "enfoca" a terminal. |
| `Este objeto no puede ser colocado aquí.` | `Esto no va aquí.` / `Aquí no cabe.` | English passive; Spanish uses active or impersonal `se`. |
| `¡Ya se encuentra un objeto en este lugar!` | `¡Ese hueco ya está ocupado!` / `¡Aquí ya hay algo!` | *Se encuentra* + *lugar* = police report. |
| `¡Ya posees esta herramienta!` | `¡Ya tienes esta herramienta!` | *Poseer* is notarial; spoken Spanish says *tener*. |
| `¡Tu resistencia es demasiado baja!` | `¡Estás sin fuerzas!` / `¡No te queda aguante!` | Stat report → player-facing line. The stat itself is still `Resistencia` (§7). |
| `OBTENER OBJETOS` | `RECOGER TODO` | Literal *GET ITEMS*. |
| `Mover hacia adelante / hacia la izquierda` | `Avanzar` / `Retroceder` / `Izquierda` / `Derecha` | Keybinding labels are one word. |
| `Realizar la reparación` / `Efectuar una compra` | `Reparar` / `Comprar` | Nominalised verb → plain verb. |
| `Guardado con éxito.` / `exitosamente` | `Partida guardada.` / `Guardado.` | *Con éxito / exitosamente* is a calque of *successfully*. |
| `Por favor, espere por favor.` / `Por favor espera` in every toast | `Espera…` / `Un momento…` | Spanish UI uses far fewer *por favor* than English. |
| `ahí fuera` for a vague *out there* | drop it, or `por ahí` / `en la zona` | *Ahí fuera* is literal and needs a real "outside". |
| `Intenté… hoy` (indefinido for today) | `He intentado… hoy` | See §3; indefinido for today sounds LatAm/translated. |
| `¿Estás seguro que quieres salir?` | `¿Seguro que quieres salir?` | Queísmo (*seguro **de** que*) **and** a gendered adjective — drop the verb instead. |

## 2. Register, Address & Character Voice
* **Pronoun set for Spain:** `tú` (singular, default), `usted` (singular formal, rare), `vosotros/as` (plural, default: `Mostradles`, `¿Sabéis?`), `ustedes` (**formal plural only** — using `ustedes` as the neutral plural marks the text as LatAm).
* **Layers, locked in `ES-ES_BIBLE.md`; never mix inside one layer:**
  1. **Buttons / menu labels:** infinitive (§7) — no pronoun at all.
  2. **System prose & tutorials:** `tú` is the modern Spanish platform standard (`¿Seguro que quieres salir?`, `Pulsa para continuar`). `usted` in system text sounds like a bank.
  3. **Character dialogue:** register belongs to the speaker. A1 Mentor → `tú`; A2 Rival → `tú`; A3 Rookie → `tú` (a teenager says `tú` to a mechanic in today's Spain — `usted` would be odd); A4 Scientist → `tú` with a colleague, `usted` only toward a stranger/superior; A5 Antagonist → cold `usted` (threat through distance).
* **`usted` is for:** officials, politicians, aristocrats, elderly strangers in formal settings, cold antagonists. Not for "polite young person" — that is a dubbing cliché.
* **Pro-drop is mandatory:** `Tú tienes que reparar…` ✗ → `Tienes que reparar…` ✓. Subject pronouns only for contrast (`Yo no he sido`).
* **Spoken warmth without heavy street slang:** `Buenas`, `Mira`, `A ver`, `Por cierto`, `Ni de broma`, `Menudo lío`, `una chapuza`, `poner a punto`, `vale`, `apañar`, `echar un cable`, `ir tirando`. Keep Madrid-specific *tronco / mazo / flipar* out of sci-fi or period settings.
* **Capitalisation:** `usted` is lowercase; `Ud.` abbreviation only in forms.

## 3. Spoken vs. Literary Tense
* **Pretérito perfecto compuesto** (`he hecho`, `ha pasado`) for anything **today, recent, or still affecting now**: `El generador ha aguantado`, `¿Has visto las noticias?`, `Se han llevado todo`. This is the es-ES default in dialogue, letters and UI results (`Se ha guardado la partida`).
* **Pretérito indefinido** (`hizo`, `voló`) for **closed past with a time marker** (`Ayer estalló`, `Hace dos años lo construyó`, `En la guerra pilotó uno`) and for **third-person lore, codex and narration** (`El imperio cayó en 2140.`) — there it is natural, not translationese.
* **Regional note:** the north-west (Galicia, Asturias, Canarias) uses indefinido for today as well; the localization standard is still perfecto. Do not imitate regional usage unless the bible assigns it to a character.
* **Future:** spoken = `voy a + inf.`; futur simple for promises/UI (`Se aplicará al reiniciar`). Never *futuro de subjuntivo* (`hubiere`) outside legal text.
* Lock in the bible: `dialogue = perfecto/indefinido per marker; lore = indefinido`.

## 4. Player Gender Neutrality
Spanish marks gender on **adjectives, participles with `estar/ser`, nouns of role, and articles**. The player's gender is unknown.

| Leaks ✗ | Neutral ✓ | Strategy |
|---|---|---|
| `Bienvenido` | `Te damos la bienvenida` / `Bienvenida al taller` (noun) | *Bienvenida* as a noun is invariant. |
| `¿Estás listo?` | `¿Todo listo?` / `¿Vamos?` | Move the adjective to a thing. |
| `Eres un mecánico hecho y derecho.` | `Ya dominas el oficio.` / `Eres una leyenda del taller.` | Feminine nouns like *leyenda, máquina, persona* are invariant regardless of the player. |
| `Has sido seleccionado.` | `Te han seleccionado.` / `Selección completada.` | Active voice with `te` — Spanish participles do **not** agree with object clitics. |
| `Estás cansado.` | `Estás sin fuerzas.` / `Te falta energía.` | Prepositional phrase instead of adjective. |
| `Jugador` / `Aliado` | `Perfil` / `Alianza` | Abstract nouns. |
| `Hola, chaval / tío / hijo / jefe` | `Hola, crack` / `¡Qué crack!` / nickname from the bible | *Crack, colega, compi* are invariant; `jefe/jefa` and `un/una máquina` are not. |
| `Estimado/a usuario/a` | `Hola` / `Saludos` | Never `@`, `x`, `-e` or `o/a` in UI or dialogue. |

* **Safe compound tenses:** `haber` + participle is **always invariant** — `Has ganado`, `Has reparado todo`, `Has superado la prueba` are safe. The trap is `ser/estar/quedar` + participle/adjective (`Estás preparado`, `Has quedado clasificado`).
* **Invariant adjectives:** `hábil`, `capaz`, `fiable`, `eficaz`, `fuerte`, `valiente`, `genial`, `imparable`, `grande`.

## 5. Plurals, Numbers & ICU
* **CLDR categories for `es`:** `one` (exactly 1), `many` (compact millions: `1 millón de`), `other` (everything else, **including 0 and decimals**).

| `{0}` | Spanish | Category |
|---|---|---|
| 0 | `0 objetos` (better: `Ningún objeto`) | other |
| 1 | `1 objeto` | one |
| 2 | `2 objetos` | other |
| 5 | `5 objetos` | other |
| 21 | `21 objetos` | other |
| 1,5 | `1,5 objetos` | other |

* **ICU:** `{count, plural, one {# objeto} other {# objetos}}`; `=0 {Ningún objeto}` is the natural override.
* `objeto(s)` with brackets is banned in UI; use ICU or two keys. `1 objetos` from a lazy plural key is an ERR.
* **Numbers as words:** zero to nine in letters inside dialogue (`tres piezas`), digits in UI. Ordinals: `1.º`, `2.ª`, `3.er` (with the period) — never `1ro`, `2do`.

## 6. Placeholder & Rich-Text Grammar Traps
* **Article + `{0}` breaks on gender:** `el {0}` → `el espada` ✗. Contractions break too: `de el {0}` ✗ (must be `del`), `a el {0}` ✗ (`al`). **Never glue `el/la/un/una/del/al` to a placeholder.** Use a classifier noun or a colon: `el objeto {0}`, `la pieza {0}`, `Obtenido: {0}`, `Equipar: {0}`.
* **Adjective / participle after placeholder:** `{0} equipado` ✗ (agreement unknown) → `Has equipado: {0}` ✓ (`haber` is invariant) or `Equipamiento: {0}`.
* **Number placeholders** follow §5 ICU; `%d objetos` is the same trap in printf form.
* **Rich text:** inverted marks go **inside** the tag with their sentence: `¿<b>Seguro</b>?` ✗ → `<b>¿Seguro?</b>` ✓; never split a word at an accent (`<color=red>Ener</color>gía` ✗). Tags must nest; the linter checks parity.
* **Concatenation ban:** `"Tienes " + n + " objetos"` cannot be pluralised or reordered; demand one string with placeholders.
* **Leading/trailing spaces** required by the source (`"Pulsa "` + key) must be preserved; run `lqa_linter.py --strict-whitespace`.
* **Engine-agnostic note:** the rules apply identically to Unity `{0}` / `{itemName}` + `<b>`/`<color=>`/`<sprite>`, Unreal `{Name}` / `|hpp(…)` / `<tag>…</>`, Godot `%s` / `%d` / BBCode `[b]…[/b]`, printf `%s %1$s`, Python-style `{name}` and ICU `{count, plural, …}`. Treat every placeholder syntax as an opaque token that cannot take an article or agreement; Unreal `|plural(one=…, other=…)` and Godot `tr_n()` follow the same one/other split as §5.

## 7. Core UI Glossary
Button format: **infinitive** for actions, **noun** for screens, **sentence case** (`Nueva partida`, never `Nueva Partida`), ALL CAPS only if the source is caps and the font has `Á É Í Ó Ú Ñ`. Never the imperative on buttons (`Guarda` ✗).

| English | `es-ES` (market standard) | Note |
|---|---|---|
| Save | `Guardar` | `Salvar` ✗ (LatAm/literal). |
| Load | `Cargar` | `Cargando…` for the progress state. |
| Quit | `Salir` | `Salir del juego` / `Salir al menú`. |
| Settings / Options | `Ajustes` / `Opciones` | Pick one; `Configuración` (singular) is acceptable, `Configuraciones` ✗. |
| OK / Confirm | `Aceptar` / `Confirmar` | `OK` only if the bible allows it. |
| Cancel | `Cancelar` | |
| Back | `Atrás` | `Volver` also common. |
| Continue | `Continuar` | |
| New Game | `Nueva partida` | `Nuevo juego` ✗. |
| Apply | `Aplicar` | |
| Delete | `Eliminar` / `Borrar` | |
| Yes / No | `Sí` / `No` | `Sí` always with the accent. |
| Pause | `Pausa` | Noun as menu title. |
| Resume | `Reanudar` | `Continuar` on the pause menu is also standard. |
| Retry | `Reintentar` | |
| Skip | `Omitir` / `Saltar` | `Saltar` for cutscenes. |
| Inventory | `Inventario` | |
| Equip | `Equipar` | |
| Craft | `Fabricar` / `Crear` | `Fabricación` for the menu. |
| Upgrade | `Mejorar` | `Mejora` (noun). |
| Level | `Nivel` | `Nv.` abbreviation. |
| Health | `Salud` / `Vida` (`PS` / `PV`) | Pick one per bible. |
| Stamina | `Resistencia` / `Aguante` | `Resistencia` is the stat name standard; `aguante` is the spoken word. |
| Damage | `Daño` | Singular. |
| Buy / Sell | `Comprar` / `Vender` | |

## 8. Typography, Numbers & Formatting
* **Opening marks are mandatory:** `¿Seguro que quieres salir?`, `¡Cuidado!` — the only exception is a key with a documented font limitation, recorded in the bible. In rich text they stay inside the tag (§6).
* **Quotes:** RAE order is `«…»` → `“…”` → `‘…’`. Most games lock `“ ”` as primary for font reasons; either is fine, but lock one. Never straight `"` in dialogue.
* **Numbers:** decimal comma, thousands point: `1.234,56` (RAE prefers a thin space, but `1.234` is the Spanish game/retail convention). Currency after the number with a space: `12,50 €`. Percent: RAE `50 %` (space); many games use `50%` — lock one.
* **Date / time:** `26/11/2026` or `26 de noviembre de 2026` (month lowercase); time `14:30`.
* **Case:** sentence case; **no Title Case**; days, months, languages, nationalities lowercase (`lunes`, `noviembre`, `español`). Accented capitals are mandatory (`ÁREA`, `ÉXITO`, `MÁS`).
* **Ellipsis:** single `…`. **Dashes:** `—` (raya) for dialogue in narrative prose, closed to the text (`—Hola —dijo`); `-` only in compounds. No space before `? ! : ;` (unlike French).
* **Line breaking:** never leave `¿` or `¡` at the end of a line; keep `12,50 €` together with a no-break space.

## 9. Text Expansion & UI Fit
* **Typical expansion vs. English: +15 % to +30 %**; short labels can double (`ON` → `ACTIVADO`, `Apply` → `Aplicar`, `Load` → `Cargar`). Industry rule of thumb (IBM/W3C): the shorter the source, the higher the ratio.
* **Shortening, in order:** drop articles in labels (`Nivel`, not `El nivel`) → shorter synonym (`Atrás` vs `Volver atrás`, `Sí` vs `Aceptar`) → standard abbreviations in tooltips only (`Nv.`, `PS`, `Config.`) → never cut a word mid-way or drop an accent to save a pixel.
* Run `ui_expansion_checker.py --locale es-ES --fail-on-high`; the checker's locale table must carry the same +30 % ceiling as this section.

## 10. Ratings, Legal & Sensitive Content
* **Rating board:** **PEGI**, adopted in Spain through the industry code (AEVI). *Bad Language* descriptor thresholds decide which words are allowed.
* **Profanity ladder (lock in bible):** `jolín / jopé / porras` (PEGI 3–7) → `mierda`, `joder` (mild in Spain, but PEGI 12+), `coño` (12–16) → `hostia`, `gilipollas`, `cabrón` (16) → `hijo de puta` (18 if aimed at a person) → slurs never.
* **Sensitive topics:** the Civil War and Franco, ETA/Basque conflict, Catalan independence, the monarchy and the Church are live political issues — jokes need lead sign-off; religious swearing (`hostia`, `me cago en…`) is common speech but is still *Bad Language* for PEGI.
* **Legal:** consumer law requires Spanish on store pages and manuals for products sold in Spain; loot boxes are under proposed gambling regulation — keep odds wording factual (`probabilidad`), never `gratis` for anything with a cost.
* **LatAm builds** (ESRB, Mexico's own system) are out of scope for this file.

## 11. Golden Voice Anchors (A1–A5)
Each pair keeps the **same meaning**; only the voice changes. Roles are generic (the Mentor, the Rival…) — never project names.

1. **A1 Mentor / Veteran (`tú`, warm, pretérito perfecto):**
   * *Robotic ✗:* `"Comienza con cualquier cosa que puedas reciclar y pon el lugar en funcionamiento nuevamente. Entonces enviaré contratos hacia tu dirección."`
   * *Natural ✓:* `"Empieza con lo que puedas rescatar de la chatarra y vuelve a poner el taller en marcha. Luego te paso unos cuantos encargos."`
2. **A2 Hotshot Rival (`tú`, cocky, fast):**
   * *Robotic ✗:* `"La gente continúa diciendo que perdí mi ventaja. Es completamente falso. Repara el vehículo tan rápido como puedas."`
   * *Natural ✓:* `"Por ahí van diciendo que he perdido facultades. ¡Ni de broma! Ponme la máquina a punto, y rapidito."`
3. **A3 Rookie / Teen (`tú`, short, everyday slang):**
   * *Robotic ✗:* `"Intenté reparar la fuga utilizando un sellador, sin embargo el material se desprendió al despegar."`
   * *Natural ✓:* `"He intentado tapar la fuga con masilla, pero nada más despegar se ha soltado todo."`
4. **A4 Scientist / Engineer (`usted` toward a stranger, precise but spoken):**
   * *Robotic ✗:* `"Resulta necesario proceder a la sustitución del generador con anterioridad al próximo uso del aparato."`
   * *Natural ✓:* `"Cambie el generador antes de volver a encender el aparato."`
5. **A5 Outlaw / Antagonist (cold `usted`, short, gender-safe):**
   * *Robotic ✗:* `"Se me ha informado de que usted ha establecido contacto con las autoridades. Lamentaría que su situación se volviera complicada."`
   * *Natural ✓:* `"Me han dicho que ha hablado con las autoridades. Sería una lástima que las cosas se le complicaran."`

## 12. Linter Coverage Note
Currently in `lqa_linter.py` for `es-ES`: `Configuraciones` (ERR), `Enfocar` (WARN), `posees` (WARN), `se encuentra un objeto` (WARN). Everything else in §1, §4, §6 and §8 is **not** yet enforced.

**Suggested linter patterns (regex-friendly, low false-positive risk, for the scripts owner):**
* ERR `\b(?:el|la|los|las|un|una|unos|unas|del|al)\s+\{\w+\}` — article/contraction glued to a placeholder (§6).
* ERR `\bSalvar\b` in UI categories (Save → `Guardar`); WARN elsewhere (`salvar` = rescue is legitimate in dialogue).
* ERR `\bComputadora\b`, `\bOBTENER OBJETOS\b`, `\bMover hacia\b`.
* WARN `\bno puede ser \w+ad[oa]s?\b` — English passive.
* WARN `\b(?:realizar|efectuar) (?:la|una|el|un) \w+(?:ción|miento)\b` — nominalised verb.
* WARN `\bcon éxito\b|\bexitosamente\b` — calque of *successfully*.
* WARN `^(?!.*¿).*\?` and `^(?!.*¡).*!` — closing mark without opening mark (skip keys flagged `font_limited` in the bible).
* WARN `\b(?:Estás|Eres|Has (?:sido|quedado)) (?:listo|preparado|seguro|cansado|seleccionado|clasificado)\b` — gendered predicate about the player.
* WARN `\bBienvenido\b` — use `Te damos la bienvenida`.
* WARN `\b\w+@s\b|\b\w+[oa]/[oa]\b|\bl[oa]s/[oa]s\b` — `@`, `o/a` gender hacks.
* WARN `\bustedes\b` — formal plural only in es-ES; verify the speaker.
* WARN `\b(?:estás|está) segur[oa] (?:de )?que\b` — gendered adjective + queísmo risk; prefer `¿Seguro que…?`.
