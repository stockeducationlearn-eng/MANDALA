# BİLGİ ARAŞTIRMA — Tam Windows Paketi

Sürüm 3.0 — değişiklik listesi için `DEGISIKLIKLER.md` dosyasına bakın.

## Özellikler
- **Adım adım akış:** Arayüz üç adıma bölünmüştür; üstte adım göstergesi,
  altta `Geri` / `İleri` düğmeleri. Aynı anda tek adım görünür.
  1. Kaynak ekle ve seç, 2. Ara, 3. Sonuç ve rapor.
- **Menü çubuğu:** Dosya, Ara, Kaynaklar, Rapor, Görünüm ve Yardım menüleriyle
  tüm işlemler tek yerde; klavye kısayolları eşlenmiştir.
- **Oluşturulan raporlar:** `Raporlar` sekmesinde üretilen tüm raporlar (PDF,
  Word, TXT, CSV, konu notu, yedek) tür, boyut ve tarih bilgisiyle listelenir;
  tek tıkla açılır, silinebilir, klasör açılabilir.
- **Kaynak seçimi:** Kaynak kütüphanesindeki `Aramada` sütunundan istediğiniz
  kaynakları işaretleyip yalnızca onlarda arama yapabilirsiniz. Seçim kalıcıdır.
- PDF, DOCX, TXT, PNG, JPG/JPEG, BMP, TIFF kaynaklarını arşive alır.
- Kaynakları `documents/` klasörüne kopyalar; metinlerini SQLite'a kaydeder.
- PDF sayfa numarası, Word paragraf/tablo konumu, TXT satır numarası ve görsel adıyla sonuç gösterir.
- Türkçe karakter duyarlı/duyarsız arama seçeneği, tam ifade araması ve tüm kelimeler/eşleşen kelimeler modu. Duyarsız modda ç/ğ/ı/ö/ş/ü ve i/İ/I/ı eşitlenir; duyarlı modda Türkçe harfler aynen aranır.
- Genişletilmiş arama girdisi: elle yazmanın yanında bir dökümandan (PDF/DOCX/TXT) paragraf seçme, resimden OCR ile metin çıkarma, ekran görüntüsü alma (tam ekran veya seçilen bölge) ve web adresinden sayfa metni alma.
- Web sayfası ve ekrandan/resimden gelen metin istenirse doğrudan kaynak olarak arşive eklenebilir; arama sonucunda `Kaynak dosyayı aç` web adresini tarayıcıda açar.
- Kaynak sonuçlarına not ekleme, önceki aramaları tekrar açma.
- Kaynak dosyayı açma; bulunan tüm sonuçları tek raporda PDF, Word (DOCX), TXT veya CSV olarak dışa aktarma. PDF ve Word raporları varsa ekrandaki yapay zekâ konu notunu ve kaynak sonuçlarını birlikte içerir.
- Dört araştırma modu: Otomatik, Çıkmış soru, Paragraf/metin ve Kavram.
- Bir kavramın kaynaklarda geçtiği farklı yerleri bulup kaynak parçalarını birleştirerek konu notu oluşturma.
- Ollama'nın yanıtını ekranda düzenleme; notu SQLite veritabanına ve TXT dosyasına kalıcı kaydetme.
- İsteğe bağlı yerel Ollama modeliyle kaynak parçalarına dayalı açıklama.
- İsteğe bağlı Tesseract OCR: görseller ve taranmış PDF sayfaları.
- Veritabanı + kaynak arşivi için yedek oluşturma.
- Windows, Linux ve macOS'ta kaynak dosya açma desteği.

## Windows kurulumu
1. ZIP'i ör. `C:\BilgiArastirma` konumuna çıkar.
2. Python 3.10+ kurulu olsun. Kurulum sırasında `Add Python to PATH` seçili olsun.
3. Klasör içinde PowerShell açın ve çalıştırın:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

İlk çalıştırmada `.venv` yoksa `Kurulum.bat` dosyasını çalıştırabilirsiniz. İnternet bağlantısı yalnızca Python paketlerini kurmak için gerekir.

## Arama girdisini hazırlama
Arama kutusuna elle yazabilirsiniz (çok satırlı; `Ctrl+Enter` ile arar). Yanındaki `Girdi kaynağı…` düğmesi şu seçenekleri sunar:

