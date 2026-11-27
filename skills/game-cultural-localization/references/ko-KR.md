# Korean (`ko-KR`) Game Localization & Culturalization Playbook

Target feel. **번역투 없는 자연스럽고 생생한 한국어, 화자마다 또렷한 말투, 한국 게이머에게 익숙한 UI**.

Scope. Standard Korean (표준어) for any genre, engine and platform released in Korea. Speech-level lock, particle handling, 띄어쓰기 and GRAC compliance are **text-layer** concerns owned here. Examples use generic roles (A1 to A5) and generic items (`{itemName}`, "a generator", "the workshop").

## 1. Anti-Translationese Ban List

Korean gamers are allergic to 번역투 shaped by English *and* Japanese. Hard bans. The ✓ column uses the register locked in §2.2 (system text = 합쇼체).

| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `당신은 ~할 수 있습니다` | `~할 수 있습니다` (subject dropped) | `당신` is confrontational or marital in Korean. Never in UI |
| `~에 의해 파괴되었다` | `해적이 부쉈다` / `해적 공격으로 파괴됐다` | `~에 의해` passive is an English calque |
| `그 / 그녀 / 그들의` in every line | omit, or `그 사람`, `그쪽`, `녀석`, `일당` | Korean drops known referents |
| `이 아이템은 여기에 배치할 수 없습니다.` | `여기에는 설치할 수 없습니다.` | `배치` is technical. `이 아이템은` is redundant |
| `이미 아이템이 존재합니다!` | `이미 다른 물건이 있습니다.` | `존재하다` is philosophical register |
| `이미 이 도구를 소유하고 있습니다!` | `이미 가지고 있는 도구입니다.` | `소유` is legal register |
| `스태미나가 너무 낮습니다!` | `스태미나가 부족합니다.` | *too low* calque. Stat lock = `스태미나` (`내구도` is Durability) |
| `포커스` (interact prompt) | `사용` / `조사` / `대화` | *Focus* never meant *interact* |
| `아이템 획득` (GET ITEMS) | `모두 받기` | `획득` is log-speak. Buttons are 명사형 |
| `~하는 것이 가능합니다` | `~할 수 있습니다` | Japanese-style 가능 calque |
| `~하는 것을 원하십니까?` | `~하시겠습니까?` | *Do you want to* calque |
| `성공적으로 저장되었습니다` | `저장했습니다` / `저장 완료` | *successfully* is noise |
| `~을(를) 필요로 합니다` | `열쇠가 필요합니다` (particle on a fixed noun) | *requires* calque |
| `~에 대하여` / `~에 있어서` | `~에 대해` / drop | 문어체 particles in dialogue |
| `매우 강력한 매우 희귀한` | `아주 강력하고 희귀한` | adjective stacking |

## 2. Register, Address & Character Voice

### 2.1 Speech levels (화계)

| Level | Endings | Game use |
|---|---|---|
| 합쇼체 (하십시오체) | `~합니다`, `~습니까?`, `~하십시오` | System messages, legal text, formal NPCs |
| 해요체 | `~해요`, `~하세요`, `~할까요?` | Tutorials, friendly NPCs, shopkeepers |
| 해체 (반말) | `~해`, `~야`, `~지`, `~자` | Peers, family, rivals |
| 하게체 | `~하게`, `~하나?`, `자네` | Elder → younger adult (mentor), slightly old-fashioned |
| 해라체 | `~한다`, `~해라` | Narration, written notes, orders |

### 2.2 UI register lock (locked for this suite)

| Category | Register | Example |
|---|---|---|
| System messages, errors, dialogs, toasts | 합쇼체 statements. Requests in `~하세요` (`~하십시오` only for legal/safety) | `여기에는 설치할 수 없습니다.` / `다시 시도하세요.` |
| Tutorials / narrator hints | 해요체 | `먼저 작업장을 가동해 볼까요?` |
| Buttons, labels | 명사형 (noun or `-기`) | `저장`, `계속하기`, `모두 받기` |
| Character-voiced hints (speaker tagged) | that speaker's level | `자리 없다니까. 다른 데 놔.` |

