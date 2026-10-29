# AGENTS.md

## Proje
MANDALA deposundaki `BilgiArastirma_TamPaket`: Windows'a yönelik, Tkinter GUI'li,
tamamen yerel bir belge arşivi + tam metin arama + raporlama uygulaması.
Ağ erişimi yalnızca isteğe bağlı yerel Ollama (`localhost:11434`) içindir.

## Komutlar
```bash
# Kurulum
python -m venv .venv && .venv/bin/python -m pip install -r requirements.txt

# Testler (geçici veritabanı kullanır, arşive dokunmaz)
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest

# Uygulama (GUI; headless ortamda çalışmaz, tkinter gerekir)
.venv/bin/python app.py
```

## Mimari
`app.py` (GUI/orkestrasyon) → servis modülleri → SQLite.
- `text_utils.py`: Türkçe harf katlama (`tr_lower`, `tr_upper`, `tr_fold_for_search`).
- `database.py`: bağlantı yönetimi (`db()` context manager), şema, FTS5 indeksi.
- `ingest.py`: dosya alma, SHA-256 dedup, PDF/DOCX/TXT/görsel metin çıkarımı + OCR.
- `search_engine.py`: FTS5 + geri dönüş taraması, kapsam süzgeci, puanlama.
- `text_sources.py`: dökümandan paragraf listeleme, resim/ekran OCR, web sayfası metni.
- `ai_helper.py`: Ollama prompt/istek, sorgu genişletme ve anlamsal sıralama.
- `exporter.py`: TXT/DOCX/PDF/CSV rapor + ZIP yedek; `list_reports()` ile rapor listeleme.
- `scope.py`: kaynak seçiminin (arama kapsamı) saf mantığı; Tk'sız test edilir.

## Kritik kurallar
- **Bağlantı yönetimi:** Asla çıplak `with connect() as con:` kullanmayın; bu yalnızca
  commit/rollback yapar, bağlantıyı kapatmaz. Her yerde `with database.db() as con:`
  kullanın.
- **Türkçe metin:** `str.lower()`/`str.upper()`/`str.casefold()` Türkçe için yanlıştır
  (İ/I/ı). Her zaman `text_utils` fonksiyonlarını kullanın.
- **FTS indeksi:** `chunks_fts` ham metni değil `tr_fold_for_search` ile katlanmış
  metni tutar; bu yüzden indeks yalnızca `database.add_chunks()` üzerinden
  güncellenir. Chunk'ları doğrudan INSERT ederseniz indeks ile veri ayrışır.
- **Arama:** `search(..., ignore_turkish_case=..., all_terms=..., min_coverage=...)`;
  FTS5 yalnızca OR (varsayılan) aramada ve duyarsız modda kullanılır, çünkü FTS önek
  eşleştirmesi ortak kökleri (`feshettiğinde`/`feshederse`) bulamaz. `all_terms=True`
  olduğunda tam tarama + kapsam süzgeci devreye girer.
- **Kapsam belge düzeyinde ölçülür:** `_document_coverages` terimleri belgenin tüm
  parçaları üzerinden arar. Parça (satır) bazında ölçmek, tek parçaya sığmayan soru
  metinlerinde yanlışlıkla boş sonuç verir.
- **Durdurma kelimeleri:** `content_terms()` sınav/gündelik dil kelimelerini eler
  (`text_utils.TR_STOPWORDS`). Ham terimler gerektiğinde `tokens()` kullanın.
- **Arama sorguları:** Türkçe ekler için önek (`"terim"*`) ve ortak kök eşleşmesi
  (`_term_matches`) kullanılır.
- **Ollama:** `ai_helper.expand_query` ve `rank_by_relevance` ağ çağrısı yapar ve
  hata durumunda `OllamaError` yükseltir; çağıran taraf (app.py) kullanıcıya anlaşılır
  mesaj gösterip normal aramaya düşmelidir. Model "arayıcı" değil "jüri"dir: adaylar
  önce kelime tabanlı aramayla getirilir.
