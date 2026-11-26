# Turkish (`tr-TR`) Game Localization & Culturalization Playbook

Target feel. **Yaşayan, samimi gündelik Türkçe ve gerçek Türk oyuncu dili**, ZERO *çeviri kokusu*, ZERO dilekçe Türkçesi.

## 1. Anti-Translationese Ban List

| Robotic ✗ | Natural ✓ | Why |
|---|---|---|
| `Sen ... yapabilirsin` / `Senin deponda` | `Yapabilirsin` / `Deponda` | Türkçe pro-drop. Zamir tekrarı İngilizce kokar. |
| `... tarafından üretildi` / `saldırıya uğradı` | `... üretti` / `... saldırdı` | İngilizce *by* pasifi. Etken kur. |
| `Burada zaten bir eşya bulunmaktadır!` | `Burası zaten dolu!` / `Burada zaten bir şey var!` | `bulunmaktadır` = resmî yazı. Toast konuşur. |
| `Bu eşya buraya yerleştirilemez.` | `Bu buraya uymaz.` / `Bunu buraya koyamazsın.` | Edilgen + `-ebil` olumsuz = kullanma kılavuzu. |
| `Bu alete zaten sahipsin!` | `Bu alet sende zaten var!` | *have/own* kalıbı. İyelik `-de var` ile kurulur. |
| `Kondisyonun çok düşük!` | `Nefesin tükendi!` / `Enerjin yetmiyor!` (toast) · stat adı. `Dayanıklılık` | `Kondisyon` stat adı olarak da toast olarak da yapay. |
| `Uyku süresi çok kısa.` | `Bu kadar kısa uyunmaz.` | İsim yığını yerine fiil. |
| `Mevcut siparişi iptal etmeden yükseltme yapamazsın.` | `Önce devam eden siparişi iptal et, sonra yükselt.` | `yükseltme yapmak` yardımcı fiil şişmesi. `yükselt`. |
| `X'e sahipsin` / `gerçekleştirmek` / `sağlamak` | `X'in var` / `sende X var` · `yapmak` · `halletmek` | `sahip olmak` resmî. `var olmak` ise *to exist* demektir, karşılık DEĞİLDİR. |
| `İşlem başarıyla tamamlandı.` | `Tamam, oldu!` / `Kaydedildi.` | Sistem jargonu. |
| `Lütfen bekleyiniz.` / `Giriniz` | `Lütfen bekle.` / `Gir` (`sen` UI) · `Bekleyin` (`siz` UI) | `-iniz` bankamatik dili. Oyun UI'si tek kipte kalır. |
| `su üstünde kalmak` (*stay afloat* kalkı) | `ayakta kalmak` / `batmamak` / `idare etmek` | Türkçede deyim değil. |
| `Bu tamamen güneş yıkamasıdır.` / `kozmik saçmalık` | `Kuyruklu yalan!` / `Külliyen yalan!` / `Boş laf.` | Şaka ve ünlemler kalk yapılmaz, yeniden yazılır. |

## 2. Register, Address & Character Voice

* **Pro-drop.** Fiil çekimi kişiyi taşır. `sen / ben / o` yalnızca vurgu ya da karşıtlık için yazılır (*"Ben elimden geleni yaparım ama gerisi sende."*).
* **`sen` karakterleri (A1 Mentor, A2 Rival, A3 Rookie, A5 Outlaw).** Canlı parçacıklar ve deyimler. `bak`, `işte`, `zaten`, `hani`, `valla` (az ve yerinde), `ayağa kaldırmak`, `hurdaya çıkmak`, `elinden iş gelmek`, `kafaya takmak`, `canına okumak`, `çarkı döndürmek`.
* **`siz` karakterleri (A4 Scientist resmî bağlamda, yetkililer, koleksiyoncular, yabancılar).** Modern ve temiz `siz`. ASLA Osmanlı/dilekçe üslubu (*"arz ederim"*, *"tarafınıza iletilmiştir"*, *"müteşekkir kalırım"*). Kibar karakter de *"Açık konuşayım"*, *"İşin doğrusu"*, *"Bize çok yardımcı oldunuz"* der.
* **Asla karıştırma.** Aynı karakter aynı muhataba hep `sen` ya da hep `siz` der. UI/tutorial projede tek kipte kilitlenir (varsayılan `sen`, Steam/konsol Türkçesi standardı). Kipi `TR-TR_BIBLE.md` dosyasına yaz.
* **Hitap sözcükleri (oyuncuya).** `evlat`, `usta`, `çaylak`, `patron`, `dostum`, `kaptan` cinsiyetsizdir. `oğlum`, `kızım`, `abi`, `abla`, `delikanlı`, `hanımefendi`, `beyefendi`, `Bay/Bayan` oyuncu için YASAK (bkz. §4).