| Sekme | Ne yapar |
|---|---|
| Dökümandan paragraf | PDF, DOCX veya TXT açar; bölümleri listeler; seçtiğiniz paragrafı arama kutusuna aktarır veya arşive ekler |
| Resim (OCR) | PNG/JPG/BMP/TIFF seçer; Tesseract ile metni çıkarır |
| Ekran görüntüsü | Tüm ekranı ya da fareyle seçtiğiniz bölgeyi yakalayıp OCR ile metne çevirir |
| Web adresi | `http://`/`https://` adresindeki sayfa metnini indirir; isterseniz kaynak olarak arşive ekler |

OCR ve indirme işlemleri arka planda çalışır; pencere donmaz. Web'den veya ekrandan gelen metni arşive eklerseniz, arama sonuçlarında `Kaynak dosyayı aç` ilgili adresi tarayıcıda açar.

## OCR kurulumu
Tesseract OCR'ı ayrıca Windows'a kurun. Yaygın yol:
`C:\Program Files\Tesseract-OCR\tesseract.exe`
Ayarlar penceresinde yolu belirtin. Türkçe OCR için `tur` dil verisi, İngilizce için `eng` dil verisi bulunmalıdır. Ayarlarda `tur+eng` kullanabilirsiniz. Tesseract kurulmamışsa metin tabanlı PDF/Word/TXT araması yine çalışır; taranmış sayfalardaki metinler çıkarılamayabilir.

## Ücretsiz yerel yapay zekâ (isteğe bağlı)
1. Ollama'yı kurun. Windows'ta masaüstü uygulaması arka planda servis olarak çalışır; ayrıca bir şey başlatmanız gerekmez.
2. PowerShell'de gerekli modelleri indirin (her biri bir kez indirilir, sonra çevrimdışı çalışır):
   - `ollama pull qwen2.5:3b` — konu notu ve model puanlaması için.
   - `ollama pull nomic-embed-text` — hızlı akıllı arama (gömme) için; yaklaşık 275 MB.
3. `ollama list` komutuyla iki modelin de listede göründüğünü doğrulayın.
4. Ollama uygulaması çalışır durumdayken Bilgi Araştırma içinden `Kaynaklardan konu notu oluştur` seçeneğini kullanın.
5. `Araştırma türü` alanında `Çıkmış soru`, `Paragraf / metin` veya `Kavram` seçin. Örneğin tek başına `tazminat` yazıp `Kavram` modunu seçebilirsiniz.
6. Oluşan notu ekranda düzenleyip `Konu notunu arşivle` düğmesiyle veritabanına ve `exports/` klasörüne kaydedin.
7. Ayarlar içinden model adlarını (`Ollama model adı`, `Gömme modeli`) değiştirebilirsiniz.

**Gömme modelini indirdiğinizi nasıl anlarsınız:** `Hızlı akıllı arama (gömme)` işaretliyken model yüklü değilse uygulama "İndirmek için: ollama pull nomic-embed-text" mesajını gösterir. Gömme modeli indirmek istemezseniz bu onay kutusunu kaldırın; akıllı arama, zaten kurulu olan `qwen2.5:3b` ile model puanlaması modunda çalışır (daha yavaş, gömme modeli gerekmez).

Model yerel bilgisayarda çalışır. Hız ve cevap kalitesi donanıma/model boyutuna bağlıdır. Temel arama için Ollama gerekmez. Uygulama yalnızca arama sonuçlarını modele gönderir; tüm 500 sayfalık kaynağı tek seferde göndermez. Model yanıtları yine de kaynak metniyle karşılaştırılmalıdır.

## Dosyalar
- `data/pdf_arastirma.db`: veritabanı (kaynaklar, arama geçmişi ve arşivlenmiş konu notları)
- `data/settings.json`: uygulama ayarları
- `documents/`: kaynak dosyalar
- `exports/`: oluşturulan raporlar, konu notları ve yedekler
- `logs/`: hata kayıtları

Bu klasörü yedeklemek için uygulamadaki `Yedek oluştur` düğmesini kullanın. Veritabanı ile belge arşivi birlikte ZIP'e alınır.

## Adım adım kullanım
Uygulama üç adımdan oluşur. Üstteki adım göstergesinden doğrudan geçebilir,
alttaki `Geri` / `İleri` düğmelerini kullanabilir ya da `Ctrl+1/2/3`
kısayollarına basabilirsiniz.

| Adım | İçerik |
|---|---|
| 1 · Kaynak ekle ve seç | Kaynak ekleme düğmeleri, tam genişlikte kaynak listesi (`Aramada` sütunu), `Tümü`/`Hiçbiri`, seçim özeti |
| 2 · Ara | **Sorgu ve sonuçlar** sekmesi (sorgu, arama, ayarlar, sonuç tablosu) ve **Son aramalar** sekmesi |
| 3 · Sonuç ve rapor | **Kaynak metni ve not** sekmesi (konu notu, rapor üretme) ve **Raporlar** sekmesi |

