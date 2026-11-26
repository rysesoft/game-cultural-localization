# Russian (`ru-RU`) Game Localization & Culturalization Playbook

Target feel. **Живой, естественный разговорный русский + настоящий язык игроков**, ZERO *канцелярит* (Chukovsky's bureaucratic plague), ZERO wooden English calques.

## 1. Anti-Translationese Ban List

| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `Осуществлять ремонт` / `производить сборку` | `Чинить` / `Собирать` | Verbal-noun chain = канцелярит. |
| `Фокусировать` (interact) | `Использовать` / `Открыть` | Calque of "Focus". |
| `Данный предмет не может быть размещён здесь.` | `Сюда это не подойдёт.` / `Сюда не поставить.` | *Данный* in any case + passive. |
| `В данном месте уже находится предмет!` | `Место уже занято!` / `Тут уже что-то лежит!` | *Находится* = police report. |
| `Вы уже обладаете данным инструментом!` | `Этот инструмент у вас уже есть!` | *Обладать* is legal Russian. |
| `Ваша выносливость слишком низкая!` | `Не хватает сил!` / `Выносливость на нуле!` | Stat stays `Выносливость`. Toast speaks. |
| `ПОЛУЧИТЬ ПРЕДМЕТЫ` | `ЗАБРАТЬ ВСЁ` | |
| `Двигаться вперёд / Двигаться влево` | `Вперёд` / `Влево` | Keybinding labels are adverbs. |
| `Ты имеешь` / `Он имеет` | `У тебя есть` / `У него есть` | Calque of *have*. |
| `В целях продолжения нажмите` | `Чтобы продолжить, нажмите` | *В целях* is officialese. |
| `Операция успешно завершена.` | `Готово!` / `Сохранено.` | System jargon. |
| `Является` / `представляет собой` | drop the copula. `Реактор — источник энергии.` | Written-register copula. |
| `Космическая чушь!` | `Чушь!` / `Бред!` / `Ерунда!` | Calqued exclamation. |

## 2. Register, Address & Character Voice

| Speaker | Address | Notes |
|---|---|---|
| UI, tutorials, toasts, system messages | **`вы` (lowercase)**, the default | Russian game convention. Also the gender-neutral option (§4). `ты` UI only for deliberately casual/kids' products, locked in `RU-RU_BIBLE.md`. |
| A1 Mentor, A2 Rival, A3 Rookie | `ты` | Particles. `ну`, `да`, `же`, `вот`, `ладно`, `слушай`, `короче` (A3). |
| A4 Scientist (colleague) | `ты`. `вы` for a formal official | Precise terms, spoken syntax. |
| A5 Outlaw / Antagonist, officials | cold `вы` or contemptuous `ты` | One form per character for the whole game. |

* **Capitalization.** `Вы` with a capital only in personal letters addressed to one person. In UI, dialogue, and narration write `вы / вам / ваш` lowercase.
* **Never mix** `ты` and `вы` between the same two characters unless a scripted relationship shift is logged in the ledger.
* **`ё`.** Lock per project. Many studios write `ё` consistently (`всё`, `ещё`, `живём`). Others only where ambiguity arises (`все/всё`). Either way, never mix within one game. The font must have the glyph.
* **Anglicisms.** `лут`, `скилл`, `квест`, `крафт`, `босс` are gamer Russian, acceptable in A2/A3 dialogue and casual UI. Official UI prefers `добыча`, `навык`, `задание`, `создание`. Pick per product.

## 3. Spoken vs. Literary Tense

N/A, Russian has one past tense. The spoken/written difference is **aspect and vocabulary**, not tense. Rules that matter.

* **Aspect in speech.** Completed one-off action = perfective (`починил`, `собрал`). Process/habit = imperfective (`чинил`, `собирал`). Mixing them reads foreign.
* **Historical present** is natural in lively narration (`Прихожу вчера — а там дым.`), not in UI.
* **Bookish markers to avoid in dialogue.** `являться`, `осуществлять`, participles in `-щий/-вший` chains, deverbal nouns (`осуществление`, `произведение ремонта`). Lore/codex may use them sparingly.

## 4. Player Gender Neutrality

Past-tense singular verbs (`сделал` / `сделала`), short adjectives (`готов` / `готова`), and the pronoun `сам / сама` reveal gender.

| Leaks ✗ | Neutral ✓ |
|---|---|
| `Ты запустил мастерскую быстрее, чем я думал.` | `Мастерская уже в строю — куда быстрее, чем я думал!` / `У тебя вышло запустить мастерскую быстрее…` |
| `Ты доказал, что умеешь.` | `Тебе уже по плечу любая деталь.` / `Дело ты знаешь отлично.` |
| `Собери сам или купи.` | `Собери своими руками или купи в терминале.` / `Собери или купи.` |
| `Ты готов?` | `Начинаем?` / `Всё готово?` |
| `Ты сохранил игру.` | `Игра сохранена.` / `Сохранено.` |
| `Ты пришёл вовремя.` | `Ты как раз вовремя.` / `Вовремя!` |
| `Уважаемый господин` (to player) | `Здравствуйте` / `Приветствуем` |

* **With `вы`.** Plural past (`вы сделали`, `вы справились`) is automatically neutral, this is why `вы` is the UI/tutorial default.
* **With `ты`.** Use present, perfective future (`сделаешь`, `появишься`), imperative, infinitive, impersonal (`можно`, `нужно`, `получилось`), nouns of result. Avoid past tense, short adjectives, `сам/сама`, `один/одна`, `должен/должна`, `рад/рада` about the player.
* Named NPCs with known gender speak about themselves freely (the Rival may say `я выдохся` if male).

## 5. Plurals, Numbers & ICU

Russian has **four** CLDR categories. **One** (1, 21, 31 … ending in 1 but not 11), **few** (2 to 4, 22 to 24 … but not 12 to 14), **many** (0, 5 to 20, 25 to 30, 11 to 14 …), **other** (fractions).

| Count | Russian | ICU |
|---|---|---|
| 0 | `0 реакторов` | `many` |
| 1 | `1 реактор` | `one` |
| 2 | `2 реактора` | `few` |
| 5 | `5 реакторов` | `many` |
| 11 / 12 / 14 | `11 реакторов` / `12 реакторов` / `14 реакторов` | `many` |
| 21 | `21 реактор` | `one` |
| 22 | `22 реактора` | `few` |
| 25 | `25 реакторов` | `many` |
| 1,5 | `1,5 реактора` | `other` |

```text
{count, plural, one {{count} реактор} few {{count} реактора} many {{count} реакторов} other {{count} реактора}} на складе
```

* Feminine/neuter nouns. `1 деталь / 2 детали / 5 деталей`. `1 задание / 2 задания / 5 заданий`.
* Verb agreement. `Остался 1 реактор`, `Осталось 2 реактора`, `Осталось 5 реакторов`, keep the full clause inside each branch.
* Without ICU support, avoid the noun. `Реакторы: {count}`, `Реакторов на складе: {count}`.

## 6. Placeholder & Rich-Text Grammar Traps

* **Case after prepositions.** `из {0}`, `в {0}`, `с {0}`, `от {0}` need genitive/accusative/instrumental. A nominative item name breaks. Insert a declined classifier. `"Перенос деталей со станции {0} на склад"`, `"Предмет {0} перенесён на склад"`, or a colon. `"Перенесено на склад: {0}"`.
* **Adjective agreement.** `Новый {0}` fails for feminine/neuter nouns. Use `Новинка: {0}` or `{0} (новое)`.
* **Numerals + noun.** Never `{count} реактор(ов)`. Use ICU (§5).
* **`{playerName}` in address.** Russian has no vocative, but the name still needs case after prepositions (`для {playerName}`). Keep it nominative. `{playerName}, …` or `Игрок: {playerName}`.
* **Rich-text tags wrap whole words.** `<b>реактора</b>` (ending inside), never `<b>реактор</b>а`. Same for `[b]…[/b]` BBCode and Unreal `<>` styles.
* **Engine equivalents.** Unity `{0}`, Unreal `{Name}`, Godot `%s`, ICU, printf `%1$s`, the Russian case and gender are carried by the classifier noun next to the placeholder.
* **Concatenation.** Word order differs (`Стоимость улучшения: {0}`). Report seams to the lead. Keep legacy leading/trailing spaces exactly (`--strict-whitespace`).
* **Separate** `Контракт` (customer contract) from `Заказ` (workstation order) when a game has both.

## 7. Core UI Glossary

Buttons. **Infinitive** (Russian standard). `Отмена` is the noun exception. Choose **perfective** for one-shot actions (`Построить`, `Собрать`, `Сохранить`), **imperfective** for ongoing modes/toggles (`Показывать подсказки`, `Следить`).

| EN | ru-RU | Note |
|---|---|---|
| Save / Load | `Сохранить` / `Загрузить` | |
| Quit | `Выйти` · `Выход` (menu heading) | `Выйти в меню` / `Выйти из игры` |
| Settings / Options | `Настройки` / `Параметры` | |
| OK / Confirm | `ОК` / `Подтвердить` | |
| Cancel / Back | `Отмена` / `Назад` | noun form standard |
| Continue / Resume | `Продолжить` / `Продолжить` (`Возобновить` rare) | |
| New Game | `Новая игра` | |
| Apply | `Применить` | |
| Delete | `Удалить` | |
| Yes / No | `Да` / `Нет` | |
| Pause | `Пауза` | |
| Retry / Skip | `Повторить` (`Попробовать снова`) / `Пропустить` | |
| Inventory / Equip | `Инвентарь` / `Экипировать` (`Надеть` for wearables) | |
| Craft / Upgrade | `Создать` (`Собрать`) / `Улучшить` | tab. `Создание` / `Крафт` (casual) |
| Level / Health / Stamina / Damage | `Уровень` / `Здоровье` (`ОЗ`) / `Выносливость` / `Урон` | |
| Buy / Sell | `Купить` / `Продать` | |
| Take All | `Забрать всё` | |

* Capitalization. Sentence case (`Новая игра`), never English Title Case. ALL CAPS only if the engine applies it. Typical limits. Button 12 to 14, tab 10, badge 6.

## 8. Typography, Numbers & Formatting

* **Quotes.** `«…»` outer, `„…“` inner. `"…"` is wrong in final text.
* **Numbers.** `1 234,56` (space thousands, comma decimal). Percent with space `40 %` (GOST), though `40%` is widespread in games, pick one in the bible.
* **Currency.** `1 234,56 ₽` or `1 234,56 руб.` (after, with space). In-game currency. `1 250 кредитов` (declined by ICU).
* **Date/time.** `26.11.2026`, `26 ноября 2026 г.`. Time `14:30`.
* **Dashes.** Em dash `—` spaced for dialogue and copula replacement (`Реактор — источник энергии`). Hyphen in compounds. Ellipsis `…`.
* **Capitalization.** Months, nationalities lowercase. Only the first word of a title capitalized.
* **Letter `ё`.** See §2. In ALL CAPS `Ё` must exist in the font (check with `font_glyph_scanner.py`).
* **Line breaks.** `U+00A0` after one-letter prepositions (`в`, `с`, `к`, `у`, `о`, `и`, `а`), before the dash, between number and unit.

## 9. Text Expansion & UI Fit

* **Typical expansion from en.** +15 to 30 %. Cyrillic glyphs are also wider on average than Latin in many fonts. Short strings expand most (`APPLY` → `ПРИМЕНИТЬ`, `SETTINGS` → `НАСТРОЙКИ`, `RETRY` → `ПОВТОРИТЬ`).
* **Shortening strategies.** Drop objects (`Сохранить игру` → `Сохранить`), nouns on tabs (`Создание`), accepted abbreviations (`ОЗ`, `ур.`, `мин`, `с`), shorter synonyms (`Попробовать снова` → `Повторить`).
* `ui_expansion_checker.py --locale ru-RU` uses the ru factor. Keep `max_chars` metadata current.

## 10. Ratings, Legal & Sensitive Content

* **Age marking (436-ФЗ).** Mandatory labels `0+ / 6+ / 12+ / 16+ / 18+` on the product and store page. The translation must not exceed the declared tier (profanity, violence, alcohol, drugs).
* **Profanity (мат).** `блядь`, `хуй`, `пизда`, `ебать` and derivatives are legally `18+` and require a warning label. Even at `18+` many publishers avoid them. Use `чёрт`, `блин`, `хрен`, `сволочь`, `гад` for strong-but-legal tone. Match the source tier, never the words.
* **LGBT-related content.** Since the 2022 amendments (Federal Law 478-ФЗ) any "propaganda of non-traditional relationships" is banned for all ages. Games have been pulled from the Russian market or edited. Never add such content in translation. Flag existing content with `[sensitive]` for the publisher's legal decision.
* **Nazi symbolism.** Public display is an offense (Art. 20.3 КоАП) even in historical games. Swastikas are routinely removed in Russian builds. Flag. Do not improvise.
* **Other legal hot spots.** Criticism of the armed forces and "discrediting" laws (2022), "extremist" organizations, religious insult (Art. 148 УК), real politicians, depictions of Crimea/Donbas and maps, drug use glamorization, gambling (loot boxes require honest odds wording).
* **Soviet-era references.** Nostalgic humour is fine. Glorification of repression is not.

## 11. Golden Voice Anchors (A1 to A5)

Each pair keeps the **same meaning**. Only the register changes. Generic roles, no project names.

1. **A1 Mentor / Бывалый механик** (`ты`, без привязки к полу игрока)
   * **✗ Канцелярит.** "Начни с переработки доступных материалов с целью восстановления работы мастерской, и я передам тебе контракты."
   * **✓ Живой.** "Начни с того, что удастся разобрать на запчасти, и поставь мастерскую на ноги. Как дело пойдёт, подкину тебе пару своих контрактов."
2. **A2 Hotshot Rival / Дерзкий гонщик** (`ты`, NPC с известным полом)
   * **✗ Канцелярит.** "Критики утверждают, что мои навыки снизились, что совершенно не соответствует действительности. Произведите ремонт машины в кратчайшие сроки."
   * **✓ Живой.** "Все твердят, будто я выдохся. Чушь. Подлатай мне машину поскорее — подиум я никому не отдам."
3. **A3 Rookie / Новичок** (`ты`, короткие фразы)
   * **✗ Канцелярит.** "Я предпринял попытку устранения утечки при помощи промышленной замазки, однако она отказала непосредственно после взлёта."
   * **✓ Живой.** "Пробовал залепить течь промышленной замазкой, но стоило оторваться от земли, как она задымилась и отвалилась."
4. **A4 Scientist / Инженер** (`ты` между коллегами)
   * **✗ Канцелярит.** "Выходная мощность генератора снизилась до сорока процентов от номинального значения вследствие недостаточного охлаждения."
   * **✓ Живой.** "Генератор выдаёт только 40 % — охлаждение не справляется. Сначала поменяй вентилятор, потом замерим ещё раз."
5. **A5 Outlaw / Антагонист** (холодно, коротко, без пола игрока)
   * **✗ Канцелярит.** "В случае продолжения твоей деятельности на данной территории ты столкнёшься с негативными последствиями."
   * **✓ Живой.** "Ещё раз здесь появишься — пожалеешь. Последнее предупреждение."

## 12. Linter Coverage Note

`lqa_linter.py --locale ru-RU` currently catches. `фокусировать` (ERR), `осуществлять / осуществить / производить / произвести` (WARN, note `производить` is a false positive in `производить впечатление` and factory contexts, narrow to `производить (?:ремонт|сборку|установку|замену)`), `данный предмет/инструмент/объект` (WARN, nominative only).

### Suggested linter patterns

| Severity | Pattern | Message |
|---|---|---|
| WARN | `\bданн(?:ый\|ая\|ое\|ые\|ого\|ой\|ому\|ым\|ыми\|ом\|ых\|ую)\b` (replace current rule) | канцелярит `данный` in every case |
| WARN | `\b(?:осуществл\w+\|производить (?:ремонт\|сборку\|установку\|замену)\|произвести (?:ремонт\|сборку\|установку\|замену))\b` (replace current rule) | verbal-noun helper, FP-safe |
| ERR | `\b(?:из\|в\|во\|с\|со\|от\|к\|ко\|на\|при\|о\|об)\s+\{\w+\}` | preposition directly before placeholder (case trap) |
| ERR | `\{\w+\}\s*\(\w+\)` | `(ов)`-style optional plural. Use ICU |
| WARN | `\b(?:сам\|сама\|один\|одна\|должен\|должна\|рад\|рада\|готов\|готова)\b` in `[player]`-tagged strings | gendered form about the player |
| WARN | `\bты\s+\w+(?:ал\|ил\|ел\|ул\|ёл\|ла\|ила\|ела)\b` in `[player]`-tagged strings | gendered past tense with `ты` |
| WARN | `\b(?:являться\|является\|представляет собой\|в целях\|находится\|обладаете\|обладаешь)\b` | канцелярит |
| WARN | `\bКосмическ\w+ чушь\b` | calqued exclamation |
| WARN | `(?<=[^.!?»]\s)Вы\b` | capital `Вы` mid-sentence in UI/dialogue |
| WARN | `"[^"]+"` (straight double quotes) | use `«…»` |
| ERR | `\b(?:бля\w*\|хуй\w*\|пизд\w*\|еба\w*\|ёб\w*)\b` when rating tag < 18+ | мат above declared age tier |