## 3. Spoken vs. Literary Tense

Türkçede edebî/konuşma ayrımı Batı dillerindeki gibi değildir. Asıl tuzak **görülen geçmiş (-di) / duyulan geçmiş (-miş)** seçimidir.

* **-di.** Konuşanın gördüğü, yaptığı, kesin bildiği olaylar. *"Sızıntıyı macunla kapattım."*, *"Jeneratörü değiştirdik."* UI sonuç mesajları da -di. `Kaydedildi`, `Satın alındı`, `Üretim tamamlandı`.
* **-miş.** Duyulan, çıkarım yapılan, dedikodu ve haber. *"Başkan Yardımcısı sizinle temasa geçmiş."*, *"Jeneratör gece bozulmuş."* Mektup/dedikodu/rapor sahnelerinde -miş olmadan metin yapay olur.
* **-miş'in ikinci işlevi.** Şaşırma ve sonradan fark etme (*"Meğer macun tutmamış!"*).
* **Anlatıcı/codex metinleri.** -di ya da -miş tutarlı seçilir. Aynı paragrafta karıştırma. Lore'da geniş zaman (-r) de doğaldır (*"Reaktörler yüz yıl dayanır."*).
* Batı dillerindeki "spoken vs. literary tense" kuralı Türkçe için uygulanmaz. -di/-miş yukarıdaki gibi kullanılır.

## 4. Player Gender Neutrality

Türkçede fiil, sıfat ve zamir cinsiyet taşımaz. **Tek sızıntı noktası hitap ve rol adlarıdır.**

| Sızdıran ✗ | Nötr ✓ |
|---|---|
| `Aferin oğlum!` / `Bravo kızım!` | `Aferin evlat!` / `Helal olsun!` |
| `Abi, şunu bir toparla.` | `Usta, şunu bir toparla.` / `Şunu bir toparla.` |
| `Gerçek bir adam gibi çalıştın.` | `Tam bir usta gibi çalıştın.` |
| `Sayın Bay {playerName}` | `Sayın {playerName}` |
| `Hoş geldin delikanlı.` | `Hoş geldin çaylak.` |

* Oyuncunun cinsiyeti bilinmiyorsa **hiçbir** hitapta `oğlum/kızım/abi/abla/hanım/bey` kullanma. NPC'nin kendi cinsiyeti biliniyorsa NPC kendinden istediği gibi söz eder (*"Ben bu işi yirmi yıldır yapıyorum."*).
* `{playerName}` + hitap. `{playerName} usta` güvenli. `{playerName} Bey/Hanım` yasak.

## 5. Plurals, Numbers & ICU

Türkçede **sayıdan sonra isim tekil kalır**, ASLA `3 Reaktörler`. CLDR kategorileri `one` (1) ve `other` (gerisi). İkisi de tekil isim alır, fark yalnız bazı yapılarda görülür.

| Sayı | Türkçe | ICU |
|---|---|---|
| 0 | `0 reaktör` / `Hiç reaktör yok` | `=0` / `other` |
| 1 | `1 reaktör` | `one` |
| 2 | `2 reaktör` | `other` |
| 5 / 21 / 22 / 25 | `5 reaktör` / `21 reaktör` / `22 reaktör` / `25 reaktör` | `other` |

```text
{count, plural, =0 {Depoda reaktör yok.} one {Depoda {count} reaktör var.} other {Depoda {count} reaktör var.}}
```

* Çoğul eki yalnızca sayı YOKKEN gelir. `Reaktörler` (sekme adı), `Hepsini al`.
* "Birkaç", "çoğu", "tüm" gibi nicelik sözcüklerinden sonra da tekil. `birkaç parça`, `tüm siparişler` (istisna `tüm` + çoğul doğaldır).
* Sıra sayıları. `1.`, `2.` (nokta) ya da `1'inci`. UI'da `1. Seviye` yerine `Seviye 1` tercih edilir.