Adım düğmelerinde sayı görünür: kaç kaynak eklendiği ve kaç sonuç bulunduğu.
2. adımda bir sonuca çift tıklarsanız 3. adım açılır ve kaynak metni gösterilir.

## Menüler
Uygulamanın üstünde bir menü çubuğu bulunur.

| Menü | İşlemler |
|---|---|
| Dosya | Kaynak ekle, girdi kaynağından al, yedek oluştur, çıkış |
| Ara | Ara, akıllı ara, sorguyu temizle, son aramalar |
| Kaynaklar | Tüm kaynakları aramaya dâhil et, hiçbirini kullanma, kaynak sil, kaynak dosyayı aç |
| Rapor | Raporlar sekmesini aç, PDF/Word/TXT/CSV raporu üret, konu notunu arşivle |
| Görünüm | Adımlar arasında geçiş (1/2/3), ayarlar |
| Yardım | Hakkında (sürüm bilgisi) |

Kısayollar: `Ctrl+O` kaynak ekle, `Ctrl+G` girdi kaynağı, `Ctrl+Enter` ara,
`Ctrl+Shift+Enter` akıllı ara, `Ctrl+1/2/3` adımlar, `Ctrl+R` raporlar, `Ctrl+Q` çıkış.

## Kaynak seçimi (birden fazla kaynakta arama)
1. adımdaki kaynak listesinde `Aramada` sütunu bulunur. Bir kaynağın önündeki
`✓` işaretine tıklayarak onu aramaya dâhil edebilir ya da çıkarabilirsiniz.
`Tümü` ve `Hiçbiri` düğmeleri toplu seçim yapar. Yalnızca işaretli kaynaklarda
arama yapılır; seçim ayarlara kaydedilir. Hiçbir kaynak seçili değilken arama
başlatılırsa uyarı verilir. Akıllı arama da aynı seçime uyar.

## Oluşturulan raporlar
Rapor ürettiğinizde (PDF, Word, TXT, CSV, konu notu, yedek) dosya `exports/`
klasörüne yazılır ve 3. adımdaki `Raporlar` sekmesindeki liste otomatik güncellenir.

| Düğme | Ne yapar |
|---|---|
| Aç | Seçili raporu varsayılan uygulamada açar (çift tıklama da açar) |
| Sil | Seçili raporu siler |
| Klasörü aç | `exports` klasörünü dosya yöneticisinde açar |
| Yenile | Listeyi yeniden tarar |

Liste en yeni rapor en üstte olacak şekilde sıralanır; her satırda tür, boyut,
oluşturulma zamanı ve dosya adı görünür.

## Arama davranışı
Arama, SQLite FTS5 tam metin indeksi (Türkçe katlanmış metin üzerinde) ve kelime örtüşmesine dayanır; gelişmiş vektör tabanlı anlamsal arama içermez. FTS5 bulunmayan ortamlarda otomatik olarak Python taramasına düşer. Türkçe ekler için önek eşleşmesi kullanılır (`tazminat` -> `tazminatı`). Soru metnini seçenekleriyle birlikte veya tek kavram olarak aratabilirsiniz.

### Eşleşme oranı
`Eşleşme` alanı, sonuçların ne kadar sıkı süzüleceğini belirler:

- `Herhangi biri`: sorgudaki terimlerden en az biri geçen bölümler (varsayılan).
- `Çoğu (%60)`: terimlerin en az %60'ı kaynakta geçen belgeler. Soru metni için önerilir.
- `Çok (%80)` / `Tümü (%100)`: daha katı süzme. `Tümü`, terimlerin tamamını arar ve uzun soru metinlerinde sık sık boş sonuç verir.

Sınav sorusu veya uzun paragraf gibi girdilerde `Tümü (%100)` yerine `Çoğu (%60)` kullanın; seçeneklerdeki çeldirici kelimeler ve farklı çekimler yüzünden tüm terimlerin birebir geçmesi beklenmemelidir. Arama, soru ve gündelik dilde sık geçen ama ayırt ediciliği olmayan kelimeleri (`soru`, `hangi`, `için`, `her` gibi) otomatik olarak eler.

Kapsam, parça (satır/sayfa) yerine belge düzeyinde ölçülür; çünkü bir soru tek parçaya sığmaz. Farklı çekimler ortak kök üzerinden eşleşir (`feshettiğinde` -> `feshederse`).

