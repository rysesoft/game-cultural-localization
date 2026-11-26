# Traditional Chinese (`zh-Hant`) Game Localization & Culturalization Playbook

Target feel: **道地自然的台灣口語、角色各有腔調、繁中玩家熟悉的介面用語**——絕不拿簡體跑機械「簡轉繁」。

Scope: `zh-Hant` in this suite **defaults to Taiwan (zh-TW)**: 國語 vocabulary, Taiwan standard glyph forms, GSRR ratings. Hong Kong (`zh-HK`) shares the script but not the vocabulary or dialogue register — see §2.5, §7.2 and §10; ship a separate `zh-HK` locale if Hong Kong is a target market. Examples use generic roles (A1–A5) and generic items (`{itemName}`, "a generator", "the workshop").

## 1. Anti-Translationese Ban List

Two kinds of leak are banned: 翻譯腔 (English-shaped Chinese) and 陸語硬轉 (Mainland vocabulary in Traditional characters). Vocabulary pairs live in §7.1; sentence patterns here. The ✓ column uses neutral Taiwan 國語 and the UI register of §2.

| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `你可以去使用X來做Y` / `你的倉庫中的物品` | `用X就能Y` / `倉庫裡的物品` | `你 / 你的 / 的` spam |
| `被海盜所襲擊` / `無法被放置在此處` | `遭海盜襲擊` / `這裡放不下` | `被……所` written passive |
| `當……的時候` / `在……的情況下` | `……時` / `要是……` | *when / in case of* frames |
| `此處已存在一個物品！` | `這裡已經有東西了。` | `存在` + `一個` article calque |
| `你已經擁有這項工具！` | `這個工具你已經有了。` | `擁有` legal register |
| `你的體力過低！` | `體力不足。` (UI) / `沒力氣了！` (dialogue) | *too low* calque |
| `聚焦` (interact prompt) | `使用` / `查看` / `交談` | *Focus* never meant *interact* |
| `獲取物品` (GET ITEMS) | `全部領取` / `全部拿取` | `獲取` is log-speak |
| `進行修理` / `進行製造` | `修理` / `製造` | `進行` + verbal noun = 公文腔 |
| `成功地儲存了` | `已儲存` / `儲存成功` | *successfully* calque |
| `這是一個很好的工具` | `這工具很好用` | `一個` as article |
| `它` for every object | omit | `它` spam |
| `透過……的方式` | `用……` | *by means of* calque |
| `做出決定` / `作出貢獻` | `決定` / `貢獻` | light-verb calque |
| `茲通知` / `敬請知悉` in dialogue | `跟你說一聲` / `請注意` | bureaucratic 公文 clichés |