## 6. Placeholder & Rich-Text Grammar Traps

* **Ünlü uyumu ve kesme işareti.** `{0}'a / {0}'e / {0}'ı / {0}'i / {0}'u / {0}'ü`, ekin biçimi `{0}`'ın son hecesine bağlıdır, bu yüzden **`{0}`'a doğrudan ek bağlanmaz.** Çözüm. Tür adı ekle, eki ona ver. `"{0} istasyonundan Depoya taşınıyor"`, `"{0} eşyasını kuşan"`, `"Seviye {1} için %{0}"`.
* **Yabancı özel adlara ek, OKUNUŞA göre.** `Crowe` /kro/ → `Crowe'yu, Crowe'ya`. `Mike` /mayk/ → `Mike'ı`. `Bordeaux` → `Bordeaux'yu`. `Shakespeare` → `Shakespeare'i`. Yazılışa göre ek (`Crowe'u`) YANLIŞTIR. Projede özel telaffuz kararı varsa (seslendirme "Krov" diyorsa) ledger'a yaz.
* **Cins isimlere kesme işareti YOK.** `Depoya`, `terminalden`, `lazerini`, `Depo'ya` yanlış. Kesme yalnız özel ad, kısaltma ve rakamdan sonra. `TV'yi`, `{playerName}'a` (yine ünlü uyumu sorunu, mümkünse yeniden kur).
* **Etiket içinde ek.** Ek etiketin İÇİNDE kalır. `<b>Depoya</b>`, `<u>Sökme Lazerini</u>`, `[b]Terminalden[/b]`. `<b>Depo</b>ya` yasak (kelime sınırı bölünür, bazı motorlar eki ayrı sarar).
* **Concatenation yasağı.** `"Yükseltme " + {name}` gibi parçalı dizgiler Türkçede söz dizimi ters çevirir (`{name} Yükseltmesi`). Bölünmüş kaynak dizgiyi lead'e bildir. Zorunluysa baştaki/sondaki boşlukları aynen koru (`--strict-whitespace`).
* **Motor karşılıkları.** Unity `{0}` ve `<b>`. Unreal `{Name}`. Godot `%s` ve `[b][/b]`. ICU `{count, plural, ...}`. Printf `%1$s`. Kural hepsinde aynı. Ek, placeholder'a değil, yanındaki Türkçe tür adına.
* **Yüzde.** `%{0}`, işaret önde ve bitişik (`%40`). `{0}%` yanlış.

## 7. Core UI Glossary

Türkçe PC/konsol/Steam standardı. **Emir kipi (2. tekil)** ya da **kısa isim**. Mastar (`Kaydetmek`) menüde YASAK. Yalnızca açıklama metninde ("Kaydetmek için...") geçer.

| EN | tr-TR | Biçim / Not |
|---|---|---|
| Save / Load | `Kaydet` / `Yükle` | emir |
| Quit | `Çık` (buton) · `Çıkış` (menü başlığı) | |
| Settings / Options | `Ayarlar` / `Seçenekler` | isim. Proje tek terim seçer |
| OK / Confirm | `Tamam` / `Onayla` | |
| Cancel / Back | `İptal` / `Geri` | `İptal Et` yalnızca cümle içinde |
| Continue / Resume | `Devam Et` / `Devam Et` (`Sürdür` nadir) | |
| New Game | `Yeni Oyun` | |
| Apply | `Uygula` | |
| Delete | `Sil` | |
| Yes / No | `Evet` / `Hayır` | |
| Pause | `Duraklat` | |
| Retry / Skip | `Tekrar Dene` / `Atla` | |
| Inventory / Equip | `Envanter` / `Kuşan` | `Donan` yapay |
| Craft / Upgrade | `Üret` / `Yükselt` | sekme adı. `Üretim` |
| Level / Health / Stamina / Damage | `Seviye` / `Can` / `Dayanıklılık` / `Hasar` | `Sağlık` yalnız sim/strateji |
| Buy / Sell | `Satın Al` / `Sat` | |
| Take All | `Hepsini Al` | |