Mixing `~없어요` and `~없습니다` inside one category is a `register` issue (score 2). Write the choice into `KO-KR_BIBLE.md` in Phase 0.

### 2.3 Addressing the player
* Never `당신`, `그대`, or `너` in UI. Use a title (`사장님`, `대장`, `선장님`, `공방장님`), `{playerName} 님` / `{playerName} 씨`, or omission.
* Kinship address (`형`, `오빠`, `누나`, `언니`, `동생`) depends on **both** speakers' genders → banned for the player (§4). `자네` is fine from an elder mentor. `얘야` only for a child character, never for an adult player.
* `그쪽` is a deliberately cool, distant address, use it only for antagonists signalling contempt, and note it in the bible.

### 2.4 Archetype voices (A1 to A5)

| ID | Archetype | Level to player | Markers |
|---|---|---|---|
| A1 | Mentor / Veteran | 반말 or 하게체, warm | `~해 봐`, `~해 둘게`, `몸 조심해라`, `자네` |
| A2 | Hotshot Rival | 반말, fast | `~거든`, `~라고`, `헛소리`, `애송이` |
| A3 | Rookie / Teen | 해요체, breathless | `~했는데요`, `~해 버렸어요`, `진짜`, `완전` |
| A4 | Scientist / Engineer | 해요체 or 합쇼체, precise but spoken | `~해야 돼요`, exact numbers, `~하면 안 됩니다` |
| A5 | Outlaw / Antagonist | 합쇼체 with cold distance, or terse 반말 | short sentences, `~겠습니까.`, `그쪽`, ellipsis |

## 3. Spoken vs. Literary Tense
N/A, Korean has no spoken/literary past split. The speech-level axis of §2 replaces it. Aspect traps that still read as translationese.
* Double past `~했었다` for a simple event. `열쇠를 찾았었다` ✗ → `열쇠를 찾았다` ✓. Reserve `~했었다` for "used to / no longer".
* Progressive calque `~하고 있었다` for *was trying*: `막으려고 하고 있었어요` ✗ → `막아 보려고 했어요` ✓.
* Future `~할 것입니다` for every *will*: `저장될 것입니다` ✗ → `저장됩니다` ✓.
* Narration uses 해라체 `~했다`. Dialogue uses the speaker's level.

## 4. Player Gender Neutrality
Korean verbs carry no gender, so leaks come from **address terms, kinship words and descriptors**.
1. **NPC → player address.** `형 / 오빠 / 누나 / 언니 / 동생 / 아들 / 딸 / 아가씨 / 총각 / 청년 / 처자` banned. Use `{playerName} 님`, a title, or omit.
2. **NPC about player.** `그분`, `그 사람`, `사장님`, `플레이어` (system). Never `그녀`. Avoid `그` too when omission works.
3. **Descriptors.** `씩씩한 청년`, `예쁜 아가씨`, `사나이`, `여장부` ✗ → `든든한 사람`, `실력 있는 사람` ✓.
4. **Player's own voice.** `나 / 저` are neutral. The player never calls an NPC `형` / `오빠` / `누나` / `언니` unless the game fixes the player's gender. Use the NPC's name or title.

| Context | Leaking ✗ | Neutral ✓ |
|---|---|---|
| Mentor greeting | `우리 아들, 오랜만이다.` | `오랜만이다. 잘 지냈지?` |
| Rival taunt | `아가씨한테는 무리야.` | `너한테는 아직 무리야.` |
| Official letter | `귀하께서는 젊은 사업가로서…` | `귀하께서는 사업주로서…` |
| Third-person gossip | `그녀가 공방을 다시 열었대.` | `그 사람이 공방을 다시 열었대.` |