## 2. Register, Address & Character Voice
* **`你` vs `您`:** UI, tutorials and warnings use `你` or no pronoun. `您` only for role-polite speakers (A3 to a senior, A5's cold courtesy). Never mix in one speaker's line. **Never `妳`** (female *you*, common in Taiwanese writing) for the player — see §4.
* **Taiwanese spoken flavour (口語):** particles `啦`, `喔`, `耶`, `欸`, `齁` and intensifiers `超`, `很扯`, `蠻` carry warmth in dialogue — one per sentence, never in system text. Use `搭檔` (TW) rather than `拍檔` (HK / Cantonese origin) unless the speaker is HK-coded.
* **Mainland spoken leaks** (`牛逼`, `靠譜`, `給力`, `視頻`) are `regional_leak` findings even in Traditional characters. Classical allusions (`廉頗老矣`) do not belong in casual speech.
* **Archetype voices (A1–A5):**

| ID | Archetype | Pronoun to player | Markers |
|---|---|---|---|
| A1 | Mentor / Veteran | `你` | `先……再說`, `別太勉強`, `我幫你……`, `欸` |
| A2 | Hotshot Rival | `你` | `根本鬼扯`, `快點`, `我才不會……`, `菜鳥` |
| A3 | Rookie / Teen | `您` | `我本來想……結果……`, `超`, `整個……`, `真的` |
| A4 | Scientist / Engineer | `你` (peer) / `您` (formal) | exact numbers, `先別……`, `等我……再說` |
| A5 | Outlaw / Antagonist | `您` (cold) | `聽說……`, `那就太可惜了`, threat by implication, no exclamation marks |

### 2.5 Hong Kong (`zh-HK`) register note
* HK UI and narration use Standard Written Chinese (書面語) with HK vocabulary (§7.2). **書面粵語** (`係`, `唔`, `嘅`, `咗`, `喺`, `佢`, `點解`) is used only for dialogue when the publisher explicitly asks for a Cantonese voice — never in UI, never mixed into a TW build.
* If a project ships to both markets, request a separate `zh-HK` locale with its own glossary and critic. A single `zh-Hant` file is a Taiwan file; HK players will read it, and will notice.

## 3. Spoken vs. Literary Tense
N/A — Chinese has no tense; aspect and time words do the work, and over-marking is the translationese tell:
* **`了`:** at most one per clause; English past does not require `了` (`我昨天修了那台機器了` ✗ → `我昨天修了那台機器` ✓).
* **`過`** = experience (`去過`), **`著`** = ongoing state (`門開著`), **`正在 / 在`** = progressive — never stack `正在……著`.
* **Perfect calques:** *I have repaired it* → `我已經修過了` ✗ → `修好了` ✓.
* **Literary vs spoken:** `之` / `其` / `此` / `乃` belong to item descriptions and lore only; dialogue uses `的` / `他的` / `這`.

## 4. Player Gender Neutrality
Written Chinese distinguishes `他 / 她 / 它 / 祂`, and Taiwanese writing additionally uses **`妳`** for a female *you* — a gender leak unique to zh-Hant.
1. **Always `你`, never `妳`,** for the player and for any character whose gender is not fixed.
2. **Never `他` / `她` for the player:** use `你`, `玩家` (system), `對方`, `這位` / `那位`, the name, or a title (`店主`, `老闆` — neutral; `老闆娘` is not).
3. **Banned address terms:** `小子`, `小夥子`, `丫頭`, `小姑娘`, `小姐`, `先生`, `兄弟`, `哥們`, `姊妹`, `帥哥`, `美女`. Allowed: `孩子` (elder → young), `朋友`, `夥伴`, `老闆`, `{playerName}`.
4. `TA` is Mainland online usage — not used in TW; rephrase instead.

| Context | Leaking ✗ | Neutral ✓ |
|---|---|---|
| Mentor letter | `妳把工坊撐起來了，真不簡單。` | `你把工坊撐起來了，真不簡單。` |
| Rival taunt | `小姑娘別逞強。` | `你就別逞強了。` |
| Gossip | `她把那艘船修好了。` | `那位店主把那艘船修好了。` |
| System log | `他獲得了成就` | `{playerName}獲得了成就` / `獲得成就` |

## 5. Plurals, Numbers & ICU
* **CLDR plural categories for `zh`: `other` only.** Nouns do not inflect: `1個`, `2個`, `5個`, `21個`, `0個`. `們` marks groups of people only and never follows a number. Do not create a `one` branch.
* **Measure words (量詞)** must match the noun: `個` generic, `台` machines (`台` is the locked form; `臺` is official-document style), `座` large structures, `艘` ships, `把` tools with handles, `張` flat items, `件` items/clothing, `塊` chunks, `枚` coins/medals, `名` / `位` people, `次` occurrences.

| Noun type | 量詞 | `{0}` = 1 / 2 / 5 / 21 / 25 |
|---|---|---|
| Generic item | `個` | `零件 1個` / `2個` / `5個` / `21個` / `25個` |
| Machine | `台` | `發電機 1台` / `2台` / `5台` / `21台` / `25台` |
| Large installation | `座` | `反應爐 1座` / `2座` / `5座` / `21座` / `25座` |
| Ship | `艘` | `飛船 1艘` / `2艘` / `5艘` / `21艘` / `25艘` |
| Person | `名` | `工人 1名` / `2名` / `5名` / `21名` / `25名` |

* **Two** is `兩` before a measure word when spelled out (`兩台`); `2台` with digits; `二台` ✗.
* **Placeholder patterns:** `{itemName} ×{0}` (preferred), `{itemName}：{0}`; `{0}個{itemName}` only if every item is `個`-countable, otherwise store the 量詞 in item data.
* **ICU:** `{count, plural, other {反應爐 ×#}}`.
* **Zero:** `0個` in tables; empty states `無` / `尚無`.
* **Large numbers:** UI `10,000`; dialogue `1萬` / `3億`. Never `1萬,000`.

## 6. Placeholder & Rich-Text Grammar Traps
* No articles, no inflection: `{0}` fits wherever a noun fits; the traps are 量詞 (§5), word order and spacing.
* **Word order:** `已加入{0}` ✓ and `{0}已加入` ✓; `加入：{0}` only in logs. Time/place precede the verb: `在{location}找到了{0}` ✓.
* **Spacing (locked):** no spaces between Chinese and Latin/digits (`100克`, `HP不足`, `{playerName}說`). Leading/trailing spaces in English sources must **not** be copied; log the seam in the ledger.
* **Concatenation ban:** `"{0}" + "已送達"` pieces cannot be reordered — request full sentences.
* **Rich text:** tag whole words or whole measures: `<b>{0}台</b>` ✓, `<b>{0}</b>台` ✗. Never split a 成語 or a compound (`<color=red>反應</color>爐` ✗). Keep `。！？` outside tags. BBCode, `<sprite>` and `<link>` pass through verbatim.
* **Label colons:** full-width `：` (`等級：{0}`), never `: `.
* **Engine-specific notes (no engine is assumed):**
  * Unity Smart String / ICU `{count, plural, …}`: single `other` branch; put the 量詞 in the branch text only when the noun is fixed.
  * Unreal `FText::Format` `{Count}`: same rule; `|hpp` is Korean-only.
  * Godot `%s` / `%d` and printf: positional — request indexed placeholders (`{0}`, `%1$s`) if the Chinese sentence reorders arguments.

## 7. Core UI Glossary

| English | zh-Hant / TW (default) | Notes |
|---|---|---|
| Save | `儲存` | `存檔` = save file / save game |
| Load | `讀取` | `讀檔` / `載入` (loading screen) |
| Quit | `離開` | `結束遊戲`, `回到主選單` |
| Settings / Options | `設定` | `選項` |
| OK | `確定` | closes a dialog |
| Confirm (an action) | `確認` | keep `確定` / `確認` distinct |
| Cancel | `取消` | — |
| Back | `返回` | — |
| Continue | `繼續` | `繼續遊戲` = continue save |
| New Game | `新遊戲` | `開始新遊戲` |
| Apply | `套用` | never `應用` (Mainland) |
| Delete | `刪除` | — |
| Yes / No | `是` / `否` | — |
| Pause | `暫停` | — |
| Resume | `繼續` | `恢復` for systems |
| Retry | `重試` | — |
| Skip | `略過` | `跳過` acceptable; one per project |
| Inventory | `背包` | `物品欄`; `倉庫` = storage |
| Equip | `裝備` | — |
| Craft | `製作` | `製造` (industrial), `建造` (structures) |
| Upgrade | `升級` | `強化` (RPG gear) |
| Level | `等級` / `Lv.` | — |
| Health | `生命值` | `HP` |
| Stamina | `體力` | `耐力` only if `體力` is already HP |
| Damage | `傷害` | — |
| Buy / Sell | `購買` / `販售` | `賣出` |

* **Button form:** 2–4 characters, verb or verb+object, no `。`, no `請`. Traditional glyphs are dense (`鑿`, `鑲`, `纜`) — prefer high-legibility characters in labels.
* **Term lock (one term = one translation):** e.g. `委託` (customer contract) vs `訂單` (workstation order); `配方` vs `藍圖`; an item named *industrial sludge* stays `工業污泥` everywhere — never "improved" to `膠泥`. Record every lock in the project glossary.

### 7.1 Mainland terms that must never appear in a TW build

| English | Mainland ✗ | Taiwan ✓ |
|---|---|---|
| Settings / Default | `設置` / `默認` | `設定` / `預設` |
| Screen / Fullscreen / Resolution | `屏幕` / `全屏` / `分辨率` | `螢幕` / `全螢幕` / `解析度` |
| Mouse / Spacebar | `鼠標` / `空格鍵` | `滑鼠` / `空白鍵` |
| Quality / Optimize | `質量` / `優化` | `品質` (`畫質`) / `最佳化` (`優化` is tolerated in patch notes and dialogue — WARN, not ERR) |
| Silicon | `硅` | `矽` (never `矽膠` for the raw resource) |
| Information / Message / File | `信息` / `文件` | `資訊` / `訊息` / `檔案` |
| Laser / Plasma | `激光` / `等離子` | `雷射` / `電漿` |
| Software / Program / Video | `軟件` / `程序` / `視頻` | `軟體` / `程式` / `影片` |
| Network / Data / Server | `網絡` / `數據` / `服務器` | `網路` / `資料` / `伺服器` |
| Menu / Log in / Save file | `菜單` / `登錄` / `存盤` | `選單` / `登入` / `存檔` |
| Duct-tape / makeshift fix | `土辦法` | `應急土法` / `拼湊頂著用` / `膠帶硬補` |

### 7.2 Hong Kong vocabulary (legitimate in zh-HK, a leak in zh-TW)

| English | Taiwan | Hong Kong |
|---|---|---|
| Software / Quality | `軟體` / `品質` | `軟件` / `質素` |
| Laser / Information | `雷射` / `訊息` | `激光` / `信息` |
| Screen / Network / Data | `螢幕` / `網路` / `資料` | `屏幕` / `網絡` / `數據` |
| Video / Print / Taxi | `影片` / `列印` / `計程車` | `視頻` / `打印` / `的士` |
| Partner / Awesome | `搭檔` / `超讚` | `拍檔` / `正` |

The linter should treat the HK column as ERR under the TW default and WARN under an HK variant; it must never silently pass either.

## 8. Typography, Numbers & Formatting
* **Punctuation is full-width:** `，。！？：；` and `、` for lists. No space after full-width punctuation. Taiwan fonts centre punctuation in the em-box (置中); Mainland fonts bottom-left it — another reason not to reuse an SC font.
* **Quotes (Taiwan / HK):** `「」` outer, `『』` inner. `“ ”` is Mainland style — banned. Titles use `《》`.
* **Ellipsis:** `……` (two U+2026). Never `...` or `。。。`.
* **Dash:** `——` only if the project allows dashes; otherwise rephrase with `，` / `：`. Never `" - "`.
* **Digits and Latin are half-width** (`100`, `HP`, `Lv.5`); full-width `１００` banned. Percent `50%`, multiplication `×3`.
* **台 / 臺:** lock `台` (`台灣`, `平台`, `一台`) for games; `臺` only if the client is a government body.
* **的 / 地 / 得:** `的` before nouns, `地` before verbs, `得` after verbs (`跑得快`). Taiwanese casual writing merges them; UI and narration keep the standard.
* **Numbers, dates, currency:** `1,000` / `0.5` / `2026年11月26日` or `2026/11/26` (no 民國 years in games) / `14:30` or `下午2:30` / `NT$100` or `100元` (HK: `HK$100`) / in-game `1,000金幣`.
* **No Title Case / caps:** emphasis is `「」` or a bold tag; never Latin ALL CAPS in Chinese UI.
* **Line breaking (避頭尾 + 標點懸掛):** no spaces; the engine breaks between any two characters **except**: `，。、！？：；」』）》` cannot start a line; `「『（《` cannot end one. Hanging punctuation is acceptable in body text if the engine supports it. Do not split `1,000`, `{0}台`, `Lv.5`. Unity TextMeshPro: *Line Breaking for Asian languages* lists; Unreal: ICU line breaking is default; Godot: `TextServer` — verify each with a two-line tooltip.
* **Font:** Taiwan glyph forms (Noto Sans CJK TC / Source Han Sans TW — 教育部標準字體: `骨`, `刃`, `戶`, `兌`); for HK use the HK variant (Noto Sans CJK HK) with HKSCS coverage. Verify Big5 (+ HKSCS) with `font_glyph_scanner.py`; system fonts are `.ttc`.

## 9. Text Expansion & UI Fit
* **Typical ratio vs English:** Traditional Chinese needs **far fewer characters** (≈0.4–0.6× count) but each glyph is ~1.8× a Latin glyph wide and visually denser than Simplified; visual width is typically **0.7–1.0×** English (rule of thumb — measure per font). Risks: stroke density at small sizes, fallback fonts, hanging punctuation.
* `ui_expansion_checker.py --locale zh-Hant` weights Wide/Fullwidth glyphs at 1.8× (same as zh-CN); count `……「」` (Ambiguous width) as wide. Density is not measured by the tool — enforce the minimum font size by review.
* **Fit rules:** buttons 2–4 characters, tabs ≤ 4, badges ≤ 2; line height ≥ 1.4; minimum **14 px** (Traditional needs more than Simplified; `鑲`, `纜`, `鬱` blur at 12 px).
* **Shortening (in order):** drop `請` / `您`; verb+object only (`全部領取物品` → `全部領取`); two-character compounds (`正在載入中` → `載入中`); abbreviations `Lv.`, `HP`.

## 10. Ratings, Legal & Sensitive Content
* **Taiwan — GSRR (遊戲軟體分級管理辦法):** 普遍級 (普), 保護級 (護, 6+), 輔12級, 輔15級, 限制級 (限, 18+). Descriptors: 暴力, 性, 恐怖, 毒品, 不當言語, 反社會性, 菸酒, 賭博. Text alone can raise the level through 不當言語 and 賭博.
* **Taiwan profanity policy:** `幹`, `操`, `他媽的`, `靠北` → 輔15 / 限; `靠`, `可惡`, `該死`, `鬼扯`, `白目`, `廢物` are the 輔12 ceiling; 普 / 護 titles stay at `糟糕`, `哎呀`.
* **Taiwan loot boxes:** probability disclosure for paid random items is mandatory (消費者保護處 online-game contract rules, in force since 2023) — translate odds strings exactly; never promise outcomes.
* **Hong Kong:** no mandatory game rating; COIAO (淫褻及不雅物品管制條例) governs obscene/indecent content. Cantonese 粗口 (`屌`, `撚`, `柒`, `鳩`, `閪`) is far stronger than written Mandarin swearing — only in a Cantonese-dialogue build cleared by the publisher. Political satire about mainland governance is a legal risk for the HK publisher under the national security framework; keep it out of HK builds.
* **Cross-strait naming:** in a TW build refer to the mainland as `中國大陸` / `大陸` where needed; never `中國台灣`; the language label is `繁體中文` (script), never a flag or `台灣` alone. Do not reuse Mainland-reviewed strings that rename places.
* **Religion and folk belief:** `媽祖`, `土地公`, temples and fortune-telling are everyday culture in TW and HK — fine; mocking them is not.
* Never translate rating icons or labels; copy them.

## 11. Golden Voice Anchors (A1–A5)
Each pair keeps the **same meaning** as the English gloss; only the Chinese changes. Roles and items are generic so the anchors transfer to any project.

**A1 Mentor / Veteran** — EN: *"Start with whatever you can salvage and get the workshop running again. Do that, and I'll send a few contracts your way."*
* ✗ `「從任何你能回收的東西開始，讓這個地方重新運轉起來。做到那一點，我會把合同發往你的方向。」`
* ✓ `「手邊能拆出什麼廢料就先用上，先把工坊撐起來再說。等上軌道了，我分幾筆委託給你。」`

**A2 Hotshot Rival** — EN: *"People keep saying I've lost my edge. Total nonsense. Fix her up as fast as you can."* (`her` = the Rival's racer)
* ✗ `「人們一直說我失去了優勢，那完全是胡說。盡可能快地把她修好。」`
* ✓ `「外頭那些人老愛說我過氣了。根本鬼扯！快幫我把這台寶貝修好。」`

**A3 Rookie / Teen** — EN: *"I tried to plug the leak with industrial sludge, but the moment the ship lifted off, it smoked and peeled right off."*
* ✗ `「我嘗試使用工業污泥修補洩漏，但飛船懸停的瞬間它就冒煙脫落了。」`
* ✓ `「我本來想拿工業污泥把漏口堵住，結果飛船才剛離地，那東西就冒煙，整塊掉下來了。」`

**A4 Scientist / Engineer** — EN: *"The generator's output is unstable. Don't run it above 80% until I've recalibrated the coils."*
* ✗ `「發電機的輸出是不穩定的。在我重新校準線圈之前，不要在80%以上運行它。」`
* ✓ `「發電機輸出還不穩。線圈我重新校正之前，別開到80%以上。」`

**A5 Outlaw / Antagonist** — EN: *"I hear the Council contacted you directly. I'd hate to see things get complicated for you."*
* ✗ `「我被告知議會已經直接聯繫了您。我不希望看到您的事情變得複雜。」`
* ✓ `「聽說議會直接找過您了。……要是事情變複雜了，那就太可惜了。」`

**UI register sample (not an archetype)** — EN: *"There's already an item here! Keep one reactor in the warehouse by crafting or buying one."*
* ✗ `「此處已存在一個物品！透過製造或購買在倉庫中保持1個反應爐。」`
* ✓ `「這裡已經有東西了。製作或購買一座反應爐，放進倉庫備用。」`

## 12. Linter Coverage Note
Currently in `lqa_linter.py` for `zh-Hant`: Mainland-term leak `設置|屏幕|全屏|默認|鼠標|分辨率|優化|激光|信息` (ERR — `優化` is a false positive in patch notes; `屏幕` / `激光` / `信息` are legitimate HK), `硅` (ERR), `被.{1,10}所` (WARN). Never use `\b` in CJK patterns; use plain alternations or lookarounds.

### Suggested linter patterns

| Severity | Regex | Message |
|---|---|---|
| ERR | `(?:設置\|全屏\|默認\|鼠標\|分辨率\|軟件\|程序\|視頻\|網絡\|服務器\|菜單\|登錄\|存盤\|等離子)` | Mainland term in `zh-Hant` (TW default) |
| WARN (ERR unless `--variant hk`) | `(?:屏幕\|激光\|信息\|質素\|數據\|打印\|的士)` | HK vocabulary — legitimate only in a zh-HK build |
| WARN | `優化` | `最佳化` in settings UI; `優化` tolerated in patch notes/dialogue |
| ERR | `硅` | Mainland character — TW/HK standard is `矽` |
| ERR | `[们这个来时说为对从后无与体设档过当该这里]` | Simplified character in a Traditional string |
| WARN | `[“”]` | Mainland quotes — use `「」` |
| WARN | `妳` | gendered *you* — use `你` |
| WARN | `當.{1,12}的時候` | *when…* frame — use `……時` |
| WARN | `進行(?:修理\|製造\|製作\|建造\|升級\|購買\|儲存\|載入)` | `進行` + verbal noun — use the plain verb |
| WARN | `成功地` | *successfully* calque |
| WARN | `[０-９Ａ-Ｚａ-ｚ]` | full-width digit/Latin — use half-width |
| WARN | `\.\.\.\|。。。` | wrong ellipsis — use `……` |
| WARN | `(?:小子\|小夥子\|丫頭\|小姑娘\|哥們\|兄弟\|姊妹\|帥哥\|美女)` | gendered address to player |
| WARN | `(?:係\|唔\|嘅\|咗\|喺\|佢)` | written Cantonese in a non-HK dialogue build |
