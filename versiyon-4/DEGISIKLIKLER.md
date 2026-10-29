# Değişiklik Notları

## Sürüm 4.0

1. adım iki bölüme ayrıldı ve kaynak yönetimi baştan kuruldu: yeni bir çalışma
için eklenen kaynaklarla, daha önce kullanılmış kaynakların tutulduğu döküman
arşivi artık ayrı listeler.

### Yeni döküman ekle

- `＋ Kaynak ekle…` ve `Girdi kaynağından al…` düğmeleri.
- Eklenen dosya doğrudan bu listeye girer ve aramada kullanılır.
- `Tümünü işaretle` / `İşaretleri kaldır` toplu seçim.
- Listeden çoklu satır seçip `Seçilileri arşive ekle` ya da
  `Seçilileri sil (toplu)` kullanılabilir.

### Döküman arşivi

- Daha önce kullanılmış kaynaklar burada tutulur; veritabanında saklanır.
- Arşivden bir kaynağı üstteki listeye sürükleyip bırakarak ya da seçip
  `Aramaya ekle` düğmesiyle alabilirsiniz.
- `Seçilileri arşivden çıkar` kaynağı arşivden çıkarır.
- Bir kaynak ya aramada ya arşivde bulunur; iki listede birden görünmez.

### Aynı isimde dosya engeli

- Arşivde aynı isimde bir kaynak varsa ekleme engellenir.
- Aynı içerikli dosya yeniden eklenirse kopya oluşmaz; mevcut kayıt kullanılır.
- Farklı içerikli ama aynı isimli dosyada yeniden adlandırma penceresi açılır.
  Önerilen ad (`rapor (2).pdf` gibi) hazır gelir; yeni ad girilmeden işlem sürmez.

### Arama kapsamı

- Arama yalnızca işaretli kaynaklarda yapılır.
- İşaretli kaynaklar silindiğinde seçim, arama boş dönmesin diye kalan
  kaynaklara düşer.

### Teknik

- `documents` tablosuna `in_study` ve `in_archive` sütunları eklendi. Eski
  veritabanları yükseltmede çalışma listesine taşınır; kullanıcının aramaları
  boş dönmez.
- Ad karşılaştırması Türkçe küçük harfe göre yapılır: "RAPOR.PDF" ile
  "rapor.pdf" aynı sayılır.
- Ad çakışması mantığı `library.py` içinde, arayüzden bağımsız tutulur.

### Testler

Test sayısı 133'ten **169'a** çıktı (2 test ortama bağlı olarak atlanır).
Kütüphane adlandırma kuralları, ad/içerik çakışması, yeniden adlandırmayla
çözüm, çalışma-arşiv ayrımı ve toplu silme sonrası seçim tutarlılığı sınanır.
Ayrıca `test_ai_helper` içindeki taklit vektör üreteci, süreç başına
rastgeleleştirilen `hash()` yerine `crc32` kullanacak biçimde düzeltildi; test
aralıklı olarak başarısız oluyordu.

## Sürüm 3.0

Arayüz artık tek ekran değil, adım adım ilerleyen bir akış. Üstte adım
göstergesi, altta `Geri` / `İleri` düğmeleri var. Aynı anda yalnızca bir adım
görünür; böylece ekran kalabalığı kalktı.

### Adım 1 — Kaynak ekle ve seç

- `＋ Kaynak ekle` ve `Girdi kaynağından al…` düğmeleri.
- Kaynak listesi tam genişlikte; `Aramada` sütunundan işaretleme.
- `Tümü` / `Hiçbiri` toplu seçim.
- Altta "Aramaya dâhil: 3/7 kaynak seçili" biçiminde özet.

### Adım 2 — Ara

İki sekme içerir:

- **Sorgu ve sonuçlar:** sorgu kutusu, `Ara`, `Akıllı ara (Ollama)`,
  `Girdi kaynağı…`, `Temizle`; araştırma türü, eşleşme oranı ve Türkçe
  duyarlılık seçenekleri; sonuç tablosu.
- **Son aramalar:** geçmiş aramalar listesi.

Bir sonuca çift tıklandığında 3. adım açılır ve kaynak metni gösterilir.

### Adım 3 — Sonuç ve rapor

İki sekme içerir:

- **Kaynak metni ve not:** konu notu oluşturma, arşivleme, PDF/Word/TXT/CSV
  rapor üretme, kaynak dosyayı açma; seçili kaynak metni ve not alanı.
- **Raporlar:** üretilen raporların listesi (tür, boyut, tarih, ad).

### Gezinme

- Adım göstergesindeki düğmelere tıklayarak doğrudan geçebilirsiniz.
- `Geri` / `İleri` düğmeleri; ilk ve son adımda ilgili düğme pasif olur.
- Kısayollar: `Ctrl+1`, `Ctrl+2`, `Ctrl+3` adımlara; `Ctrl+R` raporlar
  listesine.
- Adım düğmelerinde sayı görünür: kaç kaynak eklendiği ve kaç sonuç bulunduğu.
- Arama bittiğinde durum satırı sonuçları görmek için `İleri`ye geçmeyi önerir.

### Testler

Test sayısı 127'den **133'e** çıktı (2 test ortama bağlı olarak atlanır).
Adım sayısı, adım geçişleri (ilk/son sınırları), aynı anda yalnızca bir adımın
görünmesi, sıra dışı adım numaralarının sınırlanması, sekmelerin doğru adımda
olması ve adım düğmelerindeki kaynak sayısı penceresiz ortamda sınanır.

