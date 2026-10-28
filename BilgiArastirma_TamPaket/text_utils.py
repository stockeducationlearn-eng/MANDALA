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