## 5. Plurals, Numbers & ICU
* **CLDR plural categories for `ko`: `other` only.** `~들` is optional and never required after a number. `원자로 1개`, `2개`, `5개`, `21개`, `25개`, `0개`, one form. Do not create a `one` branch.
* **Counter nouns (단위명사)** must match the noun. `개` generic, `명` people (`분` honorific), `대` machines/vehicles, `척` ships, `자루` tools with handles, `장` flat items, `마리` animals, `회` / `번` occurrences, `개월` months.

| Noun type | Counter | `{0}` = 1 / 2 / 5 / 21 / 25 |
|---|---|---|
| Generic item | `개` | `원자로 1개` / `2개` / `5개` / `21개` / `25개` |
| Machine | `대` | `발전기 1대` / `2대` / `5대` / `21대` / `25대` |
| Ship | `척` | `함선 1척` / `2척` / `5척` / `21척` / `25척` |
| Person | `명` | `작업자 1명` / `2명` / `5명` / `21명` / `25명` |

* **Spacing.** Arabic numeral + counter is written attached (`1개`, `3명`). Spelled-out number + counter is spaced (`한 개`, `세 명`). Lock the attached digit style for UI.
* **Placeholder patterns.** `{itemName} ×{0}` (preferred). `{itemName} {0}개` only when every item in the table is `개`-countable. Otherwise store the counter in item data (`{itemName} {0}{counter}`).
* **ICU.** `{count, plural, other {원자로 #개}}`.
* **Zero.** `0개` in tables. Empty states say `없음` / `비어 있음`.
* **Large numbers.** `10,000` in UI. `1만` / `3억` acceptable in dialogue. Never `1만,000`.

## 6. Placeholder & Rich-Text Grammar Traps

### 6.1 The particle trap (조사)
Korean particles change with the final sound (받침) of the preceding word. A particle glued to `{0}` is wrong for roughly half of all item names.

| Variable (받침 / no 받침) | Invariant (safe directly after `{0}`) |
|---|---|
| `은/는`, `이/가`, `을/를`, `과/와`, `으로/로`, `아/야`, `이여/여`, `이랑/랑` | `의`, `에`, `에서`, `에게`, `도`, `만`, `부터`, `까지`, `처럼`, `보다` |

Solutions, in order of preference.
1. **Rephrase with an invariant particle or a fixed noun.** `{0}에서 창고로 운반 중` ✓. `{loanAmount} 크레딧을 대출하시겠습니까?` ✓ (particle on the fixed word `크레딧`).
2. **Engine-side resolution** (engine-specific, check which one the project uses).
   * Unreal `FText::Format` Hangul postposition. `{Item}|hpp(을,를)`, `{Item}|hpp(은,는)`, `{Item}|hpp(이,가)`, `{Item}|hpp(으로,로)` picks the particle at runtime.
   * Unity Localization Smart Strings. No built-in Korean particle formatter, implement a custom formatter (e.g. `{item:ko(을|를)}`) or use solution 3. ICU `MessageFormat` has no particle selector either.
   * Godot `%s` / printf `%1$s`: no runtime help. Use solution 1 or 3.
3. **Fallback notation.** `{0}을(를)`, `{0}이(가)`, `{0}은(는)`, `{0}과(와)`, `{0}(으)로`, consonant form first, vowel form in parentheses. Acceptable in system text, ugly in dialogue. Count each use in the ledger.

Never ship `{0}을`, `{0}를`, `{0}이`, `{0}가`, `{0}은`, `{0}는`, `{0}으로` bare on a variable.

### 6.2 Other traps
* **Concatenation ban.** `"{0}" + "을 배달했습니다"` cannot be fixed by translation. Request a full-sentence string.
* **Spaces.** Korean uses spaces (띄어쓰기). Mandatory leading/trailing spaces in sources (`" credits"`) must be preserved exactly (`--strict-whitespace` checks them).
* **Rich text.** Wrap the whole 어절 (word + particle). `<b>열쇠를</b>` ✓. `<b>열쇠</b>를` is legal but may break word-wrap at the tag. Never split number from counter (`<color=red>1</color>개` ✗). BBCode (`[b]…[/b]`) and `<sprite>` pass through verbatim.
* **Honorific agreement.** If `{0}` can be a person, `{0} 님이 ~하셨습니다`, particle and honorific verb must agree.

