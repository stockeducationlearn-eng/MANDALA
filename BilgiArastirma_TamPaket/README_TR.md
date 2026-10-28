# BİLGİ ARAŞTIRMA — Tam Windows Paketi

## Özellikler
- PDF, DOCX, TXT, PNG, JPG/JPEG, BMP, TIFF kaynaklarını arşive alır.
- Kaynakları `documents/` klasörüne kopyalar; metinlerini SQLite'a kaydeder.
- PDF sayfa numarası, Word paragraf/tablo konumu, TXT satır numarası ve görsel adıyla sonuç gösterir.
- Türkçe karakter duyarlı/duyarsız arama seçeneği, tam ifade araması ve tüm kelimeler/eşleşen kelimeler modu.
- Kaynak sonuçlarına not ekleme, önceki aramaları tekrar açma.
- Kaynak dosyayı açma; bulunan tüm sonuçları tek raporda PDF, Word (DOCX), TXT veya CSV olarak dışa aktarma. PDF ve Word raporları varsa ekrandaki yapay zekâ konu notunu ve kaynak sonuçlarını birlikte içerir.
- Dört araştırma modu: Otomatik, Çıkmış soru, Paragraf/metin ve Kavram.
- Bir kavramın kaynaklarda geçtiği farklı yerleri bulup kaynak parçalarını birleştirerek konu notu oluşturma.
- Ollama'nın yanıtını ekranda düzenleme; notu SQLite veritabanına ve TXT dosyasına kalıcı kaydetme.
- İsteğe bağlı yerel Ollama modeliyle kaynak parçalarına dayalı açıklama.
- İsteğe bağlı Tesseract OCR: görseller ve taranmış PDF sayfaları.
- Veritabanı + kaynak arşivi için yedek oluşturma.

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

## OCR kurulumu
Tesseract OCR'ı ayrıca Windows'a kurun. Yaygın yol:
`C:\Program Files\Tesseract-OCR\tesseract.exe`
Ayarlar penceresinde yolu belirtin. Türkçe OCR için `tur` dil verisi, İngilizce için `eng` dil verisi bulunmalıdır. Ayarlarda `tur+eng` kullanabilirsiniz. Tesseract kurulmamışsa metin tabanlı PDF/Word/TXT araması yine çalışır; taranmış sayfalardaki metinler çıkarılamayabilir.

## Ücretsiz yerel yapay zekâ (isteğe bağlı)
1. Ollama'yı kurun.
2. PowerShell'de `ollama pull qwen2.5:3b` çalıştırın.
3. Ollama uygulaması çalışır durumdayken Bilgi Araştırma içinden `Kaynaklardan konu notu oluştur` seçeneğini kullanın.
4. `Araştırma türü` alanında `Çıkmış soru`, `Paragraf / metin` veya `Kavram` seçin. Örneğin tek başına `tazminat` yazıp `Kavram` modunu seçebilirsiniz.
5. Oluşan notu ekranda düzenleyip `Konu notunu arşivle` düğmesiyle veritabanına ve `exports/` klasörüne kaydedin.
4. Ayarlar içinden model adını değiştirebilirsiniz.

Model yerel bilgisayarda çalışır. Hız ve cevap kalitesi donanıma/model boyutuna bağlıdır. Temel arama için Ollama gerekmez. Uygulama yalnızca arama sonuçlarını modele gönderir; tüm 500 sayfalık kaynağı tek seferde göndermez. Model yanıtları yine de kaynak metniyle karşılaştırılmalıdır.

## Dosyalar
- `data/pdf_arastirma.db`: veritabanı (kaynaklar, arama geçmişi ve arşivlenmiş konu notları)
- `data/settings.json`: uygulama ayarları
- `documents/`: kaynak dosyalar
- `exports/`: CSV ve yedekler
- `logs/`: hata kayıtları

Bu klasörü yedeklemek için uygulamadaki `Yedek oluştur` düğmesini kullanın. Veritabanı ile belge arşivi birlikte ZIP'e alınır.

## Arama davranışı
Arama yerel metin eşleşmesi ve kelime örtüşmesine dayanır; gelişmiş vektör tabanlı anlamsal arama içermez. Soru metnini seçenekleriyle birlikte veya tek kavram olarak aratabilirsiniz. Ollama, aramada bulunan kaynak parçalarına göre not hazırlar; arşivde bulunmayan bilgileri kaynaklardan doğrulayamaz. Üretilen notları kaynaklarla karşılaştırın. OCR hataları, tablolar ve karmaşık sayfa düzenleri sonuçları etkileyebilir.

## Sorun giderme
- `py` bulunamadı: Python kurulumunu PATH seçeneğiyle yeniden yapın veya `python` komutunu deneyin.
- PowerShell aktivasyon engeli: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` çalıştırın, sonra etkinleştirme komutunu yeniden deneyin.
- Ollama hatası: Ollama uygulamasının çalıştığını ve modelin `ollama list` çıktısında göründüğünü doğrulayın.
- OCR hatası: Tesseract yolunu ve `tur`/`eng` dil verilerini kontrol edin.