- **Ollama akışı:** Tüm istekler `stream=True` ile gönderilir. `stream=False` isteğinde
  sunucu yanıtı tek parçada yollar; uzun üretim okuma zaman aşımına takılır ve
  kullanıcı yanlışlıkla "bağlanılamadı" hatası görür. Akışta zaman aşımı parça başına
  geçerlidir. Zaman aşımı ile bağlantı hatasını ayırt etmek için `_classify()` kullanın;
  ikisi de `requests.ConnectionError` olarak gelebilir, mesaj metnine bakmak gerekir.
- **Ollama ön kontrolü:** Uzun istekten önce `check_ollama()` ile sunucu ve model
  doğrulanır. Puanlama `batch_size` (varsayılan 10) ile gruplanır; tek büyük istek
  yavaş donanımda zaman aşımına uğrar.
- **Ollama JSON çıktısı:** Yapısal çağrılarda `format="json"` istenir; eski sürümler
  400 döndürürse kısıtsız yeniden denenir. Model yine de geçerli JSON vermeyebilir;
  ayrıştırma için `_extract_json()` kullanın (kod bloğu -> doğrudan -> dengeli bölge ->
  onarım -> kesik kapatma). Küçük modeller tek tırnak, sondaki virgül ve çevre metin
  üretir; `_as_score_map()` liste biçimini de kabul eder.
- **Ollama dayanıklılığı:** `rank_by_relevance` bozuk bir parti için bir kez yeniden
  dener, yine olmazsa o partiyi `ai_score=None` ile döndürür (arama çökmez). Puanlananlar
  önce, puanlanamayanlar özgün sırada sonda gelir; arayüz bunları "—" olarak gösterir.
- **Parçalama:** `ingest` satır satır parça kaydetmez; `text_utils.split_paragraphs`
  ile paragraf birleştirir. PDF çıkarımı metni sarar, satır başına parça bir cümleyi
  10+ kaynağa böler. Yeni kaynak türü eklerken bu fonksiyonu kullanın.
- **Ollama gömme:** `embed_texts` + `rank_by_embedding` metin üretmeden vektör
  benzerliğiyle sıralar; akıllı aramanın varsayılan (hızlı) modudur. Üretim yapan
  `rank_by_relevance` yavaştır, alternatif olarak kalır. Yeni Ollama `/api/embed`
  toplu kabul eder, eskisi `/api/embeddings` tek tek.
- **İlgi süzgeci:** `filter_by_score` eşiğin altındaki ve puanlanamayan sonuçları
  eler; varsayılan 3 (`settings["ai_min_score"]`). 0 puanlı ilgisiz parçalar
  listeyi doldurup asıl kaynağı gizlediği için süzülür.
- **Metin kaynakları:** `text_sources.py` dış ağa yalnızca `requests` ile çıkar; dosya
  yazmaz. Web getirme `http`/`https` dışını reddeder ve yanıt boyutunu sınırlar.
  `app.py` içindeki `InputSourceDialog` ağır işleri (OCR, indirme) arka plan iş
  parçacığında yapar ve sonucu `after()` ile ana iş parçacığına taşır; Tk çağrılarını
  asla iş parçacığından yapmayın.
- **Web kaynakları:** `documents.stored_path` yerel `.txt` kopyasını tutar; kaynak
  adresi `documents.source_url` sütunundadır. Yolu dosya varsayarak kullanan her kod
  `source_url` durumunu ele almalı (bkz. `open_source`).
- **Kaynak seçimi:** `search(..., document_ids=[...])` süzgeci hem FTS hem tam tarama
  yolunda uygulanır. Kapsam kararı `scope.resolve_scope` ile verilir: `None` = tümü,
  boş liste = hiçbiri (kullanıcı uyarılır), liste = yalnızca o belgeler. Seçili
  belgelerin tümü silinirse `resolve_scope` `None` döndürür, böylece arama çıkmaz
  sokakta kalmaz. Bu mantığı app.py'ye gömmeden `scope.py` içinde tutun.