## 7. Core UI Glossary

| English | ko-KR (default) | Notes |
|---|---|---|
| Save | `저장` | `저장하기` in `-기`-style menus |
| Load | `불러오기` | `로드` only if the project already uses it |
| Quit | `종료` | `게임 종료`, `타이틀로` |
| Settings / Options | `설정` | `옵션` (older console style) |
| OK / Confirm | `확인` |, |
| Cancel | `취소` |, |
| Back | `뒤로` | `돌아가기` |
| Continue | `계속` / `계속하기` | `이어하기` = continue saved game |
| New Game | `새 게임` | `처음부터` |
| Apply | `적용` |, |
| Delete | `삭제` |, |
| Yes / No | `예` / `아니요` | `아니오` is non-standard spelling |
| Pause | `일시 정지` | `일시정지` only if the project closes up labels |
| Resume | `계속하기` | `재개` |
| Retry | `다시 시도` | `재시도` |
| Skip | `건너뛰기` | `스킵` (casual) |
| Inventory | `인벤토리` | `가방`, `소지품` |
| Equip | `장착` | `장비` = equipment (noun) |
| Craft | `제작` | `건조` for ships |
| Upgrade | `강화` | `업그레이드` for systems |
| Level | `레벨` / `Lv.` |, |
| Health | `체력` | `HP` if the UI uses abbreviations |
| Stamina | `스태미나` | never `기력` for the stat |
| Damage | `피해` | `데미지` (colloquial), one per project |
| Buy / Sell | `구매` / `판매` | `구입` acceptable |

* **Button form.** 명사형 (`저장`, `적용`) or `-기` (`계속하기`, `불러오기`), 2 to 6 syllables, no `~합니다`, no final period.
* **Same thing, same name, decided by the context map.** When the map says two keys name the same in-game object or mechanic, they get the same word, and when it says they are different things, they stay apart. E.g. `의뢰` (customer contract) vs `주문` (workstation order). `설계도` vs `레시피`. An item named *industrial sludge* stays `산업용 슬러지` everywhere, never "improved" to `퍼티` in dialogue. The map records which keys name the same thing, so no term is locked in a list.

## 8. Typography, Numbers & Formatting
* **Punctuation is half-width** (`.`, `,`, `!`, `?`, `:`), never `。` or `、`. One space after sentence punctuation. System messages end in a period (locked). `!` is free in character lines.
* **Quotes.** `“ ”` for speech, `‘ ’` for nested quotes/emphasis. `「」` is Japanese style and banned.
* **Ellipsis.** `…` (U+2026, one) or `……` for dramatic pauses. Never `...`.
* **Tilde `~`.** Ranges (`1~5`) and casual elongation in dialogue (`안녕~`). Never in system text.
* **띄어쓰기.** `할 수 있다`, `안 되다`, `한 번`, `좀 더`, `~해 주세요` (spaced auxiliary in formal text, `~해주세요` tolerated in dialogue, lock one). Compound labels may close up (`일시정지`) only if locked.
* **외래어 표기법 (loanword spelling).** `스태미나` (not `스테미너`), `메시지` (not `메세지`), `콘텐츠` (not `컨텐츠`), `컨트롤러`, `인벤토리`, `레이저`, `센서`, `캐릭터`, `라이선스`, `디지털`, `플랫폼`, `배터리`.
* **Numbers.** `1,000` / `0.5` / `50%` (no space) / `×3` / `1,000원` (attached) / `2026년 11월 26일` or `2026-11-26` / `14:30` or `오후 2:30`.
* **Case/emphasis.** No Title Case. Never ALL CAPS Latin in Korean UI. Emphasis via `‘ ’` or a bold tag.
* **Word wrap (어절 단위).** Korean breaks at **spaces**, never inside an 어절. Unity TextMeshPro. Enable *Use Modern Hangul Line Breaking Rules* in TMP Settings, otherwise TMP may break between syllables. Unreal. Verify the Slate/ICU line-break behaviour keeps an 어절 together (ICU allows breaks between Hangul syllables by default), if a build wraps mid-word, escalate as an engine setting, not a text fix. Godot. Verify `autowrap_mode` = word. Hanging punctuation is not used in Korean.
* **Font.** Korean-first CJK font (Noto Sans CJK KR / Source Han Sans KR, or system Malgun Gothic `.ttc`). Hangul in a Japanese/Chinese-first font falls back and shifts baseline. Scan KS X 1001 coverage with `font_glyph_scanner.py`.

