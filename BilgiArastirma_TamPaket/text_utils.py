"""Türkçe metin normalizasyonu.

`str.lower()`/`str.upper()` Türkçe için yanlıştır: "İ" -> "i̇" (i + birleşen
nokta) ve "I" -> "i" üretir. SQLite'ın unicode61 tokenizer'ı da i/ı ayrımını
çözmez. Bu modül Türkçe kurallarına uygun katlama sağlar.
"""

import unicodedata

_TURKISH_LOWER = str.maketrans({"İ": "i", "I": "ı"})
_TURKISH_UPPER = str.maketrans({"i": "İ", "ı": "I"})

# Arama için aksan/şapka sadeleştirmesi; ı -> i birleştirmesi dahil.
_ASCII_FOLD = str.maketrans({
    "ı": "i", "ç": "c", "ğ": "g", "ö": "o", "ş": "s", "ü": "u",
    "â": "a", "î": "i", "û": "u", "ä": "a", "é": "e",
})


def tr_lower(text):
    """Türkçe kurallarına göre küçük harfe çevirir (İ->i, I->ı)."""
    return text.translate(_TURKISH_LOWER).lower()


def tr_upper(text):
    """Türkçe kurallarına göre büyük harfe çevirir (i->İ, ı->I)."""
    return text.translate(_TURKISH_UPPER).upper()


def tr_fold_for_search(text):
    """Arama anahtarı üretir: İ/I/ı ve tüm Türkçe aksanlar tek biçime iner.

    "İstanbul", "ISTANBUL", "ıstanbul" -> "istanbul"; "IĞDIR" ve "ığdır"
    -> "igdir"; "çalışma" -> "calisma". Böylece noktalı/noktasız i ve
    aksan farkları aramayı etkilemez.
    """
    folded = tr_lower(text).translate(_ASCII_FOLD)
    folded = unicodedata.normalize("NFKD", folded)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", folded)
