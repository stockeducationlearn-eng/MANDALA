"""Arama girdisini farklı kaynaklardan toplayan yardımcılar.

Kullanıcı yalnızca elle yazmak yerine bir dökümandan paragraf seçebilir,
bir resimden OCR ile metin çıkarabilir, ekran görüntüsü alabilir veya bir
web adresindeki sayfa metnini kullanabilir. Buradaki tüm fonksiyonlar ağ
erişimi dışında yan etkisizdir; dosya yazmaz.
"""

import io
import re

import requests
from PIL import Image

# Aşırı büyük yanıtları belleğe almamak için üst sınırlar.
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
REQUEST_TIMEOUT = 20
USER_AGENT = "BilgiArastirma/1.0 (+yerel arastirma araci)"

# Web sayfasında gövde metni sayılmayan etiketler.
_DROP_TAGS = ("script", "style", "noscript", "template", "svg", "head", "nav", "footer", "form")


def html_to_text(html):
    """HTML içeriğini okunabilir düz metne çevirir.

    BeautifulSoup varsa gövde etiketlerini tercih eder; yoksa basit bir
    regex temizliği uygular. Böylece paket kurulmasa da çalışır.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return _html_to_text_regex(html)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = main.get_text("\n")
    return _tidy(text)


def _html_to_text_regex(html):
    text = re.sub(r"(?is)<(script|style|noscript|head)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                         ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(entity, char)
    return _tidy(text)


def _tidy(text):
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def fetch_url_text(url, timeout=REQUEST_TIMEOUT):
    """Bir web adresinin metnini döndürür. Yalnızca http/https kabul edilir."""
    url = (url or "").strip()
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        raise ValueError("Geçerli bir adres girin (http:// veya https:// ile başlamalı).")
    response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT}, stream=True)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    chunks, total = [], 0
    for block in response.iter_content(64 * 1024):
        total += len(block)
        if total > MAX_DOWNLOAD_BYTES:
            break
        chunks.append(block)
    raw = b"".join(chunks)
    encoding = response.encoding or "utf-8"
    try:
        body = raw.decode(encoding, errors="replace")
    except LookupError:
        body = raw.decode("utf-8", errors="replace")
    if "html" in content_type or re.search(r"(?i)<html|<body", body[:2000]):
        return html_to_text(body)[:MAX_TEXT_CHARS]
    return _tidy(body)[:MAX_TEXT_CHARS]


def image_text(image, lang="tur+eng", tesseract_path=""):
    """Bir PIL görüntüsünden OCR ile metin çıkarır."""
    import pytesseract
    if tesseract_path:
        from pathlib import Path
        if Path(tesseract_path).exists():
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
    try:
        return pytesseract.image_to_string(image, lang=lang).strip()
    except Exception as exc:
        raise RuntimeError(f"OCR başarısız: {exc}") from exc


def image_file_text(path, lang="tur+eng", tesseract_path=""):
    """Bir resim dosyasından OCR ile metin çıkarır."""
    return image_text(Image.open(path), lang=lang, tesseract_path=tesseract_path)


def capture_screen_text(lang="tur+eng", tesseract_path="", region=None):
    """Ekran görüntüsü alıp OCR ile metnini döndürür.

    Önce `mss`, yoksa `PIL.ImageGrab` kullanılır. region=(x, y, genişlik, yükseklik)
    verilirse yalnızca o bölge alınır.
    """
    image = capture_screen(region=region)
    return image_text(image, lang=lang, tesseract_path=tesseract_path)


def capture_screen(region=None):
    """Ekranın (veya bir bölgenin) görüntüsünü PIL Image olarak döndürür.

    `mss` tercih edilir; kurulu değilse ya da ekrana bağlanamazsa
    (ör. başsız/headless oturum) `PIL.ImageGrab` denenir. İkisi de
    başarısız olursa anlaşılır bir hata verilir.
    """
    errors = []
    try:
        import mss
        factory = getattr(mss, "MSS", None) or mss.mss
        with factory() as sct:
            monitor = sct.monitors[1]
            if region:
                x, y, w, h = region
                monitor = {"left": x, "top": y, "width": w, "height": h}
            shot = sct.grab(monitor)
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except ImportError:
        pass
    except Exception as exc:
        errors.append(f"mss: {exc}")

    try:
        from PIL import ImageGrab
        box = None
        if region:
            x, y, w, h = region
            box = (x, y, x + w, y + h)
        return ImageGrab.grab(bbox=box)
    except Exception as exc:
        errors.append(f"ImageGrab: {exc}")

    raise RuntimeError("Ekran görüntüsü alınamadı. " + " | ".join(errors))


def image_bytes(image, fmt="PNG"):
    """PIL görüntüsünü bellekte kodlar (diske yazmadan)."""
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def list_paragraphs(path, min_length=1):
    """PDF/DOCX/TXT dosyasındaki metin bloklarını (konum, metin) olarak listeler."""
    from ingest import extract_file
    blocks = extract_file(path)
    return [(loc, text) for loc, text in blocks if len(text.strip()) >= min_length]


def preview(text, width=90):
    """Paragraf listesinde göstermek için tek satırlık kısa önizleme."""
    flat = " ".join((text or "").split())
    return flat[:width] + ("…" if len(flat) > width else "")