## 9. Text Expansion & UI Fit
* **Typical ratio vs English.** Korean usually has **fewer characters** (≈0.7 to 0.9× count) but Hangul glyphs are wide. Visual width is typically **0.9 to 1.1×** English (rule of thumb, measure per font). Height, not width, is the usual clip.
* `ui_expansion_checker.py --locale ko-KR` weights Hangul at 1.8×. Treat `…“”` (Ambiguous width) as wide.
* **Fit rules.** Buttons ≤ 6 syllables, tabs ≤ 4, badges ≤ 3. Line height ≥ 1.4. Minimum 12 px (14 px recommended).
* **Shortening (in order).** Drop `-하기` (`설정하기` → `설정`). Sino-Korean noun instead of phrase (`모두 받기` → `일괄 수령`). Drop particles in labels (`남은 시간이` → `남은 시간`) but never drop spaces. Abbreviations `Lv.`, `HP`.

## 10. Ratings, Legal & Sensitive Content
* **GRAC (게임물관리위원회)** ratings. 전체이용가, 12세이용가, 15세이용가, 청소년이용불가. Descriptors. 선정성, 폭력성, 공포, 언어의 부적절성, 약물, 범죄, 사행성. Text alone can raise a rating through 언어의 부적절성 and 사행성.
* **Profanity policy.** `씨발`, `존나`, `좆`, `병신` → 청소년이용불가 only. `젠장`, `망할`, `빌어먹을`, `제기랄`, `미친` (as exclamation), `개-` prefixes (`개판`) are the 15세 ceiling. 12세 and below. `이런!`, `말도 안 돼!`.
* **Gambling words (사행성).** `도박`, `카지노`, `베팅`, `판돈` move ratings. Prefer `뽑기`, `확률`, `내기` in all-ages text. Probability disclosure for 확률형 아이템 is mandatory (게임산업법, in force since 2024), translate loot-box odds strings exactly.
* **Japanese-origin vocabulary** (일본어 잔재, `노가다`, `땡땡이`, `뽀록`, `간지`) is casual dialogue only. Never in UI.
* **Sensitive geopolitics.** `동해` (never `일본해`). `독도` is Korean. Avoid 욱일기 (Rising Sun) imagery and jokes about 일제강점기. `조선족` / `북한` references need care. `중국산` / `일본산` as insults ✗.
* **Minors.** Sexualised descriptions of school-age characters are rejected by GRAC regardless of rating. `소녀` + romantic context is a red flag.

## 11. Golden Voice Anchors (A1 to A5)
Each pair keeps the **same meaning** as the English gloss. Only the Korean changes. Roles and items are generic so the anchors transfer to any project.

**A1 Mentor / Veteran**, EN. *"Start with whatever you can salvage and get the workshop running again. Do that, and I'll send a few contracts your way."*
* ✗ `"네가 회수할 수 있는 무엇이든 가지고 시작해서 작업장을 다시 작동하게 만들어라. 그러면 내 계약들을 너의 방향으로 보내겠다."`
* ✓ `"우선 건질 만한 고철부터 챙겨서 작업장부터 다시 돌려 봐. 그것만 되면 내 쪽에서 의뢰 몇 건 넘겨줄게."`

