import shutil

import pytest
from PIL import Image

import text_sources
from conftest import PAGE


def test_html_to_text_drops_script_and_style():
    text = text_sources.html_to_text(PAGE)
    assert "Tazminat Hakkı" in text
    assert "İşçinin kıdem tazminatı" in text
    assert "gizli" not in text
    assert "color:red" not in text
    assert "&amp;" not in text


def test_html_to_text_regex_fallback_matches():
    text = text_sources._html_to_text_regex(PAGE)
    assert "Tazminat Hakkı" in text
    assert "gizli" not in text


def test_fetch_url_text_reads_html_page(web_server):
    text = text_sources.fetch_url_text(web_server + "/sayfa")
    assert "İşçinin kıdem tazminatı" in text
    assert "IĞDIR" in text


def test_fetch_url_text_reads_plain_text(web_server):
    text = text_sources.fetch_url_text(web_server + "/duz")
    assert text == "düz metin içerik"


def test_fetch_url_rejects_non_http():
    with pytest.raises(ValueError):
        text_sources.fetch_url_text("ftp://example.com/dosya")
    with pytest.raises(ValueError):
        text_sources.fetch_url_text("sadece metin")


def test_list_paragraphs_from_txt(tmp_path):
    src = tmp_path / "belge.txt"
    src.write_text("Birinci paragraf metni.\n\nİkinci paragraf metni.\n", encoding="utf-8")
    blocks = text_sources.list_paragraphs(src)
    assert len(blocks) == 2
    assert blocks[0][1] == "Birinci paragraf metni."


def test_preview_shortens_long_text():
    assert text_sources.preview("kısa") == "kısa"
    long = "kelime " * 40
    assert text_sources.preview(long, width=20).endswith("…")


def test_image_bytes_roundtrip():
    img = Image.new("RGB", (10, 10), "white")
    data = text_sources.image_bytes(img)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def _has_tesseract():
    return bool(shutil.which("tesseract"))


@pytest.mark.skipif(not _has_tesseract(), reason="Tesseract kurulu değil")
def test_image_file_text_reads_rendered_text(tmp_path):
    from PIL import ImageDraw, ImageFont
    img = Image.new("RGB", (420, 90), "white")
    ImageDraw.Draw(img).text((10, 25), "Tazminat 2026", fill="black", font=ImageFont.load_default())
    src = tmp_path / "resim.png"
    img.save(src)
    text = text_sources.image_file_text(src, lang="eng")
    assert "Tazminat" in text or "2026" in text


def test_image_text_reports_missing_tesseract():
    """Tesseract ikilisi yoksa net bir hata verilmeli (sessizce boş dönmemeli)."""
    if _has_tesseract():
        pytest.skip("Tesseract kurulu")
    with pytest.raises(RuntimeError, match="OCR"):
        text_sources.image_text(Image.new("RGB", (20, 20), "white"), lang="eng")


def test_capture_screen_reports_clear_error_without_display():
    """Ekran yoksa (başsız ortam) anlaşılır bir hata verilmeli."""
    import os
    if os.environ.get("DISPLAY") and shutil.which("xdotool"):
        pytest.skip("Görüntülenebilir bir ekran var")
    try:
        text_sources.capture_screen(region=(0, 0, 50, 50))
    except RuntimeError as exc:
        assert "Ekran görüntüsü alınamadı" in str(exc)
    except Exception as exc:  # pragma: no cover - bazı ortamlarda farklı hata
        pytest.fail(f"Beklenmeyen hata tipi: {type(exc).__name__}: {exc}")


@pytest.mark.skipif(not _has_tesseract(), reason="Tesseract kurulu değil")
def test_capture_screen_text_reads_generated_image(tmp_path):
    # Ekran yerine dosyadan okuyan yol; capture_screen_text ile aynı OCR hattı.
    from PIL import ImageDraw
    img = Image.new("RGB", (420, 90), "white")
    ImageDraw.Draw(img).text((10, 25), "Ekran 123", fill="black")
    text = text_sources.image_text(img, lang="eng")
    assert "123" in text