* Buton büyük/küçük harf. Her kelimenin ilk harfi büyük (`Devam Et`) ya da motor ALL CAPS uygularsa `DEVAM ET`. Cümle metninde cümle düzeni. Tipik sınır. Buton 12, sekme 10 karakter.
* Yabancı sözcük ölçüsü. `Grup` > `Fraksiyon`. `Beceri` > `Skill`. `Görev` > `Quest`. `Ganimet` > `Loot`. `Envanter`, `Seviye` yerleşmiştir.

## 8. Typography, Numbers & Formatting

* **İ/ı (KRİTİK).** `i` → `İ` (`İPTAL`, `İNŞA ET`, `İYİLEŞTİR`), `ı` → `I` (`ISINMA`, `SIĞINAK`). `IPTAL` ve `INŞA` hatadır. ALL CAPS'i motor uyguluyorsa motorun `tr-TR` kültür ayarı doğrulanır.
* **Tırnak.** `“ ”` (çift), iç tırnak `‘ ’`. `« »` ve `„ “` Türkçe değildir.
* **Sayılar.** Binlik ayırıcı nokta, ondalık virgül. `1.234,56`. Yüzde önde. `%50`.
* **Para.** `1.250 TL` ya da `1.250 ₺` (sayıdan sonra, boşluklu). `₺1.250` İngilizce dizilişidir. Oyun içi kurgusal para. `1.250 Kredi`.
* **Tarih/saat.** `26.11.2026`, `26 Kasım 2026`. Saat TDK'ye göre `14.30`, oyun UI'sinde `14:30` yaygın, projede tek biçim seç ve ledger'a yaz.
* **Büyük/küçük harf.** İngilizce Title Case yok. Cümle içinde `Yeni oyun` değil, buton olarak `Yeni Oyun`. Özel ad dışında büyük harf yok (`Depo` yalnızca UI öğesi adıysa).
* **Kesme/tire.** Özel ada ek `'`. Ekleri cins isme kesmesiz. `-` ile birleşik sayı (`3-5 dakika`). Üç nokta tek karakter `…`.
* **Satır kırma.** `{playerName}` ve ek arasına, sayı ve birim arasına (`3 dk`) `U+00A0`. Uzun bileşik kelimeler (`Dayanıklılık`) kırılamaz. Buton genişliği buna göre planlanır.

## 9. Text Expansion & UI Fit

* **Tipik genişleme.** İngilizceye göre +10 ile 25 % (eklemeli yapı kısa sözcüğü uzatır `ON` → `AÇIK`, `APPLY` → `UYGULA`, `SETTINGS` → `AYARLAR`, kısa dizgiler en çok büyür).
* **Kısaltma stratejileri.** Yardımcı fiili at (`İptal Et` → `İptal`), isimleştir (`Devam Ediliyor` → `Devam`), sayı + kısaltma (`dk`, `sn`, `sv`), `Dayanıklılık` → `Dayan.` yalnızca badge'de.
* `ui_expansion_checker.py --locale tr-TR` locale katsayısıyla ölçer. `max_chars` meta verisi olmayan butonlar için lead'e bildir.

## 10. Ratings, Legal & Sensitive Content

* **Derecelendirme.** Türkiye'de zorunlu ulusal kurul yok. Konsol ve PC mağazaları **PEGI** kullanır. Mobil. IARC. Yaş eşiğini kaynak `[rating]` etiketine göre eşle.
* **Küfür.** PEGI 12'ye kadar hafif (`lanet olsun`, `kahretsin`). PEGI 16'da orta (`salak`, `pislik`). Ağır argo yalnız PEGI 18 ve projede açıkça onaylıysa. Kaynak "strong" ise Türkçe karşılığı birebir değil, aynı seviyede.
* **Hassas içerik.** Atatürk'e, Türk bayrağına ve devlet kurumlarına hakaret (5816 sayılı Kanun, TCK 300/301) yayın riski. Dinî metin ve sembollerin alay konusu edilmesi. Kürt/Ermeni meselesi ve harita/sınır tasvirleri. Kumar benzeri mekanikler (loot box) için uyarı metni. Bunları ledger'a `[sensitive]` etiketiyle yaz, kendi başına değiştirme.
* **Alkol/tütün.** Reklam yasağı oyun içi kurgu için geçerli değil. Ancak marka adı kullanma.

## 11. Golden Voice Anchors (A1 ile A5)

Her çift AYNI anlamı korur. Yalnız üslup değişir. Proje adı yok. Jenerik roller.