- **Çalışma / arşiv ayrımı:** `documents.in_study` aramada kullanılacak kaynakları,
  `documents.in_archive` arşivdekileri belirtir. `database.list_study_documents()` ve
  `list_archive_documents()` birbirini dışlar: arşiv sorgusu `in_study=0` koşulunu da
  taşır, böylece eski bir kayıt iki listede birden görünmez. Bir kaynağı arşive
  taşırken `set_in_archive(..., True)` ile birlikte `set_in_study(..., False)`
  çağrılmalı; tersi için de aynısı geçerlidir.
- **Ad çakışması:** Arşivde aynı isimde iki döküman bulunmaz. Karar mantığı
  `library.py` içindedir (`find_conflict`, `is_identical`, `suggest_name`); `ingest.py`
  bunu `NameConflictError` / `DuplicateError` hâline getirir. Aynı içerik (`sha256`)
  yeniden eklenirse kopya oluşmaz, mevcut kayıt döndürülür. Ad karşılaştırması
  `normalize_name` ile Türkçe küçük harfe indirilir; `str.lower()` kullanmayın.
  Yeniden adlandırma diyaloğu (`RenameDialog`) yalnızca ana iş parçacığında açılır;
  arka planda çalışan `add_sources` bunun için `_ask_rename` köprüsünü kullanır.
- **Toplu silme:** `delete_selected_ids` sonrası arama seçimi `scope.selection_after_delete`
  ile düzeltilir; seçili kaynakların tümü silinirse seçim kalanlara düşer ki arama
  sessizce boş dönmesin.
- **Arayüz kablolaması:** Menü, adım ve tablo sütunlarını değiştirdiğinizde
  `tests/test_app_ui.py` içindeki sahte Tk katmanını da güncelleyin; bu testler
  penceresiz ortamda kurulumu doğrular.
- **Adım akışı:** `_build_ui` üç adım çerçevesini (`_build_step_sources`,
  `_build_step_search`, `_build_step_result`) `self.step_frames` listesine ekler;
  `show_step(n)` yalnızca birini `pack` eder. 1. adım yatay bir `Panedwindow`
  (`self.sources_panes`) içinde yan yana iki `LabelFrame` barındırır: solda
  `study_section` (yeni çalışma, `weight=3`), sağda döküman arşivi (`weight=2`).
  Panelleri adım çerçevesine doğrudan `pack` etmeyin; `panes.add(...)` kullanın,
  aksi halde yan yana düzen bozulur. Sürükle-bırak `winfo_containing`
  ile bırakma noktasını bulur; testler `_archive_drag_drop`'u doğrudan çağırır.
  Widget'ları adım dışına taşımayın; `self.doc_tree`, `self.archive_tree`,
  `self.result_tree` gibi alanlar kurulum sırasında oluşturulmalı, çünkü menü ve
  kısayollar onlara erişir. Kullanıcıya görünen işlemlerin kimlik alan sürümlerini
  (`*_from_ids`, `*_ids`) ayırın; böylece hem menü hem test tek kod yolunu kullanır.
- **Rapor listesi:** `exporter.list_reports()` dosya sistemini tek kaynak kabul eder,
  ayrıca veritabanı kaydı tutmaz. `EXPORT_DIR` monkeypatch ile değiştirilebilir.
- **Sürüm:** `app.py` içindeki `APP_VERSION` sabiti pencere başlığında, üst şeritte ve
  Hakkında penceresinde kullanılır; sürüm artırırken burayı ve `DEGISIKLIKLER.md`
  dosyasını güncelleyin.

## Notlar
- `fonts/DejaVuSans.ttf` repoya gömülüdür; PDF raporlarında Türkçe karakterler
  bu font sayesinde korunur. Fontu kaldırmayın.
- Çalışma zamanı klasörleri (`data/`, `documents/`, `exports/`, `logs/`) ve
  `__pycache__/` sürüm kontrolüne girmemeli (bkz. `.gitignore`).
- tkinter bu konteynerde yok; GUI'yi burada çalıştırmaya çalışmayın, testlerle
  doğrulayın.