### Kaynak metni nasıl saklanır
PDF/DOCX/TXT çıkarımı metni sabit genişlikte sarar; her satırı ayrı parça saymak 3-4 satırlık bir metni 15 ayrı kaynak hâline getirir ve aramayı zayıflatır (bir cümle tek satıra sığmaz). Bu yüzden ardışık satırlar paragraflara birleştirilir. Satır sonunda bölünen kelimeler belge sözlüğüne ve Türkçe ek yapısına bakılarak onarılır ("öde"+"nir" → "ödenir").

Sınır: belgede yalnızca kırık biçimde geçen ve ek soyma ile de tanınamayan bir bölünme onarılamaz; bu durumda iki parça boşlukla birleştirilir. Yanlış birleştirme (iki ayrı kelimeyi birleştirmek) daha büyük hata olduğu için emin olunmayan durumda boşluk korunur.

### Akıllı arama (Ollama)
İki mod vardır:

- **Hızlı akıllı arama (gömme)** — varsayılan. Soru ve adaylar vektöre çevrilir (`nomic-embed-text`), benzerlik ölçülür. Metin üretilmediği için saniyeler sürer.
- **Model puanlaması** — model her adaya 0-10 puan verir. Daha ayrıntılıdır ama yavaştır.

Her iki modda da en düşük ilgi puanının (varsayılan 3) altındaki sonuçlar gizlenir; 0 puanlı ilgisiz parçalar listeyi doldurup asıl kaynağı gizlemesin.

Gömme modelini bir kez indirmeniz gerekir: `ollama pull nomic-embed-text`. Ayarlar > `Gömme modeli`.

`Akıllı ara (Ollama)` düğmesi iki aşamalı çalışır: önce model sorudan anahtar kavramları çıkarır (seçenekleri yok sayar), sonra getirilen adayları soruyla anlamsal ilgilerine göre 0-10 arası puanlayıp sıralar. Kelime eşleşmesinin kaçırdığı eşanlamlı ve farklı çekimli ifadeleri yakalar. Ollama gerekir; yoksa uyarı verir ve normal arama kullanılabilir kalır.

İstekler **akışlı** (streaming) gönderilir: model yanıtı parça parça ürettiği için yavaş bilgisayarlarda da istek tamamlanır ve durum çubuğunda ilerleme görünür. Arama başlamadan önce Ollama'nın çalışıp çalışmadığı ve modelin yüklü olup olmadığı hızlıca kontrol edilir. Yapısal çağrılarda Ollama'nın JSON kısıtı (`format: json`) kullanılır; yine de model geçerli JSON döndürmezse yanıt içinden JSON ayıklanır (markdown bloğu, çevre metin, tek tırnak, sondaki virgül). Tek bir parça puanlanamazsa arama çökmez; o parça puansız listelenir.

**"zaman aşımı" hatası alırsanız:** Ollama çalışıyor demektir, yalnızca model yetişmemiştir. Şunları deneyin:
- Daha küçük/hızlı bir model kullanın (ör. `qwen2.5:1.5b` veya `llama3.2:3b`). Ayarlar > `Ollama model adı`.
- Ayarlar > `Ollama yanıt süresi (saniye)` değerini artırın (varsayılan 300).
- İlk çağrı modeli belleğe yüklediği için yavaştır; ikinci deneme genelde çok daha hızlıdır.
- Model belleğe sığmıyorsa her seferinde diskten yüklenir; daha küçük model seçin.

Ollama, aramada bulunan kaynak parçalarına göre not hazırlar; arşivde bulunmayan bilgileri kaynaklardan doğrulayamaz. Üretilen notları kaynaklarla karşılaştırın. OCR hataları, tablolar ve karmaşık sayfa düzenleri sonuçları etkileyebilir.

## Testler
Geliştirme bağımlılıklarını kurup testleri çalıştırın:

```powershell
pip install -r requirements-dev.txt
pytest
```

`tests/` klasöründe Türkçe katlama, arama motoru, belge çıkarımı ve dışa aktarma testleri bulunur. Testler geçici veritabanı kullanır; mevcut arşive dokunmaz.

## Sorun giderme
- `py` bulunamadı: Python kurulumunu PATH seçeneğiyle yeniden yapın veya `python` komutunu deneyin.
- PowerShell aktivasyon engeli: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` çalıştırın, sonra etkinleştirme komutunu yeniden deneyin.
- Ollama hatası: Ollama uygulamasının çalıştığını ve modelin `ollama list` çıktısında göründüğünü doğrulayın.
- OCR hatası: Tesseract yolunu ve `tur`/`eng` dil verilerini kontrol edin.
