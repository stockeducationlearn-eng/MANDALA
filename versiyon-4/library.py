"""Döküman arşivi adlandırma ve çakışma kuralları.

Arayüzden bağımsız, saf mantık; Tk penceresi açmadan test edilebilir.

Kural: arşivde aynı isimde iki döküman bulunmaz. Aynı isimle bir dosya
eklenmek istenirse işlem engellenir ve kullanıcıya yeni bir ad önerilir.
"""

from text_utils import tr_lower


def normalize_name(name):
    """Ad karşılaştırması için sadeleştirir.

    Türkçe küçük harfe indirir ve boşlukları tekilleştirir; böylece
    "Kıdem  Tazminatı.PDF" ile "kıdem tazminatı.pdf" aynı sayılır.
    """
    return " ".join(tr_lower((name or "").strip()).split())


def find_conflict(name, existing):
    """Aynı adlı mevcut kaydı bulur; yoksa None.

    existing: [{'id':.., 'name':.., 'sha256':..}, ...]
    """
    key = normalize_name(name)
    if not key:
        return None
    for doc in existing:
        if normalize_name(doc.get("name")) == key:
            return doc
    return None


def is_identical(conflict, sha256):
    """Çakışan kayıt içerik olarak da aynı mı (aynı dosya)?"""
    return bool(conflict) and conflict.get("sha256") == sha256


def suggest_name(name, existing):
    """Çakışmayan bir ad önerir: 'rapor.pdf' -> 'rapor (2).pdf'."""
    raw = (name or "").strip() or "belge"
    stem, dot, ext = raw.rpartition(".")
    if not dot:                       # uzantısız ad
        stem, ext = raw, ""
    taken = {normalize_name(d.get("name")) for d in existing}
    counter = 2
    while True:
        candidate = f"{stem} ({counter})" + (f".{ext}" if dot else "")
        if normalize_name(candidate) not in taken:
            return candidate
        counter += 1


def split_study_and_archive(documents):
    """Belgeleri çalışma listesi ve arşiv olarak ikiye ayırır.

    documents: in_study / in_archive alanlarını taşıyan kayıtlar.
    """
    study = [d for d in documents if d.get("in_study")]
    archive = [d for d in documents if d.get("in_archive")]
    return study, archive
