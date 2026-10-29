import zipfile

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


# --- Oluşturulan raporları listeleme (Raporlar sekmesi) -------------------

def test_list_reports_empty_folder(export_dir):
    assert exporter.list_reports() == []


def test_list_reports_newest_first_with_kind_and_size(export_dir):
    exporter.export_results(RESULTS, fmt="txt", query="tazminat")
    exporter.export_csv(RESULTS)
    reports = exporter.list_reports()
    assert len(reports) == 2
    assert reports[0]["modified"] >= reports[1]["modified"]      # en yeni önce
    kinds = {r["kind"] for r in reports}
    assert kinds == {"Metin / konu notu", "CSV tablo"}
    assert all(r["size"] > 0 and r["path"].exists() for r in reports)


def test_report_kind_labels(export_dir):
    assert exporter.report_kind("a.pdf") == "PDF raporu"
    assert exporter.report_kind("a.docx") == "Word raporu"
    assert exporter.report_kind("a.zip") == "Yedek"
    assert exporter.report_kind("a.xyz") == "Dosya"


def test_list_reports_finds_nested_files(export_dir):
    """Alt klasördeki raporlar da listede görünmeli."""
    sub = export_dir / "eski"
    sub.mkdir()
    (sub / "rapor.txt").write_text("içerik", encoding="utf-8")
    reports = exporter.list_reports()
    assert [r["name"] for r in reports] == ["rapor.txt"]


def test_list_reports_skips_hidden_files(export_dir):
    (export_dir / ".gizli").write_text("x", encoding="utf-8")
    assert exporter.list_reports() == []


def test_human_size_formats_turkish_decimal(export_dir):
    assert exporter.human_size(512) == "512 B"
    assert exporter.human_size(2048) == "2,0 KB"
    assert exporter.human_size(5 * 1024 * 1024) == "5,0 MB"
