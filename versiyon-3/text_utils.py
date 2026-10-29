"""Türkçe metin normalizasyonu.

`str.lower()`/`str.upper()` Türkçe için yanlıştır: "İ" -> "i̇" (i + birleşen
nokta) ve "I" -> "i" üretir. SQLite'ın unicode61 tokenizer'ı da i/ı ayrımını
çözmez. Bu modül Türkçe kurallarına uygun katlama sağlar.
"""

import re
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


_LETTERS = re.compile(r"[^\W\d_]+", re.UNICODE)
_SENTENCE_END = (".", "!", "?", ":", ";", "…")
# Satır sonunda bölünmüş kelimenin devamını tanımak için yaygın Türkçe ekler.
_SUFFIXES = (
    "larina", "lerine", "larinda", "lerinde", "larini", "lerini",
    "lari", "leri", "lar", "ler", "mesi", "masi", "ması", "mesı",
    "nin", "nın", "nun", "nün", "sini", "sıni", "ini", "ını", "unu", "ünü",
    "den", "dan", "ten", "tan", "lik", "lık", "luk", "lük", "dir", "dır", "dur", "dür",
    "de", "da", "te", "ta", "me", "ma", "si", "sı", "su", "sü", "i", "ı", "u", "ü", "e", "a",
)


def _vocabulary(text):
    """Metindeki tüm kelimeleri (küçük harfe indirilmiş) sayar."""
    counts = {}
    for word in _LETTERS.findall(text):
        key = tr_lower(word)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _looks_joined(tail_word, head_word, vocab):
    """İki parça birleşince gerçek bir kelime oluşuyor mu?

    Belgede bölünmüş kelimeler yalnızca kırık biçimde geçebildiği için düz
    sözlük kontrolü yetmez ("zedelen"+"mesi" -> "zedelenmesi" belgede yok).
    Bu yüzden yaygın Türkçe ekler de soyulup gövde aranır.
    """
    if len(tail_word) < 2 or len(head_word) < 2:
        return False
    joined = tail_word + head_word
    if joined in vocab:
        return True
    for suffix in _SUFFIXES:
        if joined.endswith(suffix) and len(joined) > len(suffix) + 2:
            stem = joined[: -len(suffix)]
            if stem in vocab:
                return True
    return False


def split_paragraphs(text, max_chars=900, vocabulary=None):
    """Satırlara bölünmüş metni paragraflara birleştirir.

    PDF/DOCX çıkarımı metni sabit genişlikte sarar; her satırı ayrı parça
    saymak hem sonuç listesini şişirir (3-4 satırlık metin 15 kaynak olur)
    hem de aramayı zayıflatır, çünkü bir cümle tek satıra sığmaz. Burada
    ardışık satırlar cümle bitişi, başlık ve uzunluk sınırına göre
    paragraflara toplanır.

    Satır sonunda bölünmüş kelimeler belge sözlüğüne ve Türkçe ek yapısına
    bakılarak onarılır ("öde"+"nir" -> "ödenir"). Belgede yalnızca kırık
    biçimde geçen ve ek soyma ile de tanınamayan kelimeler onarılamaz; bu
    durumda boşlukla birleştirilir (yanlış birleştirmeden daha güvenli).
    """
    vocab = vocabulary if vocabulary is not None else _vocabulary(text)
    lines = [ln.strip() for ln in text.splitlines()]
    paragraphs = []
    for line in lines:
        if not line:
            paragraphs.append(None)   # boş satır paragraf sınırıdır
            continue
        if not paragraphs or paragraphs[-1] is None:
            paragraphs.append(line)
            continue
        previous = paragraphs[-1]
        ends_sentence = previous.rstrip().endswith(_SENTENCE_END)
        # Başlık gibi kısa ve noktalama ile bitmeyen satırlardan sonra yeni
        # paragraf başlar (ör. "Hukukun Temel Kavramları" + "Manevi tazminat…").
        heading_like = len(previous) < 60 and not ends_sentence
        starts_new = (
            (ends_sentence and len(previous) > 40 and line[:1].isupper())
            or (heading_like and line[:1].isupper())
        )
        if starts_new or len(previous) >= max_chars:
            paragraphs.append(line)
            continue
        if previous.endswith("-"):
            paragraphs[-1] = previous[:-1] + line          # tire ile bölünmüş kelime
            continue
        tail = _LETTERS.search(previous[::-1])
        head = _LETTERS.match(line)
        if tail and head:
            tail_word = tail.group(0)[::-1]
            head_word = head.group(0)
            if _looks_joined(tr_lower(tail_word), tr_lower(head_word), vocab):
                paragraphs[-1] = previous + line            # bölünmüş kelime
                continue
        paragraphs[-1] = previous + " " + line              # normal satır kaydırması
    return [p for p in paragraphs if p]


# Sınav sorusu ve gündelik dilde geçen, arama ayırt ediciliği olmayan kelimeler.
# Katlanmış (tr_fold_for_search çıktısı) biçimde tutulur; bu yüzden "için" -> "icin".
TR_STOPWORDS = frozenset("""
acaba ama ancak ardindan artik aslinda az bana bazen bazi bazilari belki ben benden beni
benim beri bes bile bin bir bircok biri birisi birkac birsuru biz bizden bize bizim boyle
boylece bu buna bunda bundan bunlar bunlari bunlarin bunu bunun burada cok cunku da daha dahi
de defa degil diger diye dolayi dolayisiyla eden ederek eger elbette en fakat filan gene gibi
gore halen hani haric hatta hem hep hepsi her herhangi herkes hic hicbir icin icinde ile
ilgili ise iste kac kadar karsi karsin kez ki kim kime kimi kimin kimse kisaca madem mi mu
nasil ne neden nedenle nerede nereye nicin niye o olan olarak oldu oldugu oldugunu olmadigi
olmak olmasi olmayan olmaz olsa olsun olup olur olursa oluyor on ona ondan onlar onlardan
onlari onlarin onu onun orada oysa oyle ozellikle pek ragmen sadece sanki sen senden seni
senin siz sizden size sizin sonra sey seyden seye seyi seyler soyle su suna sunda sundan
sunlar sunlari sunlarin sunu sunun tarafindan tum tumu uzere var ve veya ya yani yine yoksa
zaten
soru cevap secenek secenekler secenegi asagida asagidaki asagidakiler asagidakilerden
hangisi hangileri hangisinde hangisine hangisine dogru dogrudur yanlis yanlistir degildir
nedir verilen ifade ifadeler ifadelerden ifadesi hangi durumda zaman hangi
""".split())


def is_stopword(token):
    """Kelime, arama ayırt ediciliği olmayan bir durdurma kelimesi mi?

    Karşılaştırma katlanmış biçim üzerinden yapılır; bu yüzden hem duyarlı
    ("için") hem duyarsız ("icin") modda aynı sonucu verir.
    """
    return tr_fold_for_search(token) in TR_STOPWORDS
