# Game Cultural Localization

**Yapay zekâyla çevrilen oyun metni çoğu zaman doğru okunur ama yine de çeviri olduğu belli olur. Bu eklenti metni oyuncunun kendi dilinde yazılmış gibi seslendirir.** Yapay zekâ kodlama ajanları ve LLM araçları için hazırlanmış bir oyun yerelleştirme paketidir. Makine çevirisi ya da LLM taslaklarını 15 dilde doğal oyun metnine dönüştürür. Sonucu üç ayrı model ailesinden oluşan bir jüri satır satır denetler, döngüde anadili konuşan bir insan denetçiye gerek kalmaz. Yapay zekâ destekli çeviriyle oyun çıkaran ama çeviri kokan metni yayınlamak istemeyen yerelleştirme sorumluları, anlatı ekipleri ve bağımsız geliştiriciler için yapıldı. Birincil hedef Antigravity. Claude Code, Gemini CLI, Cursor, Codex ve herhangi bir düz LLM API'si de açık Agent Skills biçimi sayesinde destekleniyor.

[![CI](https://github.com/rysesoft/game-cultural-localization/actions/workflows/tests.yml/badge.svg)](https://github.com/rysesoft/game-cultural-localization/actions/workflows/tests.yml) [![License MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE) [![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB.svg)](#teknik-özellikler) [![Languages 15](https://img.shields.io/badge/languages-15-success.svg)](#desteklenen-diller) [![Zero dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#teknik-özellikler)

[English README](./README.md). Geliştiren ve bakımını yapan [Rysesoft](https://github.com/rysesoft).

## Sorun

Makine ve LLM taslakları anlamı doğru, sesi yanlış verir. İngilizce kelime sırasını korur, resmî yazışma fiillerine sarılır ve hedef dilin hiç kullanmayacağı zamirleri tekrar tekrar yazar. Oyuncu bunu ilk satırda duyar. Aşağıdaki örnekler dil rehberlerindeki Golden Voice Anchors satırlarından alındı, böylece ajanlar da insanlar da aynı satırlar üzerinden ayar yapar.

| Dil | Kaynak (EN) | Tipik MT ya da LLM çıktısı | Bu paketin beklediği | Neden |
|---|---|---|---|---|
| `tr-TR` A1 Usta | Start with whatever you can salvage and get the workshop running again. Do that, and I'll send a few contracts your way. | Mevcut malzemeleri geri dönüştürerek atölye operasyonlarını yeniden tesis et, ardından sana sözleşmeler aktaracağım. | Eldeki hurdadan ne çıkarabiliyorsan onunla başla, şu dükkânı yeniden ayağa kaldır. Çarkı bir döndür, kendi işlerimden birkaçını sana paslarım. | Bürokratik fiillerin yerini atölye dili aldı, kıdemli ustanın sıcak sesi korundu |
| `de-DE` A1 Usta | Aynı satır | Beginne mit der Verwertung verfügbarer Materialien, um den Werkstattbetrieb wiederherzustellen, und ich werde Aufträge an dich übertragen. | Fang mit dem an, was du aus dem Schrott rausholen kannst, und bring den Laden wieder zum Laufen. Dann schieb ich dir ein paar von meinen Aufträgen rüber. | Konuşma dilinde du hitabı, isim cümlesi yok, İngilizceden kopyalanmış gelecek zaman yok |
| `ja-JP` A4 Mühendis | The generator's output is unstable. Don't run it above 80% until I've recalibrated the coils. | 発電機の出力は不安定です。私がコイルを再調整するまで、それを80%以上で稼働させないでください。 | 発電機の出力が安定してません。コイルを調整し直すまで、80%以上は出さないでくださいね。 | Gereksiz 私 ve それ atıldı, kullanım kılavuzu dili yerine sohbet havasında 丁寧語 |

Dördüncü sütun paketin ulaşmak istediği sonuç. Sayfanın geri kalanı oraya nasıl varıldığını ve bunun nasıl kanıtlandığını anlatıyor.

## Nasıl Çözüyor

| Katman | Ne yapar |
|---|---|
| Bağlam | Tek bir satıra dokunulmadan önce Claude Opus üzerinde çalışan bir orkestratör ve Claude Sonnet üzerinde çalışan ajanlar oyunun kodunu, sahnelerini, prefab'larını ve metin tablolarını inceler, belirsiz kalan her şeyi stüdyoya sorar ve bir bağlam haritası yazar. Çevirmen, eleştirmen ve jüri işe bu haritayı okuyarak başlar, çünkü aynı kelime yerine göre değişir (*Play* bir oyun için *Oyna*, müzik için *Çal* olur) |
| Zanaat | Golden Voice Anchors satırları ve beş ses arketipi içeren 15 kültürelleştirme rehberi. Kültürelleştirme ajanı Pass 1 ve Pass 2'yi yazar, anadil kulağı denetçisi İngilizceyi hiç göstermeyen kör bir dilimi puanlar |
| Kapılar | Saf Python ile yazılmış linter, arayüz taşma denetçisi, font glif tarayıcısı ve eleştiri doğrulayıcısı, çıkış kodları 0, 1 ve 2. Bozuk bir yer tutucu, kesilen bir buton ya da eksik bir glif derlemeye ulaşmaz |
| Ölçüm (2.2) | Claude, Gemini ve DeepSeek her satırı üç kademede kör olarak değerlendirir, profesyonel bir referans onları kalibre eder ve her değişiklik gerekçe, kanıt, güven oranı ve güven seviyesiyle gelir |

## Çok Aileli Jüri (2.2)

2.2 sürümü tek denetçinin yerine üç model ailesinden oluşan bir jüri koyar ve sonucun ne kadar doğal göründüğünü döngüde anadili konuşan bir insan olmadan ölçer. Kendi üslubunu kayıran bir aileyi diğer ikisi oylamada geçer.

| Adım | Ne olur |
|---|---|
| Dil paketi | `build_language_pack.py`, lisanslı oyun ve arayüz derlemleriyle stüdyonun kendi çevirisinden `langpack/<locale>/` klasörünü kurar. Copyleft kaynaklar yerel makinede kalır |
| Isınma ve çiftler | `warmup_loader.py` her prompta 30 ile 50 arası doğal satır ekler, `build_contrastive_set.py` doğal satırları bilerek kelimesi kelimesine çevrilmiş robot satırlarla eşler |
| Kalibrasyon | `eval_critic.py` her jüri üyesinin çiftlerin en az %85'inde doğal satırı seçtiğini kontrol eder |
| Jüri | `jury.py` kör dilim üzerinde Claude, Gemini ve DeepSeek'ten oluşan üç kademeyi çalıştırır. Net satırlar erkenden karara bağlanır, kritik satırlar doğrudan en güçlü kademeye gider, anlaşmazlıklar anonim müzakereden geçer |
| Yeniden yazım | `pass2_rewrite.py` üç aday yazar, en ucuz kademe birini kör olarak seçer, `validate_critique` seçileni denetler |
| Rapor | `report_changes.py` her değişikliği eski ve yeni metin, gerekçe, kanıt, güven oranı ve oylarla listeler. Geliştirici kabul eder ya da reddeder, `tm.py` kararı hatırlar, `export_translations.py` sonucu oyunun kendi tablolarına yazar |

**Uzlaşma.** Her kademede her aileden bir model bulunur. Üç puanın hepsi 4 ya da 5 ise ve aralarındaki fark en fazla 1 ise satır geçer. Puanlardan biri 3 ya da altındaysa veya puanlar arasında 2 ya da daha fazla fark varsa satır bir üst kademeye çıkar. 2 ya da altında bir puan satırı doğrudan J3'e gönderir. J3 de anlaşamazsa jüri üyeleri birbirlerinin gerekçelerini model adları gizlenmiş olarak okur ve yeniden oy verir. Çoğunluk satırı karara bağlar, çoğunluk çıkmazsa satır çözülmemiş olarak geliştiriciye gider.

**Bütçe sınırları.** Bir grubun satırlarının %30'undan fazlası J2'ye ya da %10'undan fazlası J3'e gidecekse çalışma durur ve raporu yazar. Bu noktada sorun tek tek satırlarda değil, Pass 1'de ya da prompttadır.

**Güven seviyeleri.** Her değişiklik raporu kararlarına ne kadar güvenilebileceğini söyler.

| Seviye | Ne zaman | Kararın anlamı |
|---|---|---|
| measured (ölçülmüş) | profesyonel referans ve geçilmiş bir kalibrasyon | profesyonel çeviriye göre ölçülmüş |
| estimated (tahmini) | bir dil paketi kurulu | dolaylı sinyallerden tahmin edilmiş |
| rule based (kurala dayalı) | dil paketi yok | satır hakkında yalnızca kurala dayalı kapılar söz sahibi |

### Türkçe dil paketi

`langpack/tr-TR/` eklentiyle birlikte gelir. Isınma derleminde 7054 satır var. Bunların yaklaşık 1400'ü bir Rysesoft oyununun profesyonel Türkçe çevirisinden, geri kalanı Godot editörü ve Pixelorama çevirilerinden (MIT) geliyor. Wesnoth, OpenTTD ve KDE gibi copyleft derlemler paketi yalnızca onu kuran makinede besler, hiçbir zaman dağıtılmaz. Stüdyo referansı her filtre sezgisinden üstün tutulur. Bir kural profesyonel çeviriyi sürekli işaretliyorsa kural daraltılır, satır pakette kalır.

Jüri bu referansa karşı canlı kalibrasyonu bağlam haritasıyla geçti. 400 çiftte dokuz koltuğun her biri stüdyonun satırını yüzde 86 ile 98 arasında seçti, haritadan önce dört koltuk 0.85 eşiğinin altındaydı. Raporlar Türkçeyi ölçülmüş olarak işaretler. Diğer diller paketlerini `build_language_pack.py` ile kurar. `key`, `en`, `<locale>`, `category` ve `speaker` sütunlarından oluşan bir stüdyo referans tablosu o dilin ölçülmüş seviyeye çıkmasının yolunu açar.

**Anahtarsız deneyin.** Her araç `--dry-run` ile çevrimdışı çalışır. Akışın tamamını görmek için bu komutu `skills/game-cultural-localization/` klasöründen çalıştırın.

```bash
python scripts/orchestrator_stub.py --dry-run --locale tr-TR --input strings.json --workdir out/
```

Gerçek bir oyunda önce bağlam haritasını çıkarın ve `--context-map loc_work/context/CONTEXT_MAP.md` ile verin, böylece her çevirmen ve jüri üyesi her satırın nerede göründüğünü bilir. API anahtarları yalnızca `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` ve `DEEPSEEK_API_KEY` ortam değişkenlerinden, model kimlikleri `scripts/providers.config.json` dosyasından okunur. `--live` aynı akışı gerçek API'lerle çalıştırır, `budget_report.py` de kayda geçen çağrılardan bütün proje için bir maliyet tahmini çıkarır. Ayrıntılar [methodology_and_qa.md](./skills/game-cultural-localization/references/methodology_and_qa.md) ve [CLI_REFERENCE.md](./skills/game-cultural-localization/scripts/CLI_REFERENCE.md) dosyalarında.

## Neler Var

1. **15 kültürelleştirme rehberi.** Beş ses arketipiyle (A1 ile A5 arası) etiketlenmiş Golden Voice Anchors satırları içerir.
2. **İki ajan promptu.** Pass 1 ve Pass 2 için bir kültürelleştirici, bir de yalnızca hedef dildeki kör dilimi okuyan anadil kulağı denetçisi.
3. **15 dilin hepsinde yerli jüri promptları.** Her dilin kendi diliyle yazılmış, yerel bir oyuncu ya da yazar kimliği taşıyan denetçi ve Pass 2 promptu var.
4. **Deterministik kapılar.** Linter, arayüz taşma denetçisi, font tofu tarayıcısı, kör dilim üreteci ve eleştiri doğrulayıcısı. Hepsi saf Python, hiçbir bağımlılık yok.
5. **Karma aileli LLM jürisi.** Claude, Gemini ve DeepSeek her satırı üç kademede kör olarak değerlendirir, anlaşmazlıkları anonim müzakereyle çözer ve geliştiriciye gerekçe, kanıt ve güven oranı içeren bir değişiklik raporu verir.
6. **Türkçe dil paketi.** Profesyonel bir oyun çevirisinden kuruldu, jürinin kalibrasyonuna hazır.

## Desteklenen Diller

| Dil | Rehber | Notlar |
|---|---|---|
| `en` | [en.md](./skills/game-cultural-localization/references/en.md) | Yalnızca kaynak metin cilası (yer tutuculu İngilizce, birleştirme temizliği) |
| `tr-TR` | [tr-TR.md](./skills/game-cultural-localization/references/tr-TR.md) | Yer tutucular için ek ve kesme işareti kuralları, kurulu dil paketi |
| `de-DE` | [de-DE.md](./skills/game-cultural-localization/references/de-DE.md) | Perfekt ve Präteritum ayrımı, du/Sie kilidi, ẞ kullanımı |
| `fr` | [fr.md](./skills/game-cultural-localization/references/fr.md) | fr-FR'yi kapsar, Québec terimleri ve boşluk kuralları için fr-CA notu var |
| `es-ES` | [es-ES.md](./skills/game-cultural-localization/references/es-ES.md) | İspanya İspanyolcası, tú/usted |
| `it-IT` | [it-IT.md](./skills/game-cultural-localization/references/it-IT.md) | Passato prossimo, tu/Lei |
| `pt-BR` | [pt-BR.md](./skills/game-cultural-localization/references/pt-BR.md) | Brezilya Portekizcesi, pt-PT'den ayrı, iki yönde sızıntı denetimi |
| `pt-PT` | [pt-PT.md](./skills/game-cultural-localization/references/pt-PT.md) | Avrupa Portekizcesi, tu/você, ayrı rehber |
| `pl-PL` | [pl-PL.md](./skills/game-cultural-localization/references/pl-PL.md) | Üç çoğul biçimi, cinsiyetten bağımsız geçmiş zaman |
| `lt-LT` | [lt-LT.md](./skills/game-cultural-localization/references/lt-LT.md) | Çoğul biçimleri, seslenme hâli, aksanlı harfler için font denetimi |
| `ru-RU` | [ru-RU.md](./skills/game-cultural-localization/references/ru-RU.md) | Üç çoğul biçimi, канцелярит yasak listesi, ты/вы |
| `ja-JP` | [ja-JP.md](./skills/game-cultural-localization/references/ja-JP.md) | 役割語, arayüz üslubu kilidi, sayma sözcükleri, 禁則処理 |
| `ko-KR` | [ko-KR.md](./skills/game-cultural-localization/references/ko-KR.md) | 화계 kilidi, yer tutucudan sonra gelen ilgeç tuzakları |
| `zh-CN` | [zh-CN.md](./skills/game-cultural-localization/references/zh-CN.md) | Basitleştirilmiş Çince, Anakara terimleri ve uyumluluk notları |
| `zh-Hant` | [zh-Hant.md](./skills/game-cultural-localization/references/zh-Hant.md) | Geleneksel Çince, varsayılan Tayvan, Hong Kong alt bölümü (`--variant hk`) |

## Farkı Ne

| Yetenek | Düz MT ya da LLM promptu | CAT aracı yapay zekâ eklentileri | Bu paket |
|---|---|---|---|
| Kör anadil kulağı denetimi (denetçi kaynağı hiç görmez) | hayır | hayır | evet, `make_blind_slice.py` ile zorunlu |
| Üç model ailesinden kalibre edilmiş jüriyle ölçülen doğallık | hayır | hayır | evet, `jury.py` ve `eval_critic.py` kalibrasyonu |
| Dile özel kültürelleştirme rehberi ve beş ses arketipi | hayır | kısmen (stil kılavuzları) | evet, tek şablonda 15 rehber |
| 0/1/2 çıkış kodlu deterministik kapılar | hayır | kısmen (QA denetimleri) | evet, linter, arayüz, font, eleştiri şeması |
| Motordan bağımsız işaretler (Unity, Unreal, Godot, ICU, printf) | kısmen | kısmen | evet, her stil için eşlik denetimi |
| API'den bağımsız (herhangi bir LLM, düz sistem promptları) | evet | hayır (sağlayıcıya bağlı) | evet |
| Sıfır bağımlılık | uygulanmaz | hayır | evet, yalnızca Python 3.9+ standart kütüphanesi |
| Her dil için cinsiyetten bağımsız oyuncu sesi | hayır | hayır | evet, rehberin 4. bölümü |
| Çoğul ve ICU kategorileri (few, many) | hayır | kısmen | evet, rehberin 5. bölümü |
| Bölgesel sızıntı tespiti (pt-PT içinde pt-BR, zh-Hant içinde zh-CN) | hayır | kısmen | evet, veriye dayalı kurallar |

## Nasıl Çalışır (Faz 0 ile 3 arası)

| Faz | Ne olur | Kapı |
|---|---|---|
| 0 Bağlam haritası ve ön kontrol | `context-cartographer` ve `context-scout` ajanları `CONTEXT_MAP.md` dosyasını yazar ve belirsiz kalanları kullanıcıya sorar. Ardından sağlama toplamları, birleştirme taraması, font glif taraması, `<LOCALE>_BIBLE.md`, transcreation ledger, sahte yerelleştirme | Her anahtar için satır notu, açık soruların cevaplanması, ek yerlerinin kaydı, eksik glif sıfır |
| 1 Temiz oda Pass 1 | `game-culturalizer` temiz kaynak gruplarını rehbere ve arketiplere göre ayarlanmış olarak çevirir | Her grupta `lqa_linter.py` çıkış kodu 0 |
| 2 Kör denetim ve Pass 2 | `make_blind_slice.py` kaynağı ayıklar, `native-ear-critic` her satıra 1 ile 5 arası puan verir, `validate_critique.py` şemayı denetler, `game-culturalizer` 5'in altında kalan her satırı yeniden yazar | Satırların %95'i 5 puanda, 2 ve altında satır yok |
| 3 Otomatik kapı | `lqa_linter.py --fail-on-error`, `ui_expansion_checker.py --fail-on-high`, `font_glyph_scanner.py`, geri yazma, sağlama toplamıyla kapsam denetimi | Hepsi 0 ile çıkar, yalnızca hedef dil dosyaları değişir |

Beş arketip A1 Usta, A2 Yarışçı, A3 Çaylak, A4 Mühendis ve A5 Antagonist. Arayüz metni bunların yerine o dilin kilitli arayüz üslubunu kullanır. `--dry-run` ya da `--live` ile orkestratör Faz 2'yi yukarıda anlatılan jüri akışı olarak çalıştırır. Her fazın girdi ve çıktılarını içeren tam çalışma kılavuzu [methodology_and_qa.md](./skills/game-cultural-localization/references/methodology_and_qa.md) dosyasında.

## Kurulum

Skill klasörü açık [Agent Skills](https://agentskills.io/specification) biçimine uyar, bu yüzden aynı `skills/game-cultural-localization/` klasörü birçok araçta yüklenir. Aşağıdaki yollar her sağlayıcının resmî belgelerinden alındı.

| Araç | Rehberler ve betikler (skill) | Ajanlar | Kurallar | İş akışı şablonu |
|---|---|---|---|---|
| Antigravity | evet, eklenti kurulumu | evet, `agents/*.md` olduğu gibi | evet, `rules/AGENTS.md` | evet, `/run-workflow` |
| Claude Code | evet, `~/.claude/skills/` ya da `.claude/skills/` | evet, `.claude/agents/` içine kopyalayıp `tools:` alanını Claude adlarına (`Read, Write, Bash`) çevirin | elle, `CLAUDE.md` içine yapıştırın | hayır, `orchestrator_stub.py` kullanın |
| Gemini CLI | evet, `~/.gemini/skills/` ya da `.gemini/skills/` (`.agents/skills/` takma adı) | elle, sistem promptu olarak | elle, `GEMINI.md` içine yapıştırın | hayır |
| Cursor | evet, `.agents/skills/` ya da `.cursor/skills/` (`.claude/skills/` klasörünü de okur) | elle, alt ajan promptu olarak | evet, `AGENTS.md` ya da `.cursor/rules/` | hayır |
| OpenAI Codex | evet, depodaki `.agents/skills/` ya da `~/.agents/skills/` | elle, sistem promptu olarak | evet, depo kökünde `AGENTS.md` | hayır |
| Herhangi bir LLM API'si | evet, dosyaları bağlam olarak ekleyin | evet, prompt gövdeleri | evet, sistem promptunun başına ekleyin | `orchestrator_stub.py` |

**Antigravity**

```bash
agy plugin validate --strict ./game-cultural-localization
agy plugin install ./game-cultural-localization
```

Ya da klasörü `~/.gemini/config/plugins/game-cultural-localization/` (genel) veya `<project>/.agents/plugins/game-cultural-localization/` (çalışma alanı) altına kopyalayın. Ardından `/game-cultural-localization` yazın, önerilen promptlardan birini seçin ya da ana ajan olarak `game-culturalizer` seçin (`agy --agent game-culturalizer`). Eklentiyi güncelledikten sonra yeni bir konuşma başlatın.

**Claude Code, Gemini CLI, Cursor, Codex**

```bash
# proje kapsamı, aracınızın okuduğu klasörü seçin (tabloya bakın)
cp -r game-cultural-localization/skills/game-cultural-localization .agents/skills/
cp -r game-cultural-localization/skills/game-cultural-localization .claude/skills/
cat game-cultural-localization/rules/AGENTS.md >> AGENTS.md
```

Skill'in `name` ve `description` alanları oturum başında, gövdesi ise gerektiğinde listedeki her araçta yüklenir. Betikler her yerde `python` ile aynı şekilde çalışır.

**Herhangi bir LLM API'si ya da CAT aracı**

1. Pass 1 ve Pass 2 için [agents/game-culturalizer.md](./agents/game-culturalizer.md) gövdesini, denetim için [agents/native-ear-critic.md](./agents/native-ear-critic.md) gövdesini sistem promptu olarak kullanın. Bağlam olarak [SKILL.md](./skills/game-cultural-localization/SKILL.md) ve bir dil rehberi ekleyin.
2. `in_<locale>_<batch>.json` dosyasını gönderin ve yanıtı `pass1_<locale>_<batch>.json` olarak kaydedin.
3. `make_blind_slice.py` betiğini çalıştırın, dilimi yeni bir konuşmada yalnızca denetçiye gönderin, yanıtı `critique_<locale>_<batch>.json` olarak kaydedin ve `validate_critique.py` betiğini çalıştırın.
4. Pass 2 için Pass 1 dosyasını ve doğrulanmış eleştiriyi gönderin, ardından Faz 3 kapısını çalıştırın.

`scripts/orchestrator_stub.py` aynı döngüyü çalıştırır. `--provider module:function` herhangi bir `complete(system, user) -> str` fonksiyonunu kabul eder, `--dry-run` çok aileli jüriyi çevrimdışı, `--live` ise gerçek API'lerle çalıştırır.

## Komut Özeti

`skills/game-cultural-localization/` klasöründen çalıştırın. Her parametre [CLI_REFERENCE.md](./skills/game-cultural-localization/scripts/CLI_REFERENCE.md) dosyasında anlatılıyor.

```bash
python scripts/font_glyph_scanner.py --input strings.en.json --dst-field en --font ./Fonts/UI.ttf --font ./Fonts/Fallback.ttc
python scripts/lqa_linter.py --input pass1_de-DE_01.json --locale de-DE --src-field en --dst-field dst --fail-on-error
python scripts/make_blind_slice.py pass1_de-DE_01.json --locale de-DE --out blind_de-DE_01.json --key-col key --target-col dst --context-cols category,speaker,archetype
python scripts/validate_critique.py critique_de-DE_01.json --slice blind_de-DE_01.json
python scripts/lqa_linter.py --input final_de-DE.json --locale de-DE --src-field en --dst-field dst --json lqa_de-DE.json --fail-on-error
python scripts/ui_expansion_checker.py --input final_de-DE.json --locale de-DE --src-field en --dst-field dst --json ui_de-DE.json --fail-on-high
```

## Teknik Özellikler

| Öğe | Değer |
|---|---|
| Diller | 15 (yukarıdaki tablo), takma adlar eşlenir (`de` için `de-DE`, `pt_BR` için `pt-BR`, `zh-TW` ve `zh-HK` için `zh-Hant`), bilinmeyen dil 2 ile çıkar |
| Girdi biçimleri | JSON listesi, JSON sözlüğü, CSV, TSV, Gettext PO (çok satırlı ve çoğul `msgstr`), Unity Localization StringTable `.asset` |
| Yer tutucu stilleri | `auto`, `unity` (`{0}`, `{name}`, Smart Strings), `unreal` (`{Name}`, `\|hpp`), `godot` (`%s`, `{name}`), `icu` (plural ve select), `printf`, `python` |
| Etiket stilleri | `tmp` (`<b> <color=> <sprite=> <style=> <link=>`), `html`, `bbcode` (`[b] [color=] [url=]`) |
| Çalışma ortamı | Python 3.9 ya da üstü, yalnızca standart kütüphane, UTF-8 girdi ve çıktı, BOM'a dayanıklı |
| Çıkış kodları | 0 temiz, 1 bulgu var (hatalar, `--fail-on-warn` ile uyarılar, `--fail-on-high` ile HIGH riskler), 2 kullanım ya da girdi hatası |
| Bağlam | Her projenin `CONTEXT_MAP.md` dosyası her satırın anlamını belirler. İsteğe bağlı isim listesi (`--glossary`, başlık `term_en,<locale>[,<locale>...],notes`) yalnızca özel isimlerin yazılışını denetler |
| Eleştiri dosyası | `critique_<locale>_<batch>.json`, 1 ile 5 arası doğallık puanı ve sorun türü, yalnızca 5'in altındaki puanlar listelenir |

Girdi satırı örneği (yalnızca `key` ve `en` zorunlu) ve eleştiri kaydı örneği.

```json
{"key": "dlg.mentor.intro_01", "en": "Take your time, kid. The {itemName} isn't going anywhere.", "category": "dialogue", "speaker": "Mentor", "archetype": "A1"}
```

```json
{"locale": "de-DE", "source_file": "blind_de-DE_01.json",
 "entries": [{"key": "dlg.mentor.intro_01", "score": 3, "issue_type": "translationese",
              "reason": "Calqued English word order.", "suggested": "Lass dir Zeit. Der {itemName} läuft dir nicht weg."}],
 "summary": {"total": 120, "flagged": 1, "critical": 0}}
```

Sorun türleri `translationese`, `register`, `tense`, `regional_leak`, `gender_leak`, `ui_verb`, `placeholder_grammar`, `terminology` ve `other` (isteğe bağlı `needs_source_check` ile).

### Dosya düzeni

```
plugin.json                 Antigravity manifesti (sürüm numarası burada)
README.md, README_TR.md     bu sayfanın İngilizcesi ve Türkçesi
AGENTS.md, CLAUDE.md        yapay zekâ ajanlarının ilk okuduğu rehber (nereden başlanır, hiç esnemeyen kurallar)
rules/AGENTS.md             her zaman açık kurallar, AGENTS.md ya da CLAUDE.md içeriği olarak da kullanılır
agents/                     game-culturalizer.md, native-ear-critic.md
skills/game-cultural-localization/
  SKILL.md                  Agent Skills giriş noktası, arketipler, 8 yasa, kısa talimatlar
  references/               15 dil rehberi, methodology_and_qa.md, transcreation_ledger_guide.md
  scripts/                  komut satırı araçları, rules/<locale>.json, CLI_REFERENCE.md, iş akışı şablonu, orkestratör, providers/ ve jüri araçları
  prompts/                  15 dil için yerli denetçi ve Pass 2 promptları, literal.md
  langpack/                 sources.manifest.json ve kurulmuş dil paketleri (local/ makinede kalır)
tests/                      python -m unittest discover tests
.github/                    CI iş akışı, issue ve PR şablonları
```

## Katkı

Pull request'lere açığız. `python -m unittest discover tests` komutunu, CLI kuruluysa `agy plugin validate --strict .` komutunu da çalıştırın. Dil rehberlerini 12 bölümlük şablonda tutun, örnekleri projeden bağımsız yazın ve [CHANGELOG.md](./CHANGELOG.md) dosyasına bir satır ekleyin. README.md ve README_TR.md birlikte güncellenir, iki dosyada bölümlerin aynı olduğunu bir test denetler. Şablonlar [.github](./.github/) klasöründe.

## Lisans

[MIT](./LICENSE). Geliştiren ve bakımını yapan Rysesoft.