## Sürüm 2.0

Bu sürümde uygulama, tek ekranlı bir araçtan sekmeli ve menülü bir masaüstü
uygulamasına dönüştürüldü. Ayrıca kaynak seçimi ve oluşturulan raporlara erişim
eklendi.

### Yeni: Menü çubuğu

Üstte, tüm işlemleri toplayan bir menü çubuğu var:

- **Dosya:** Kaynak ekle, girdi kaynağından al, yedek oluştur, çıkış.
- **Ara:** Ara, akıllı ara, sorguyu temizle, son aramalar.
- **Kaynaklar:** Tüm kaynakları aramaya dâhil et, hiçbirini kullanma, kaynak sil,
  kaynak dosyayı aç.
- **Rapor:** Raporlar sekmesini aç, PDF/Word/TXT/CSV raporu üret, konu notunu
  arşivle, rapor listesini yenile.
- **Görünüm:** Sekmeler arasında geçiş, ayarlar.
- **Yardım:** Hakkında (sürüm bilgisiyle).

Kısayollar: `Ctrl+O` kaynak ekle, `Ctrl+G` girdi kaynağı, `Ctrl+Enter` ara,
`Ctrl+Shift+Enter` akıllı ara, `Ctrl+R` raporlar, `Ctrl+Q` çıkış.

### Yeni: Sekmeli arayüz

Arama ekranı korunurken yanına ikinci bir sekme eklendi:

- **Arama sekmesi:** Önceki tek ekranın tamamı (sorgu, mod, sonuç tablosu,
  kaynak metni, notlar).
- **Raporlar sekmesi:** Oluşturulan raporları listeler.

### Yeni: Oluşturulan raporlara ulaşma

**Raporlar** sekmesinde `exports/` klasöründeki tüm raporlar listelenir:

- Tür (PDF raporu, Word raporu, Metin/konu notu, CSV tablo, Yedek), boyut,
  oluşturulma zamanı ve dosya adı sütunları.
- En yeni rapor en üstte.
- **Aç** ve çift tıklama: raporu varsayılan uygulamada açar.
- **Sil:** seçili raporu siler.
- **Klasörü aç:** `exports` klasörünü dosya yöneticisinde açar.
- **Yenile:** listeyi yeniden tarar.

Her rapor üretildiğinde (PDF, Word, TXT, CSV, konu notu, yedek) liste otomatik
güncellenir; ayrıca bir şey yapmanız gerekmez.

### Yeni: Birden fazla kaynak ekleyip seçerek aramada kullanma

Sol taraftaki **Kaynak Kütüphanesi** tablosuna `Aramada` sütunu eklendi:

- Her kaynağın önünde `✓` işareti bulunur; arama yalnızca işaretli kaynaklarda
  yapılır.
- İşarete tıklayarak kaynağı aramaya dâhil edebilir ya da çıkarabilirsiniz.
- **Tümü / Hiçbiri** düğmeleri ve **Kaynaklar** menüsüyle toplu seçim yapılır.
- Seçim ayarlara kaydedilir; uygulama kapanıp açılsa da korunur.
- Hiçbir kaynak seçili değilken arama yapılırsa uyarı verilir (sessizce boş
  sonuç dönmez).
- Akıllı arama (Ollama) da seçilen kaynaklarla sınırlıdır.
- Seçili kaynakların tümü arşivden silinirse süzgeç kendiliğinden kalkar; böylece
  arama çıkmaz sokakta kalmaz.

### Teknik değişiklikler

- `search_engine.search(...)` artık `document_ids` parametresi alıyor. Süzgeç
  hem FTS5 hem tam tarama yolunda uygulanır.
- Yeni `scope.py` modülü: kaynak seçimi mantığı arayüzden bağımsız, test
  edilebilir biçimde.
- `exporter.list_reports()`, `exporter.report_kind()`, `exporter.human_size()`:
  rapor listeleme ve okunabilir boyut biçimlendirme.
- Uygulama sürümü `app.py` içindeki `APP_VERSION` sabitinde tutulur; pencere
  başlığında, üst şeritte ve Hakkında penceresinde görünür.

### Testler

Test sayısı 97'den **127'ye** çıktı (2 test ortama bağlı olarak atlanır).

- Kaynak seçimi süzgeci (FTS ve tam tarama yolu, kapsam moduyla birlikte).
- Rapor listeleme (sıralama, tür etiketleri, alt klasörler, gizli dosyalar,
  boyut biçimlendirme).
- Kaynak seçimi saf mantığı (`scope.py`).
- Arayüz kablolaması: menü başlıkları, sekmeler, tablo sütunları ve rapor
  listesinin çizimi Tk penceresi açmadan sınanır.

## Sürüm 1.0

- Genişletilmiş arama girdisi: dökümandan paragraf seçme, resimden OCR, ekran
  görüntüsü, web adresi.
- Türkçe harf katlama, kök eşleştirme ve kapsam modları (Herhangi biri, %60,
  %80, %100).
- Paragraf bazlı metin parçalama ve satır sonu onarımı.
- İlgi eşiği: 0 puanlı sonuçlar süzülür.
- Gömme (embedding) ile hızlı akıllı arama; Ollama zaman aşımı dayanıklılığı.
- PDF, Word, TXT ve CSV rapor dışa aktarma; konu notu arşivleme.
