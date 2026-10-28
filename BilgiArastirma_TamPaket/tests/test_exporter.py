import zipfile
from pathlib import Path

import pytest

import exporter


@pytest.fixture
def export_dir(tmp_path, monkeypatch):
    out = tmp_path / "exports"
    out.mkdir()
    monkeypatch.setattr(exporter, "EXPORT_DIR", out)
    return out


RESULTS = [
    {"document_name": "hukuk.txt", "location": "Satır 1", "score": 5.42,
     "text": "İşçinin kıdem tazminatı ve çalışma koşulları düzenlenmiştir.", "note": "önemli"},
    {"document_name": "saglik.txt", "location": "PDF sayfa 2", "score": 1.1,
     "text": "Sağlık hizmeti ödemesi.", "note": ""},
]


def test_export_txt_keeps_turkish(export_dir):
    path = exporter.export_results(RESULTS, fmt="txt", query="tazminat", mode="Kavram")
    text = path.read_text(encoding="utf-8-sig")
    assert "BİLGİ ARAŞTIRMA" in text
    assert "İşçinin kıdem tazminatı" in text
    assert "Kullanıcı notu: önemli" in text


def test_export_csv_uses_semicolon(export_dir):
    path = exporter.export_csv(RESULTS)
    text = path.read_text(encoding="utf-8-sig")
    header = text.splitlines()[0]
    assert header == "Kaynak;Konum;Puan;Metin;Not"
    assert "hukuk.txt" in text


def test_export_docx_is_readable(export_dir):
    from docx import Document
    path = exporter.export_results(RESULTS, fmt="docx", query="tazminat", mode="Kavram")
    doc = Document(str(path))
    joined = "\n".join(p.text for p in doc.paragraphs)
    assert "İşçinin kıdem tazminatı" in joined


def test_export_pdf_preserves_turkish(export_dir):
    import fitz
    path = exporter.export_results(RESULTS, fmt="pdf", query="tazminat", mode="Kavram")
    with fitz.open(path) as pdf:
        text = "".join(page.get_text() for page in pdf)
    # Gömülü DejaVuSans sayesinde Türkçe karakterler bozulmadan çıkmalı.
    assert "İşçinin kıdem tazminatı" in text


def test_backup_includes_db_and_documents(tmp_path, monkeypatch):
    db = tmp_path / "data" / "pdf_arastirma.db"
    db.parent.mkdir()
    db.write_bytes(b"SQLite format 3\x00")
    docs = tmp_path / "documents"
    docs.mkdir()
    (docs / "ornek.txt").write_text("içerik", encoding="utf-8")
    out = tmp_path / "exports"
    out.mkdir()
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    monkeypatch.setattr(exporter, "DB_PATH", db)
    monkeypatch.setattr(exporter, "EXPORT_DIR", out)

    target = exporter.backup_project()
    with zipfile.ZipFile(target) as z:
        names = set(z.namelist())
    assert "data/pdf_arastirma.db" in names
    assert "documents/ornek.txt" in names
