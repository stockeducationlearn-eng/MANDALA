"""Yayın paketi oluşturucu.

Kaynak klasörü `BilgiArastirma_TamPaket/` içeriğini `versiyon-N/` kopyasına
eşitler, `versiyon-N.zip` üretir ve `.downloads/index.html` sayfasını yeniler.

Kullanım:
    python3 yayinla.py 2
"""

import argparse
import pathlib
import shutil
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / "BilgiArastirma_TamPaket"
DOWNLOADS = ROOT / ".downloads"

# Sürüm kontrolüne ve dağıtıma girmemesi gereken çalışma zamanı klasörleri.
SKIP = {".venv", "venv", "data", "documents", "exports", "logs",
        "__pycache__", ".pytest_cache", ".mypy_cache"}


def mirror(dest):
    """Kaynağı hedef klasöre birebir eşitler (fazlalıkları siler)."""
    dest.mkdir(parents=True, exist_ok=True)
    for path in sorted(dest.rglob("*"), reverse=True):
        rel = path.relative_to(dest)
        if any(part in SKIP for part in rel.parts):
            continue
        if not (SOURCE / rel).exists():
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    for path in sorted(SOURCE.rglob("*")):
        rel = path.relative_to(SOURCE)
        if any(part in SKIP for part in rel.parts):
            continue
        target = dest / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def build_zip(version, folder):
    """Klasörü `versiyon-N/...` yapısıyla ZIP'ler."""
    DOWNLOADS.mkdir(exist_ok=True)
    out = DOWNLOADS / f"versiyon-{version}.zip"
    prefix = f"versiyon-{version}"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob("*")):
            rel = path.relative_to(folder)
            if any(part in SKIP for part in rel.parts) or not path.is_file():
                continue
            z.write(path, f"{prefix}/{rel.as_posix()}")
    return out


def write_index():
    """Tüm sürümleri listeleyen indirme sayfasını yazar."""
    zips = sorted(DOWNLOADS.glob("versiyon-*.zip"),
                  key=lambda p: int(p.stem.split("-")[1]))
    rows = "\n".join(
        f'<li><a href="{z.name}">{z.name}</a> — {z.stat().st_size // 1024} KB</li>'
        for z in zips)
    page = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>MANDALA indirmeler</title></head>
<body style="font-family:system-ui;max-width:640px;margin:40px auto">
<h1>BilgiArastirma TamPaket — indirmeler</h1>
<ul>
{rows}
</ul>
<p>En yeni sürüm: <strong>{zips[-1].stem if zips else 'yok'}</strong></p>
</body></html>
"""
    (DOWNLOADS / "index.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Sürüm paketi oluşturur.")
    parser.add_argument("version", type=int, help="sürüm numarası (ör. 2)")
    args = parser.parse_args()

    folder = ROOT / f"versiyon-{args.version}"
    mirror(folder)
    zip_path = build_zip(args.version, folder)
    write_index()
    print(f"Kopya: {folder}")
    print(f"ZIP:   {zip_path} ({zip_path.stat().st_size} bayt)")


if __name__ == "__main__":
    main()
