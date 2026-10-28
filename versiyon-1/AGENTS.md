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
- `search_engine.py`: FTS5 + geri dönüş taraması, puanlama.
- `ai_helper.py`: Ollama prompt/istek.
- `exporter.py`: TXT/DOCX/PDF/CSV rapor + ZIP yedek.

## Kritik kurallar
- **Bağlantı yönetimi:** Asla çıplak `with connect() as con:` kullanmayın; bu yalnızca
  commit/rollback yapar, bağlantıyı kapatmaz. Her yerde `with database.db() as con:`
  kullanın.
- **Türkçe metin:** `str.lower()`/`str.upper()`/`str.casefold()` Türkçe için yanlıştır
  (İ/I/ı). Her zaman `text_utils` fonksiyonlarını kullanın.
- **FTS indeksi:** `chunks_fts` ham metni değil `tr_fold_for_search` ile katlanmış
  metni tutar; bu yüzden indeks yalnızca `database.add_chunks()` üzerinden
  güncellenir. Chunk'ları doğrudan INSERT ederseniz indeks ile veri ayrışır.
- **Arama:** `search(..., ignore_turkish_case=...)`; duyarsız mod FTS5 kullanır,
  duyarlı mod Python taramasına düşer. FTS5 yoksa otomatik geri dönüş vardır.
- **Arama sorguları:** Türkçe ekler için önek (`"terim"*`) kullanılır.

## Notlar
- `fonts/DejaVuSans.ttf` repoya gömülüdür; PDF raporlarında Türkçe karakterler
  bu font sayesinde korunur. Fontu kaldırmayın.
- Çalışma zamanı klasörleri (`data/`, `documents/`, `exports/`, `logs/`) ve
  `__pycache__/` sürüm kontrolüne girmemeli (bkz. `.gitignore`).
- tkinter bu konteynerde yok; GUI'yi burada çalıştırmaya çalışmayın, testlerle
  doğrulayın.
