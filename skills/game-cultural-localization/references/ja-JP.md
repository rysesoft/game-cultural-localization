# Japanese (`ja-JP`) Game Localization & Culturalization Playbook

Target feel. **翻訳調ゼロの自然で生きた日本語、キャラが立つ役割語、日本のゲーマーに馴染みのあるUI**。

Scope. Standard Japanese (共通語) for any genre, engine and platform sold in Japan. Register lock, counters, line breaking and CERO compliance are **text-layer** concerns owned by this playbook. Glyph coverage is verified with `font_glyph_scanner.py`. Examples use generic roles (A1 to A5) and generic items (`{itemName}`, "a generator", "the workshop").

## 1. Anti-Translationese Ban List

Japanese players spot *翻訳調* (hon'yakuchō) instantly. Every row is a hard ban. The ✓ column uses the register locked in §2.3 (system text = 敬体).

| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `あなたは〜することができます` | `〜できます` / `〜できる` | `あなた` is almost never used. Known subjects are dropped |
| `彼 / 彼女 / それら` in every sentence | omit, or `あいつ` / `あの人` / `連中` / `その船` | Pronoun spam is the #1 marker of machine-shaped Japanese |
| `部品が倉庫へ転送されました` | `部品を倉庫に送りました` / `倉庫に届きました` | Inanimate passive is an English calque |
| `ここにアイテムを配置することはできません。` | `ここには設置できません。` | `〜することはできません` is wordy. Plain potential form |
| `ここにはすでにアイテムが存在します！` | `すでに何か置かれています。` | `存在する` is technical. System errors take `。`, not `！` |
| `このツールはすでに所有しています！` | `このツールはすでに持っています。` | `所有` is legal register |
| `スタミナが低すぎます！` | `スタミナが足りません。` | *too low* is a calque. Japanese says *not enough* |
| `フォーカス` (interact prompt) | `調べる` / `使う` / `話す` | *Focus* never meant *interact* in Japanese games |
| `アイテムを取得` (GET ITEMS) | `すべて受け取る` | `取得` is a programmer word |
| `修理を行う` / `〜を実施する` | `修理する` | Verbal-noun helper = appliance-manual Japanese |
| `〜する必要があります` (*you need to*) | `〜してください` / `〜しよう` | Direct request is natural. *need to* reads like a spec sheet |
| `〜に関して` / `〜において` | `〜について` / `〜で` | Written-formal particles leak into dialogue |
| `〜ことが可能です` | `〜できます` | The potential form is enough |
| `私はスピードだ！` (*I am speed!*) | `最速は俺だ！` / `スピードは俺のものだ！` | Noun-copula calque. Fan renderings of the film line (`僕は速い！`, `スピード、俺はスピードだ！`) are **unverified**, never cite them as the official dub. Confirm per project (same label as the transcreation ledger) |

## 2. Register, Address & Character Voice

### 2.1 Keigo levels (敬語), who gets which

| Level | Form | Use in games |
|---|---|---|
| 常体 (だ・である) | `〜だ`, `〜する`, `〜ない` | Casual dialogue, inner monologue, narration captions |
| 丁寧語 (です・ます) | `〜です`, `〜します`, `〜ください` | System messages, polite characters, tutorials |
| 尊敬語 | `いらっしゃる`, `〜される`, `ご覧になる` | NPCs addressing customers, nobles, superiors |
| 謙譲語 | `伺う`, `〜いたします`, `申し上げる` | Butlers, receptionists, formal letters |
| ビジネス敬語 (combined) | `〜でございます`, `〜いたしております` | Corporate/official characters only, never in UI |

`拝啓` is a letter-opening formula, not keigo, do not use it as a politeness example. Official characters. Letter body in です・ます, attached reports and dossiers in である.

### 2.2 Second-person address
* UI never addresses the player with a pronoun. `あなたの持ち物` ✗ → `持ち物` ✓.
* Dialogue. Pick per speaker, `お前` (rough-warm), `あんた` (familiar), `君` (gentle, senior to junior), `{playerName}さん`, or a title (`店主`, `工房長`, `隊長`). Never `坊主` / `息子` / `娘` / `お嬢ちゃん` / `兄ちゃん` / `姉ちゃん` for the player (§4).

### 2.3 UI register lock (locked for this suite)
One register per category, written into `JA-JP_BIBLE.md` in Phase 0 and never mixed.

| Category | Register | Example |
|---|---|---|
| System messages, dialogs, toasts, tooltips | 敬体 (です・ます), ends in `。` | `ここには設置できません。` (never `置けない。`) |
| Buttons, labels, menu items | 体言止め / dictionary form | `保存`, `続ける`, `すべて受け取る` |
| Tutorial narrator | 敬体 + soft volitional | `まずは工房を動かしてみましょう。` |
| Character-voiced hints (speaker tagged) | that speaker's 役割語 | `そこはもう埋まってるぞ。` |

A toast in 常体 (`埋まってるぞ！`) is legal only when the string carries a speaker tag. Untagged UI in 常体 is a `register` issue (score 2).

### 2.4 役割語 (Yakuwarigo), character voice architecture
Character voice lives in **first-person pronoun + second-person address + 語尾 (sentence-final particles)**. Lock a profile per archetype.

| ID | Archetype | 一人称 | To player | 語尾 / tone markers |
|---|---|---|---|---|
| A1 | Mentor / Veteran | `俺` | `お前` / `あんた` | `〜だな`, `〜しろよ`, `無理すんなよ`, `〜してやるよ` |
| A2 | Hotshot Rival | `俺` | `お前` | `〜だろ？`, `〜ってわけさ`, `笑わせんな`, dropped particles, fast |
| A3 | Rookie / Teen | `僕` (male NPC) / `私` (female or unfixed) | `〜さん` | youthful です・ます: `〜なんです`, `〜ちゃった`, `すごい` |
| A4 | Scientist / Engineer | `私` | `〜さん` | precise numbers, spoken contractions. `安定してません`, `〜しないと` |
| A5 | Outlaw / Antagonist | `私` (icy) or `俺` (thug) | `お前` / `貴様` | short 常体, `……`, `〜だな`, threat by implication |

## 3. Spoken vs. Literary Tense
N/A, Japanese has no spoken/literary past split like German *Perfekt/Präteritum*. The register axis of §2 replaces it. Three aspect traps still produce translationese.
* **Past progressive calque.** *Was trying to* → `試みていました` ✗ → `〜てみたんですが` / `〜ようとしたら` ✓.
* **Resultative `〜ている` vs event `〜た`.** *The door is locked* → `ドアは施錠されました` ✗ → `ドアには鍵がかかっている` ✓. *You found a key* → `鍵を見つけた` ✓ (not `見つけています`).
* **Narration captions** use 常体 `〜た` (`船が墜落した。`), not `〜ました`, unless the narrator is a polite character.

## 4. Player Gender Neutrality
Japanese leaks gender through **pronouns and 語尾**, not verb agreement.
1. **Player's own lines.** First person is always `私` (neutral in speech and writing). `俺` / `僕` / `あたし` / `うち` are banned for the player. No gendered 語尾: feminine `〜わ`, `〜かしら`, `〜のよ` and masculine `〜ぜ`, `〜ぞ`, `〜だろ` → neutral `〜だ`, `〜だね`, `〜かな`, `〜だよ`, `〜でしょう`. Trap. `無理よ` (feminine) vs `無理だよ` (neutral), keep `だ` before `よ/ね` after nouns and na-adjectives.
2. **NPC → player.** `{playerName}さん`, `お前`, `あんた`, `君`, or a job title. Banned. `坊主`, `息子`, `娘`, `お嬢さん`, `兄ちゃん`, `姉ちゃん`, `お兄さん`, `お姉さん`, `彼`, `彼女`.
3. **NPC about player (third person).** `あの人`, `例の工房長`, `プレイヤー` (system text), the name, never `彼 / 彼女`.
4. **Compliments and insults** stay neutral. `やるじゃないか` ✓. `男気があるな` ✗. `女の子なのに` ✗.

| Context | Leaking ✗ | Neutral ✓ |
|---|---|---|
| Player letter sign-off | `俺より` / `あたしより` | `私より` / `{playerName}より` |
| Player reaction line | `そんなの無理よ！` | `そんなの無理だよ！` |
| Mentor greeting | `よう、兄ちゃん。元気か？` | `よう、元気にしてたか？` |
| Rival taunt | `お嬢ちゃんには早いぜ` | `お前にはまだ早いな` |

## 5. Plurals, Numbers & ICU
* **CLDR plural categories for `ja`: `other` only.** Nouns never change for number. `1個` / `2個` / `5個` / `21個` / `0個` are one form. Do not create a `one` branch, it is dead code that ships untested.
* **The real problem is the counter word (助数詞).** `{0}個` is only right for small objects. Machines count with `台`, ships `隻`, long thin items `本`, flat items `枚`, large installations `基`, people `人`, animals `匹`, occurrences `回`.

| Noun type | Counter | `{0}` = 1 / 2 / 5 / 21 / 25 |
|---|---|---|
| Generic small item | `個` | `コア 1個` / `2個` / `5個` / `21個` / `25個` |
| Machine, vehicle | `台` | `発電機 1台` / `2台` / `5台` / `21台` / `25台` |
| Ship | `隻` | `船 1隻` / `2隻` / `5隻` / `21隻` / `25隻` |
| Large installation | `基` | `リアクター 1基` / `2基` / `5基` / `21基` / `25基` |
| Person | `人` | `作業員 1人` / `2人` / `5人` / `21人` / `25人` (read ひとり/ふたり, same spelling) |

* **Safe placeholder patterns** when the noun is a variable. `{itemName} ×{0}` (preferred, `×` is U+00D7, no space before it), `{itemName}：{0}` in lists, `{0}つ` only for 1 to 9 (native numerals, `10つ` is wrong). Never `{0}個の{itemName}` as a generic template, it mis-counts machines and people.
* **ICU** (single branch). `{count, plural, other {リアクター ×#}}`. Fixed noun. `{count, plural, other {作業員 #人}}`.
* **Zero.** `0個` is fine in tables. Empty-state messages say `なし` / `ありません`, not `0個のアイテム`.
* **Large numbers.** UI uses half-width digits with comma grouping (`10,000`). Dialogue may use `1万` / `3億`. Never mix (`1,0000`, `1万,000`).

## 6. Placeholder & Rich-Text Grammar Traps
* **Particles are invariant** (`{0}を`, `{0}に`, `{0}が` fit every noun), Japanese has no article/elision trap. The traps are word order, counters (§5) and spacing.
* **Verb-final order.** Keep the placeholder before the verb. `{0}を倉庫に送りました` ✓, never `送りました：{0}` to mimic English order.
* **Spacing.** Japanese has no inter-word spaces. Mandatory leading/trailing spaces in English sources (`" credits"`, `"x3 "`) must **not** be reproduced, log the concatenation seam in the transcreation ledger and request a full-sentence string. No space between digits/Latin and kana (`100クレジット`, `HPが回復`, `{playerName}さん`).
* **Concatenation ban.** `"{0}" + "を取得しました"` pieces cannot be reordered. Demand one string `{0}を手に入れた。`.
* **Rich text.** Wrap whole words, never split a kanji compound or a counter from its number. `<b>{0}個</b>` ✓, `<b>{0}</b>個` ✗ (breaks wrapping at the tag). Keep `！` / `。` outside `<color>` tags. Unknown tags (`<sprite>`, `<link>`, BBCode `[b]`) pass through verbatim, never translate attribute values.
* **Engine-specific notes (no engine is assumed).**
  * Unity Smart String / ICU. `{count:plural:other {個}}` is pointless for `ja`, use the single `other` branch.
  * Unreal `FText::Format`: `{Count}` with counters in the string. `|hpp` is Korean-only, not needed here.
  * Godot `%s` / `%d` and printf. Order is positional, if the target sentence reorders arguments, request named/indexed placeholders (`{0}`, `%1$s`) instead of rewording awkwardly.
* **Forced breaks.** Use the engine `\n`, never a 全角 space. Never insert ZWSP (U+200B) inside words to fix wrapping, fix the engine setting (§8.4).

## 7. Core UI Glossary
Market standard for PC and console. Lock one column per project in `JA-JP_BIBLE.md`. The first entry is the default.

| English | ja-JP (default) | Alternatives / notes |
|---|---|---|
| Save | `セーブ` | `保存` for settings/files |
| Load | `ロード` | `読み込み` for settings/files |
| Quit | `終了` | `ゲームを終了`, `タイトルに戻る` |
| Settings / Options | `設定` | `オプション` (console tradition) |
| OK / Confirm | `決定` (console) / `OK` (PC) | `確認` only for "confirm this action" dialogs |
| Cancel | `キャンセル` |, |
| Back | `戻る` |, |
| Continue | `続ける` | `続きから` = continue saved game |
| New Game | `はじめから` | `ニューゲーム` |
| Apply | `適用` |, |
| Delete | `削除` |, |
| Yes / No | `はい` / `いいえ` |, |
| Pause | `ポーズ` | `一時停止` |
| Resume | `再開` | `ゲームに戻る` (pause menu) |
| Retry | `リトライ` | `やり直す` |
| Skip | `スキップ` |, |
| Inventory | `持ち物` | `インベントリ`, `アイテム` |
| Equip | `装備` | `装備する` (dialog verb) |
| Craft | `作成` | `クラフト`, `製作`, one per project |
| Upgrade | `強化` | `アップグレード` |
| Level | `レベル` / `Lv.` | `Lv.{0}` in badges |
| Health | `HP` | `体力` if HP is not used |
| Stamina | `スタミナ` | never `持久力` for the stat |
| Damage | `ダメージ` |, |
| Buy / Sell | `購入` / `売却` | `買う` / `売る` in NPC dialogue |

* **Button form.** 体言止め or dictionary form, 2 to 6 full-width characters, no `。`, no です・ます, no `！`.
* **Console button mapping.** Never hard-code `○で決定 / ×でキャンセル` in text, the confirm button differs by platform and generation. Use the platform's glyph tags.
* **Term lock (one term = one translation).** E.g. `依頼` (customer contract) vs `注文` (workstation order). `設計図` (blueprint) vs `レシピ` (recipe). An item named *industrial sludge* stays `工業スラッジ` everywhere, never "improved" to `パテ` (putty) in dialogue. Record every lock in the project glossary.

## 8. Typography, Numbers & Formatting

### 8.1 全角 / 半角 matrix

| Element | Rule | ✓ | ✗ |
|---|---|---|---|
| Kana, kanji, Japanese punctuation | 全角 | `設定を保存しました。` | `設定を保存しました.` |
| Digits, Latin letters | 半角 | `HP 100`, `Lv.5` | `ＨＰ １００`, `Ｌｖ．５` |
| `！` `？` | 全角, no following space in UI | `本当ですか？` | `本当ですか? ` |
| Space character | half-width only between Latin tokens. 全角 space (U+3000) banned | `HP 100` | `設定　保存` |
| Brackets around Japanese | 全角 `（）` | `（任意）` | `(任意)` |

### 8.2 Punctuation & symbols
* Quotes. `「」` for speech and titles, `『』` nested or for work titles. Never `“”` or `''` for Japanese dialogue.
* Ellipsis. 三点リーダー doubled `……` (two U+2026). Never `...` or `・・・`.
* 長音符 policy (locked). Keep the trailing `ー` on loanwords, `サーバー`, `ユーザー`, `プレイヤー`, `コンピューター`, `エネルギー`. The JIS engineering style `サーバ` / `ユーザ` is banned. Never confuse `ー` (U+30FC) with `一` (one) or `－` (full-width hyphen).
* Dashes. `——` (two U+2014) only if the project allows `—`. Otherwise rephrase with `……` or `、`. Never `" - "`.
* `々` is fine inside words (`人々`) but may not start a line (§8.4).

### 8.3 Numbers, dates, currency
* `1,000` / `0.5` / `50%` (no space) / `×3` / `2026年11月26日` or `2026/11/26` / `14:30` (24h) / `¥1,000` or `1,000円` / in-game `1,000クレジット`.
* No Title Case concept. Never capitalise or stretch katakana for emphasis. Emphasis = `「」` or a bold tag.

### 8.4 Line breaking (禁則処理)
* Japanese has no spaces. The engine must break between any two characters **except** where 禁則 forbids it.
  * 行頭禁則 (cannot start a line). `、。，．）」』】〕！？ー々ゝゞぁぃぅぇぉっゃゅょァィゥェォッャュョ`
  * 行末禁則 (cannot end a line). `（「『【〔`
  * Do not split. Digit groups (`1,000`), number + counter (`{0}個`), `Lv.5`.
* Engine settings. Unity TextMeshPro → *TMP Settings › Line Breaking for Asian languages* (leading/following character lists). Unreal → the ICU line-break iterator is default in Slate/UMG, verify with a two-line tooltip. Godot → `TextServer` handles CJK breaks, verify `autowrap_mode`. If the engine only breaks at spaces, the string will overflow, escalate. Do not insert spaces.
* Ruby/furigana. Only if the engine renders it (TextMeshPro has no native `<ruby>`). Otherwise do not add readings. 縦書き (vertical text) is not used unless the design asks for it.

## 9. Text Expansion & UI Fit
* **Typical ratio vs English.** Japanese uses 30 to 50% **fewer characters**, but each CJK glyph is ~1.8× a Latin glyph wide and taller. Net visual width is typically **0.9 to 1.2×** English (industry rule of thumb, measure per font). The risks are glyph height and fallback fonts, not just width.
* `ui_expansion_checker.py --locale ja-JP` weights Wide/Fullwidth glyphs at 1.8×. `“”`, `…`, `→` are East-Asian *Ambiguous* and render full-width in Japanese fonts, budget them as wide.
* **Fit rules.** Buttons ≤ 6 full-width chars. Tabs ≤ 4. Badges ≤ 3 (`Lv.5`, `NEW`). Line height ≥ 1.4× font size. Minimum 12 px (14 px recommended) for kanji legibility.
* **Shortening (in order).** Drop です・ます (`保存しました` → `保存完了`). 体言止め (`すべて受け取る` → `一括受取`). Katakana → kanji (`インベントリ` → `持ち物`). Drop particles in labels (`残りの時間` → `残り時間`). Abbreviations `Lv.`, `HP`, `EXP`.
* **Font.** Ship a Japanese-first CJK font (Noto Sans CJK JP / Source Han Sans JP). A Chinese-first font draws Japanese glyphs with Chinese forms (`直`, `骨`, `画`). Run `font_glyph_scanner.py` against JIS X 0208 plus JIS2004 forms. System CJK fonts are `.ttc` collections.

## 10. Ratings, Legal & Sensitive Content
* **CERO** (Computer Entertainment Rating Organization). A (all ages), B (12+), C (15+), D (17+), Z (18+, restricted sale). Text alone can move a rating. Sexual language, drug use, crime instruction and discriminatory words (差別用語) are content descriptors.
* **Profanity policy.** Japanese has no lexical equivalent of *fuck*. Intensity is carried by rudeness (`てめえ`, `クソッ`, `ふざけんな`, `ぶっ殺す`). `クソ` / `ちくしょう` are safe from B. `死ね` / `殺す` as threats push to C+. Keep A-rated titles at `もう！` / `しまった！`.
* **Banned discriminatory vocabulary** (any rating). `キチガイ` / `気違い`, `めくら`, `つんぼ`, `外人` (use `外国人`), `土人`, `部落` as a slur. Use `目が不自由な`, `耳が聞こえない`.
* **Loot boxes / gacha.** コンプガチャ is banned under 景品表示法. Probability disclosure (`提供割合`) is industry standard, chance-based reward strings must not promise outcomes (`必ず手に入る` ✗ when it is a roll).
* **Virtual currency.** 資金決済法 requires expiry/usage wording for purchased currency. Keep legal strings verbatim from the publisher.
* **Cultural sensitivities.** No jokes about the Imperial family, the atomic bombings or natural disasters. `旭日旗` imagery is legal in Japan but a severe issue in `ko-KR` / `zh-*`, flag any shared asset.
* Never translate CERO icons or labels. Copy them.

## 11. Golden Voice Anchors (A1 to A5)
Each pair keeps the **same meaning** as the English gloss. Only the Japanese changes. Roles and items are generic so the anchors transfer to any project.

**A1 Mentor / Veteran**, EN. *"Start with whatever you can salvage and get the workshop running again. Do that, and I'll send a few contracts your way."*
* ✗ `「あなたが回収できるものから始めて、工房を再び稼働させてください。そうすれば私は契約をあなたの方向へ送ります。」`
* ✓ `「まずは使えるスクラップをかき集めて、工房をもう一度動かしてみろ。それができたら、俺の方からも仕事をいくつか回してやるよ。」`

**A2 Hotshot Rival**, EN. *"People keep saying I've lost my edge. Total nonsense. Fix her up as fast as you can."* (`her` = the Rival's racer)
* ✗ `「人々は私が優位性を失ったと言い続けています。それは完全に間違いです。彼女をできるだけ早く修理してください。」`
* ✓ `「俺の腕が落ちたって、みんな好き勝手言ってやがる。笑わせんな。こいつを大至急直してくれ。」`

**A3 Rookie / Teen**, EN. *"I tried to plug the leak with industrial sludge, but the moment the ship lifted off, it smoked and peeled right off."*
* ✗ `「私は工業用汚泥を使用して漏れを塞ごうと試みましたが、船が浮上した瞬間にそれは煙を出して剥がれました。」`
* ✓ `「工業スラッジで漏れを塞いでみたんですけど、船が浮いた瞬間に煙が出て、ベロッと剥がれちゃったんです。」`

**A4 Scientist / Engineer**, EN. *"The generator's output is unstable. Don't run it above 80% until I've recalibrated the coils."*
* ✗ `「発電機の出力は不安定です。私がコイルを再調整するまで、それを80%以上で稼働させないでください。」`
* ✓ `「発電機の出力が安定してません。コイルを調整し直すまで、80%以上は出さないでくださいね。」`

**A5 Outlaw / Antagonist**, EN. *"I hear the Council contacted you directly. I'd hate to see things get complicated for you."*
* ✗ `「評議会があなたに直接連絡したと聞きました。あなたの状況が複雑になるのを見たくありません。」`
* ✓ `「評議会から直接連絡があったそうだな。……面倒なことにならなきゃいいが。」`

**UI register sample (not an archetype)**, EN. *"There's already an item here! Keep one reactor in the warehouse by crafting or buying one."*
* ✗ `「ここにはすでにアイテムが存在します！製作または購入することによって倉庫にリアクターを1個保持してください。」`
* ✓ `「すでに何か置かれています。リアクターを作成または購入して、倉庫に1基用意してください。」`

## 12. Linter Coverage Note
Currently in `lqa_linter.py` for `ja-JP`: `あなたは` (ERR), `することができます` (WARN), `私はスピードだ` (ERR). CJK text has no word boundaries, never use `\b`. Use plain substrings or lookarounds.

### Suggested linter patterns

| Severity | Regex | Message |
|---|---|---|
| ERR | `あなた(?:は\|の\|が\|を\|に\|へ\|も\|と)` | hon'yakuchō `あなた`, drop it or use role/name |
| WARN | `(?:彼女\|彼ら\|彼)(?:は\|の\|が\|を\|に)` | third-person pronoun spam |
| WARN | `を(?:行う\|行います\|行って\|実施)` | verbal-noun helper, use the plain verb |
| WARN | `(?:ことが可能です\|ことはできません\|する必要があります)` | manual phrasing, use 〜できます / 〜できません / 〜してください |
| WARN | `[０-９Ａ-Ｚａ-ｚ]` | full-width digit/Latin, use half-width |
| WARN | `\u3000` | full-width space (U+3000) in string |
| WARN | `\.\.\.\|・・・` | ASCII/katakana ellipsis, use `……` |
| WARN | `[!?](?![\]}>)])` | ASCII `!`/`?`, use `！`/`？` |
| WARN | `(?:サーバ\|ユーザ\|プレイヤ\|コンピュータ)(?!ー)` | missing 長音符 (locked long-vowel style) |
| WARN | `\}個` | counter `個` on a variable noun, verify 助数詞 or use `×{0}` |
| ERR | `(?:私\|俺\|僕)はスピードだ` | *I am speed* calque |
| WARN | `(?:坊主\|お嬢ちゃん\|兄ちゃん\|姉ちゃん)` | gendered address to player |
