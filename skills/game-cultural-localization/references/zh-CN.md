# Simplified Chinese (`zh-CN`) Game Localization & Culturalization Playbook

Target feel: **地道鲜活的现代口语、人物各有腔调、大陆玩家熟悉的干练UI**——彻底消灭“翻译腔”。

Scope: Mainland China (普通话, 简体字, GB18030) for any genre, engine and platform. Taiwan / Hong Kong are a different locale — see `zh-Hant.md`; never generate one from the other by character conversion. Examples use generic roles (A1–A5) and generic items (`{itemName}`, "a generator", "the workshop").

## 1. Anti-Translationese Ban List

Chinese players call out stiff English-ordered sentences (*机翻味 / 翻译腔*) instantly. Hard bans; the ✓ column uses neutral 普通话 and the UI register of §2.

| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `你可以去使用X来做Y` / `你的仓库中的物品` | `用X就能Y` / `仓库里的物品` | `你 / 你的 / 的` spam; Chinese drops the known subject |
| `被海盗所袭击` / `无法被放置在这里` | `遭海盗袭击` / `这里放不下` | `被……所` is a written-formal passive; most English passives become active |
| `当……的时候` / `在……的情况下` | `……时` / `要是……` / `一旦……` | *when / in case of* frames add 4–6 dead characters |
| `这里已经存在一个物品！` | `这里已经有东西了。` | `存在` + `一个` = article calque |
| `你已经拥有此工具！` | `这件工具你已经有了。` | `拥有` is legal register |
| `你的体力过低！` | `体力不足。` (UI) / `没力气了！` (dialogue) | *too low* calque |
| `睡眠持续时间太短。` | `睡得太短，没休息好。` | *duration* nominalisation |
| `聚焦` (interact prompt) | `使用` / `查看` / `交谈` | *Focus* never meant *interact* |
| `获取物品` (GET ITEMS) | `全部拿走` / `全部收取` | `获取` is log-speak |
| `进行修理` / `进行制造` | `修理` / `制造` | `进行` + verbal noun = 公文腔 |
| `成功地保存了` | `已保存` / `保存成功` | *successfully* adverb calque |
| `这是一个很好的工具` | `这工具很好用` | `一个` as indefinite article |
| `它` for every object | omit | `它` spam reads machine-translated |
| `将会` for every *will* | `会` / `就` / nothing | future-marker calque |
| `我是速度！` (*I am speed!*) | `我就是速度！` / `唯快不破！` | noun-copula calque; neither ✓ is a verified film-dub line — confirm per project |

