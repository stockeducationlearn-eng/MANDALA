# Değişiklik Notları

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