**A2 Hotshot Rival**, EN. *"People keep saying I've lost my edge. Total nonsense. Fix her up as fast as you can."* (`her` = the Rival's racer)
* ✗ `"사람들은 내가 감을 잃었다고 계속 말합니다. 그것은 완전한 거짓입니다. 그녀를 가능한 한 빨리 수리하세요."`
* ✓ `"남들은 내가 한물갔다고들 떠들어 대지. 완전 헛소리야. 내 애마, 최대한 빨리 손봐 줘."`

**A3 Rookie / Teen**, EN. *"I tried to plug the leak with industrial sludge, but the moment the ship lifted off, it smoked and peeled right off."*
* ✗ `"저는 산업용 슬러지를 사용하여 누출을 막으려고 시도했지만, 함선이 부양하는 순간 그것은 연기를 내며 벗겨졌습니다."`
* ✓ `"산업용 슬러지로 새는 데를 막아 보려고 했는데요, 함선이 뜨자마자 연기가 나더니 그대로 다 떨어져 버렸어요."`

**A4 Scientist / Engineer**, EN. *"The generator's output is unstable. Don't run it above 80% until I've recalibrated the coils."*
* ✗ `"발전기의 출력은 불안정합니다. 제가 코일을 재보정할 때까지 그것을 80% 이상으로 가동하지 마십시오."`
* ✓ `"발전기 출력이 아직 불안정해요. 코일 다시 조정할 때까지는 80% 넘기지 마세요."`

**A5 Outlaw / Antagonist**, EN. *"I hear the Council contacted you directly. I'd hate to see things get complicated for you."*
* ✗ `"저는 평의회가 당신에게 직접 연락했다고 들었습니다. 저는 당신의 상황이 복잡해지는 것을 보고 싶지 않습니다."`
* ✓ `"평의회에서 직접 연락이 갔다고 들었습니다. ……일이 괜히 복잡해지면 서로 곤란하지 않겠습니까."`

**UI register sample (not an archetype)**, EN. *"There's already an item here! Keep one reactor in the warehouse by crafting or buying one."*
* ✗ `"여기에 이미 아이템이 존재합니다! 제작하거나 구매함으로써 창고에 원자로 1개를 보유하십시오."`
* ✓ `"이미 다른 물건이 있습니다. 원자로를 제작하거나 구매해 창고에 1개 준비하세요."`

## 12. Linter Coverage Note
Currently in `lqa_linter.py` for `ko-KR`: `당신(?:은|이|의|을|에게)` (ERR), `에\s*의해\s` (WARN, misses string-final `에 의해`), `소유하고\s*있습니다` (WARN). The `{0}` + particle trap of §6.1 has no rule yet. Never use `\b` around Hangul. Use substrings or lookarounds.

### Suggested linter patterns

| Severity | Regex | Message |
|---|---|---|
| ERR | `당신` | 번역투 `당신`, use title / name / omission |
| ERR | `[}\]>]\s?(?:을\|를\|이\|가\|은\|는\|으로)(?=[\s,.!?]\|$)` | particle glued to a placeholder, rephrase, use `\|hpp`, or `{0}을(를)` |
| WARN | `[}\]>]\s?(?:을\(를\)\|이\(가\)\|은\(는\)\|과\(와\)\|\(으\)로)` | fallback particle notation, prefer invariant particle or engine resolution |
| WARN | `에\s*의해(?:서)?` | English passive calque `~에 의해` |
| WARN | `그녀` | `그녀`, gender leak / pronoun spam |
| WARN | `성공적으로` | *successfully* calque |
| WARN | `하는 것이 가능` | `~하는 것이 가능` → `~할 수 있` |
| WARN | `아니오(?=[\s,.!?]\|$)` | non-standard spelling, use `아니요` |
| WARN | `스테미너\|스테미나\|메세지\|컨텐츠` | 외래어 표기법 violation |
| WARN | `\d\s+(?:개\|명\|대\|척\|장\|회\|번)(?=[\s,.!?]\|$)` | space between digit and counter, write `1개` |
| WARN | `(?:^\|\s)(?:형\|오빠\|누나\|언니)(?=[\s,.!?~]\|$)` | kinship address, player gender leak |
| WARN | `[。、「」]` | Japanese/Chinese punctuation in Korean |