## 2. Register, Address & Character Voice
* **`你` vs `您`:** UI, tutorials and warnings use `你` or no pronoun at all (`你的仓库` → `仓库`). `您` is reserved for characters who are polite by role (A3 rookie to a senior, A4 in formal mode, A5's icy courtesy). Never mix `你` and `您` inside one speaker's line.
* **Short clauses over long modifiers:** English stacks *that/which* clauses after the noun; bad Chinese stuffs a 25-character `……的` modifier before it. Break into 6–14-character clauses driven by verbs.
* **Spoken particles (语气词):** `吧`, `呢`, `啊`, `嘛`, `啦` carry tone in dialogue — one per sentence, never in system text.
* **Dialect and era control:** UI and narration are neutral 普通话 — `这里` / `这个东西`, not Northern 儿化 (`这儿`, `那玩意儿`); 儿化 is allowed only for a speaker tagged as Northern in the bible. No 港台腔 (`有没有搞错`), no classical allusions (`廉颇老矣`) in casual speech, no dated internet slang (`yyds`, `绝绝子`) unless the brand voice asks.
* **Archetype voices (A1–A5):**

| ID | Archetype | Pronoun to player | Markers |
|---|---|---|---|
| A1 | Mentor / Veteran | `你` | `先……再说`, `别硬撑`, `我给你……`, short imperatives |
| A2 | Hotshot Rival | `你` | `纯属扯淡`, `赶紧`, `我可不……`, boasts |
| A3 | Rookie / Teen | `您` | `我试了……结果……`, `真的`, `整个……`, breathless chaining |
| A4 | Scientist / Engineer | `你` (peer) / `您` (formal) | exact numbers, `先别……`, `等我……再说` |
| A5 | Outlaw / Antagonist | `您` (cold) | `听说……`, `那就太可惜了`, threat by implication, no exclamation marks |

## 3. Spoken vs. Literary Tense
N/A — Chinese has no tense; aspect and time words do the work, and over-marking is the translationese tell:
* **`了`:** at most one per clause; English past does not require `了` (`我昨天修了那台机器了` ✗ → `我昨天修了那台机器` ✓). Sequential narration often needs no `了` at all.
* **`过`** = experience (`去过`), **`着`** = ongoing state (`门开着`), **`正在 / 在`** = progressive — never stack `正在……着`.
* **Perfect calques:** *I have repaired it* → `我已经修过了` ✗ (sounds like *at some point*) → `修好了` ✓.
* **Literary vs spoken:** `之` / `其` / `此` / `乃` belong to item descriptions and lore only; dialogue uses `的` / `他的` / `这`.

## 4. Player Gender Neutrality
Written Chinese distinguishes `他 / 她` (and `它` / `祂`); spoken Chinese does not. Rules:
1. **Never write `他` or `她` for the player.** Use `你` (direct address), `玩家` (system), `对方`, `这位` / `那位`, the player's name, or a title (`店主`, `老板` — neutral; `老板娘` is not).
2. **`TA`** (Latin letters) is tolerated only in casual/online UI (`TA的主页`); never in narrative or dialogue.
3. **Banned address terms:** `小子`, `小伙子`, `丫头`, `姑娘`, `小姐`, `兄弟`, `哥们`, `姐妹`, `先生`, `女士`. Allowed: `孩子` (elder → young), `伙计`, `朋友`, `老板`, `{playerName}`.
4. **Descriptors:** `年轻小伙` / `美女` ✗ → `年轻人` / `这位高手` ✓.

| Context | Leaking ✗ | Neutral ✓ |
|---|---|---|
| Third-person gossip | `她把工坊盘活了。` | `那位店主把工坊盘活了。` |
| Mentor greeting | `小子，好久不见。` | `好久不见啊。` |
| Rival taunt | `小姑娘别逞强。` | `你就别逞强了。` |
| System log | `他获得了成就` | `{playerName}获得了成就` / `获得成就` |

## 5. Plurals, Numbers & ICU
* **CLDR plural categories for `zh`: `other` only.** Nouns do not inflect: `1个`, `2个`, `5个`, `21个`, `0个`. `们` marks groups of people only and never follows a number (`3个玩家们` ✗). Do not create a `one` branch.
* **Measure words (量词)** must match the noun: `个` generic, `台` machines, `座` large structures, `艘` ships, `把` tools with handles, `张` flat items, `件` items/clothing, `块` chunks, `枚` coins/medals, `名` / `位` people, `次` occurrences.

| Noun type | 量词 | `{0}` = 1 / 2 / 5 / 21 / 25 |
|---|---|---|
| Generic item | `个` | `零件 1个` / `2个` / `5个` / `21个` / `25个` |
| Machine | `台` | `发电机 1台` / `2台` / `5台` / `21台` / `25台` |
| Large installation | `座` | `反应堆 1座` / `2座` / `5座` / `21座` / `25座` |
| Ship | `艘` | `飞船 1艘` / `2艘` / `5艘` / `21艘` / `25艘` |
| Person | `名` | `工人 1名` / `2名` / `5名` / `21名` / `25名` |

* **Two** is `两` before a measure word in spelled-out speech (`两台`); with digits `2台` is fine; `二台` ✗.
* **Placeholder patterns:** `{itemName} ×{0}` (preferred), `{itemName}：{0}`; `{0}个{itemName}` only if every item in the table is `个`-countable, otherwise store the 量词 in item data.
* **ICU:** `{count, plural, other {反应堆 ×#}}`.
* **Zero:** `0个` in tables; empty states `无` / `暂无`.
* **Large numbers:** UI `10,000`; dialogue `1万` / `3亿`. Never `1万,000`.

## 6. Placeholder & Rich-Text Grammar Traps
* No articles, no inflection: `{0}` fits wherever a noun fits; the traps are 量词 (§5), word order and spacing.
* **Word order:** `已添加{0}` ✓ and `{0}已添加` ✓ are both natural; `添加：{0}` only in logs. Time/place precede the verb: `在{location}找到了{0}` ✓.
* **Spacing (locked):** no spaces between Chinese and Latin/digits (`100克`, `HP不足`, `{playerName}说`). Leading/trailing spaces in English sources (`" credits"`) must **not** be copied; log the seam in the ledger.
* **Concatenation ban:** `"{0}" + "已送达"` pieces cannot be reordered — request full sentences.
* **Rich text:** tag whole words or whole measures: `<b>{0}台</b>` ✓, `<b>{0}</b>台` ✗ (breaks wrapping at the tag). Never split a 成语 or a compound (`<color=red>反应</color>堆` ✗). Keep `。！？` outside tags. BBCode (`[b]…[/b]`), `<sprite>` and `<link>` pass through verbatim.
* **Label colons:** full-width `：` after a label (`等级：{0}`), never `: `.
* **Engine-specific notes (no engine is assumed):**
  * Unity Smart String / ICU `{count, plural, …}`: single `other` branch for `zh`; put the 量词 in the branch text (`other {# 台}`) only when the noun is fixed.
  * Unreal `FText::Format` `{Count}`: same rule; `|hpp` is Korean-only.
  * Godot `%s` / `%d` and printf: positional — if the Chinese sentence reorders arguments, request indexed placeholders (`{0}`, `%1$s`) rather than forcing English order.

## 7. Core UI Glossary

| English | zh-CN (default) | Notes |
|---|---|---|
| Save | `保存` | `存档` = a save file / save game |
| Load | `读取` | `读档` / `读取存档` for save games |
| Quit | `退出` | `退出游戏`, `返回主菜单` |
| Settings / Options | `设置` | `选项` (older) |
| OK | `确定` | closes a dialog |
| Confirm (an action) | `确认` | commits an action; keep `确定` / `确认` distinct |
| Cancel | `取消` | — |
| Back | `返回` | — |
| Continue | `继续` | `继续游戏` = continue save |
| New Game | `新游戏` | `开始新游戏` |
| Apply | `应用` | — |
| Delete | `删除` | — |
| Yes / No | `是` / `否` | — |
| Pause | `暂停` | — |
| Resume | `继续` | `恢复` for systems |
| Retry | `重试` | — |
| Skip | `跳过` | — |
| Inventory | `背包` | `物品栏`; `仓库` = storage |
| Equip | `装备` | — |
| Craft | `制作` | `制造` (industrial), `建造` (structures) |
| Upgrade | `升级` | `强化` (RPG gear) |
| Level | `等级` / `Lv.` | — |
| Health | `生命值` | `HP` |
| Stamina | `体力` | `耐力` only if `体力` is already used for HP |
| Damage | `伤害` | — |
| Buy / Sell | `购买` / `出售` | — |

* **Button form:** 2–4 characters, verb or verb+object, no `。`, no `请`.
* **Term lock (one term = one translation):** e.g. `委托` (customer contract) vs `订单` (workstation order); `配方` vs `蓝图`; an item named *industrial sludge* stays `工业污泥` everywhere — never "improved" to `胶泥` in dialogue. Record every lock in the project glossary.

### 7.1 zh-CN vs zh-Hant terminology (never cross the line)

| English | zh-CN | zh-Hant (TW) |
|---|---|---|
| Software / Program | `软件` / `程序` | `軟體` / `程式` |
| Save file / Load | `存档` / `读档` | `存檔` / `讀檔` |
| Settings / Default | `设置` / `默认` | `設定` / `預設` |
| Video | `视频` | `影片` |
| Mouse / Keyboard | `鼠标` / `键盘` | `滑鼠` / `鍵盤` |
| Screen / Resolution | `屏幕` / `分辨率` | `螢幕` / `解析度` |
| Information / Message / File | `信息` / `消息` / `文件` | `資訊` / `訊息` / `檔案` |
| Quality / Optimize | `质量` / `优化` | `品質` / `最佳化` |
| Laser / Silicon | `激光` / `硅` | `雷射` / `矽` |
| Network / Data / Server | `网络` / `数据` / `服务器` | `網路` / `資料` / `伺服器` |
| Menu / Log in / Apply | `菜单` / `登录` / `应用` | `選單` / `登入` / `套用` |

## 8. Typography, Numbers & Formatting
* **Punctuation is full-width:** `，。！？：；` and the enumeration comma `、` for lists (`修理、制造、升级`). No space after full-width punctuation.
* **Quotes (Mainland):** `“ ”` outer, `‘ ’` inner. `「」` is Taiwan/HK style — banned in zh-CN. Titles use `《》`.
* **Ellipsis:** `……` (two U+2026, six dots). Never `...` or `。。。`.
* **Dash:** `——` (two U+2014) only if the project allows dashes; otherwise rephrase with `，` / `：`. Never `" - "`.
* **Digits and Latin are half-width** (`100`, `HP`, `Lv.5`); full-width `１００` / `ＨＰ` banned. Percent `50%`, multiplication `×3`.
* **的 / 地 / 得:** `的` before nouns (`漂亮的船`), `地` before verbs (`慢慢地走`), `得` after verbs for degree/result (`跑得快`, `修得好`). `跑的快` ✗, `慢慢的走` ✗ — LLM output confuses these constantly.
* **Numbers, dates, currency:** `1,000` / `0.5` / `2026年11月26日` or `2026-11-26` / `14:30` / `¥100` or `100元` / in-game `1,000金币`.
* **No Title Case / caps:** emphasis is `“ ”` or a bold tag; never Latin ALL CAPS in Chinese UI.
* **Line breaking:** Chinese has no spaces; the engine breaks between any two characters **except** 避头尾 rules: `，。、！？：；”’）》」` cannot start a line; `“‘（《「` cannot end one. 标点悬挂 (hanging punctuation) is acceptable in body text if the engine supports it. Do not split `1,000`, `{0}台`, `Lv.5`. Unity TextMeshPro: *Line Breaking for Asian languages* lists; Unreal: ICU line breaking is default; Godot: `TextServer` — verify each with a two-line tooltip.
* **Font:** Chinese-first CJK font with GB18030 coverage (Noto Sans CJK SC / Source Han Sans SC); a Japanese-first font draws `骨`, `直`, `关` in Japanese forms. Verify with `font_glyph_scanner.py` (system fonts are `.ttc`).

## 9. Text Expansion & UI Fit
* **Typical ratio vs English:** Chinese needs **far fewer characters** (≈0.4–0.6× count) but each glyph is ~1.8× a Latin glyph wide; visual width is typically **0.7–1.0×** English (rule of thumb — measure per font). The real risks: tall glyphs clipping, fallback fonts, hanging punctuation.
* `ui_expansion_checker.py --locale zh-CN` weights Wide/Fullwidth glyphs at 1.8×; count `……“”` (Ambiguous width) as wide.
* **Fit rules:** buttons 2–4 characters, tabs ≤ 4, badges ≤ 2 (`新`, `已读`); line height ≥ 1.4; minimum 12 px (14 px recommended for dense characters like `警`, `壤`).
* **Shortening (in order):** drop `请` / `您`; verb+object only (`全部收取物品` → `全部收取`); two-character compounds (`正在加载中` → `加载中`); abbreviations `Lv.`, `HP`.

## 10. Ratings, Legal & Sensitive Content
Mainland China has no PEGI-style board; publishing requires a **版号** (NPPA licence) and domestic 适龄提示 labels (8+ / 12+ / 16+). Content review is strict and the **text layer** is read. Checklist:
* **Untranslated English in UI is a review finding** — `GET ITEMS`, `OK`, `NEW` must be Chinese (`确定`, `新`). Brand names and `HP` / `Lv.` abbreviations are tolerated if consistent.
* **Political geography:** never list `台湾`, `香港`, `澳门` as countries; the language selector label is `简体中文` / `繁體中文` (script), never `台灣` or a flag. Maps and region names follow PRC naming.
* **Blood, corpses, religion:** vivid blood (`鲜血四溅`), corpses/skeletons (`骷髅`, `尸体`) and real religious content (scripture, named sects) are frequent rejection causes — tone down in text even when the art is already adjusted.
* **Gambling words:** `赌博`, `赌场`, `下注` trigger minor-protection rules; prefer `竞猜`, `抽奖`; loot-box odds disclosure is mandatory and must be translated exactly.
* **Superstition (迷信):** `占卜`, `招魂`, `鬼` as real-world practice can be flagged; fantasy framing is usually fine.
* **Profanity:** `操`, `他妈的`, `傻逼`, `妈的` are banned in licensed releases; `放屁` is borderline — the ceiling is `扯淡`, `胡说`, `该死`, `混蛋`, `见鬼`, `废物`.
* **敏感词:** leaders' names, `六四`, `法轮功`, sensitive dates — never, even as jokes; filters also catch homophones, so avoid puns on them.
* **Platform note:** global (Steam) and domestic (WeGame / TapTap) builds may carry different strings; keep a compliance column in the ledger.

## 11. Golden Voice Anchors (A1–A5)
Each pair keeps the **same meaning** as the English gloss; only the Chinese changes. Roles and items are generic so the anchors transfer to any project.

**A1 Mentor / Veteran** — EN: *"Start with whatever you can salvage and get the workshop running again. Do that, and I'll send a few contracts your way."*
* ✗ `“从任何你能回收的东西开始，让这个地方重新运转起来。做到那一点，我会把我的几份合同发往你的方向。”`
* ✓ `“手头能拆出什么料就先用上，把工坊重新盘活再说。等运转起来了，我分几单委托给你。”`

**A2 Hotshot Rival** — EN: *"People keep saying I've lost my edge. Total nonsense. Fix her up as fast as you can."* (`her` = the Rival's racer)
* ✗ `“人们一直说我已经失去了我的锋芒，那完全是胡扯。尽可能快地把她修好。”`
* ✓ `“外头那帮人老说我跑不动了。纯属扯淡！赶紧帮我把这宝贝修好。”`

**A3 Rookie / Teen** — EN: *"I tried to plug the leak with industrial sludge, but the moment the ship lifted off, it smoked and peeled right off."*
* ✗ `“我尝试使用工业污泥修补泄漏，然而在飞船悬停的瞬间它冒烟并脱落了。”`
* ✓ `“我试过拿工业污泥把漏口堵上，结果飞船刚一离地，那东西就冒烟，整块掉下来了。”`

**A4 Scientist / Engineer** — EN: *"The generator's output is unstable. Don't run it above 80% until I've recalibrated the coils."*
* ✗ `“发电机的输出是不稳定的。在我重新校准线圈之前，不要在80%以上运行它。”`
* ✓ `“发电机输出还不稳。线圈我重新校准之前，别开到80%以上。”`

**A5 Outlaw / Antagonist** — EN: *"I hear the Council contacted you directly. I'd hate to see things get complicated for you."*
* ✗ `“我被告知议会已经直接联系了您。我讨厌看到您的处境变得复杂。”`
* ✓ `“听说议会直接找过您了。……要是事情闹复杂了，那就太可惜了。”`

**UI register sample (not an archetype)** — EN: *"There's already an item here! Keep one reactor in the warehouse by crafting or buying one."*
* ✗ `“此处已经存在一个物品！通过制造或购买在仓库中保持1个反应堆。”`
* ✓ `“这里已经有东西了。制造或购买一座反应堆，放进仓库备用。”`

## 12. Linter Coverage Note
Currently in `lqa_linter.py` for `zh-CN`: Taiwan-term leak `\b(?:螢幕|設定|預設|滑鼠|解析度)\b` (ERR — **broken**: `\b` never matches between CJK characters, so `遊戲設定` passes), `被.{1,10}所` (WARN), `已经存在一个` (WARN). Never use `\b` in CJK patterns; use plain alternations or lookarounds.

### Suggested linter patterns

| Severity | Regex | Message |
|---|---|---|
| ERR | `(?:螢幕\|設定\|預設\|滑鼠\|解析度\|軟體\|存檔\|讀檔\|影片\|網路\|資料\|程式\|選單\|登入\|套用\|品質\|最佳化\|雷射\|伺服器)` | Taiwan `zh-Hant` term leaked into `zh-CN` |
| ERR | `[們這個來時說為對從後無與體設檔過當該這裡]` | Traditional character in a Simplified string |
| WARN | `[「」『』]` | Taiwan/HK corner quotes — use `“ ”` in zh-CN |
| WARN | `当.{1,12}的时候` | *when…* frame — use `……时` |
| WARN | `进行(?:修理\|制造\|制作\|建造\|升级\|购买\|保存\|加载)` | `进行` + verbal noun — use the plain verb |
| WARN | `成功地` | *successfully* calque |
| WARN | `将会` | future-marker calque |
| WARN | `[０-９Ａ-Ｚａ-ｚ]` | full-width digit/Latin — use half-width |
| WARN | `\.\.\.\|。。。` | wrong ellipsis — use `……` |
| WARN | `(?<![{<\[\w])[A-Za-z]{4,}(?![}>\]\w])` | untranslated English word outside a tag/placeholder (版号 review risk) |
| WARN | `(?:小子\|小伙子\|丫头\|小姑娘\|哥们\|兄弟\|姐妹)` | gendered address to player |
| WARN | `(?:操你\|他妈的\|傻逼\|妈的)` | profanity banned in licensed Mainland releases |