1. **A1 Mentor / Usta** (`sen`, sıcak, kıdemli)
   * **✗ Robot.** "Mevcut malzemeleri geri dönüştürerek atölye operasyonlarını yeniden tesis et; ardından sana sözleşmeler aktaracağım."
   * **✓ Doğal.** "Eldeki hurdadan ne çıkarabiliyorsan onunla başla, şu dükkânı yeniden ayağa kaldır. Çarkı bir döndür, kendi işlerimden birkaçını sana paslarım."
2. **A2 Hotshot Rival / Yarışçı** (`sen`, küstah, hızlı)
   * **✗ Robot.** "Eleştirmenler yeteneklerimin gerilediğini ifade ediyor, bu tamamen yanlıştır. Aracı hızla tamir et."
   * **✓ Doğal.** "Millet formdan düştüğümü söyleyip duruyor. Kuyruklu yalan! Aracımı bir an önce toparla, o podyum benim."
3. **A3 Rookie / Çaylak** (`sen`, heyecanlı, kısa cümle)
   * **✗ Robot.** "Sızıntıyı endüstriyel macun kullanarak kapatmaya teşebbüs ettim, ancak kalkışta derhal başarısız oldu."
   * **✓ Doğal.** "Sızıntıyı sanayi macunuyla kapatmayı denedim ama araç yerden kesilir kesilmez macun tüttü, kavladı gitti."
4. **A4 Scientist / Mühendis** (`sen` ekip içi, resmî bağlamda `siz`)
   * **✗ Robot.** "Jeneratörün çıkış gücü, soğutma sisteminin yetersizliği nedeniyle nominal değerin yüzde kırkına düşmüş bulunmaktadır."
   * **✓ Doğal.** "Jeneratör gücünün %40'ına düşmüş; soğutma yetmiyor. Önce fanı değiştir, sonra tekrar ölçeriz."
5. **A5 Outlaw / Antagonist** (`sen`, soğuk, tehditkâr)
   * **✗ Robot.** "Bu bölgede faaliyet göstermeye devam etmen durumunda olumsuz sonuçlarla karşılaşacaksın."
   * **✓ Doğal.** "Bu bölgede işe devam edersen sonu iyi bitmez. Son uyarım."

## 12. Linter Coverage Note

`lqa_linter.py --locale tr-TR` şu kalıpları yakalar. `tarafından` (WARN), `bulunmaktadır` (ERR), `sahipsin(iz)` (WARN), bozuk büyük `I` (`IPTAL`, `INŞA`, `IYILEŞTIR`, `IÇERIK`, `ILETIŞIM`) (ERR).

### Suggested linter patterns

| Severity | Pattern | Message |
|---|---|---|
| ERR | `\b\d+\s+[^\W\d_]+(?:ler\|lar)\b` (ör. `3 Reaktörler`, Python `re` `\p{L}` desteklemez) | sayıdan sonra çoğul eki |
| ERR | `\{\w+\}'[^\W\d_]+` | `{0}'a`, placeholder'a kesme ile doğrudan ek bağlanmış |
| ERR | `\b(?:Depo\|Terminal\|Envanter\|Seviye)'(?:y\|n\|d\|t)?[aeıioöuü]` | cins isme kesme işareti |
| WARN | `\b(?:sahip olmak\|sahip olmanız\|gerçekleştir\w*)\b` | resmî yardımcı fiil |
| WARN | `\b(?:arz ederim\|tarafınıza\|müteşekkir)\b` | dilekçe üslubu |
| WARN | `\b(?:yapamazsınız\|bekleyiniz\|giriniz\|seçiniz)\b` | `-iniz` bankamatik kipi (projede `siz` UI yoksa) |
| WARN | `\b(?:oğlum\|kızım\|abi\|abla\|delikanlı\|beyefendi\|hanımefendi)\b` (`[player]` etiketli dizgilerde) | oyuncuya cinsiyetli hitap |
| WARN | `\d+%` | yüzde işareti sonda. `%\d+` olmalı |
| WARN | `\b(?:su üstünde kal\w*\|kozmik saçmalık)\b` | bilinen kalk |
| WARN | `\b(?:Kaydetmek\|Yüklemek\|Çıkmak\|Uygulamak)\b` (yalnız buton anahtarlarında) | menüde mastar |
