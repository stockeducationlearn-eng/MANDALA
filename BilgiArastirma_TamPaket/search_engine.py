import re
from database import db, fts_enabled
from text_utils import tr_fold_for_search, tr_lower, is_stopword

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def normalize(text, ignore_turkish_case=True):
    """Arama karşılaştırması için metni tek biçime indirir.

    ignore_turkish_case=True: Türkçe karakterler eşitlenir (ç->c, ı/i->i).
    ignore_turkish_case=False: yalnızca Türkçe küçük harfe çevrilir, aksanlar korunur.
    """
    return tr_fold_for_search(text) if ignore_turkish_case else tr_lower(text)


def tokens(text, ignore_turkish_case=True):
    return [t for t in _WORD.findall(normalize(text, ignore_turkish_case)) if len(t) > 1]


def content_terms(text, ignore_turkish_case=True):
    """Aranacak ayırt edici terimleri çıkarır (durdurma kelimeleri elenir).

    Bir sınav sorusu verildiğinde "soru", "hangi", "için", "her" gibi kelimeler
    kaynakta hiç geçmediği için "hepsi eşleşsin" kuralını kilitler. Bu kelimeler
    atıldığında geriye anlam taşıyan terimler kalır. Hepsi durdurma kelimesi
    çıkarsa (ör. sorgu yalnızca "nedir"), boş liste döndürmemek için ham
    terimlere düşülür.
    """
    words = tokens(text, ignore_turkish_case)
    kept = [t for t in dict.fromkeys(words) if not is_stopword(t)]
    return kept or list(dict.fromkeys(words))


def _common_prefix_len(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _term_matches(term, body, body_words):
    """Terim, metinde geçiyor mu? (alt dize veya ortak kök eşleşmesi)

    Türkçe ekler yüzünden aynı kavram farklı biçimlerde görünür:
    "feshettiğinde" (soru) ve "feshederse" (kaynak) ya da "tazminatı" ve
    "tazminatına". Düz alt dize karşılaştırması bunları kaçırır; bu yüzden
    yeterince uzun ortak köke sahip kelimeler eşleşmiş sayılır.
    """
    if term in body:
        return True
    need = min(len(term), 5)
    for word in body_words:
        if _common_prefix_len(term, word) >= need:
            return True
    return False


def _match_expression(terms, all_terms):
    # Türkçe ekler için önek eşleşmesi: "tazminat" -> "tazminatı"yı da bulur.
    quoted = [f'"{t}"*' for t in terms]
    return (" AND " if all_terms else " OR ").join(quoted)


def _fts_candidates(con, terms, all_terms, candidate_limit, document_ids=None):
    sql = """
        SELECT c.id AS chunk_id, c.document_id, c.location, c.text,
               d.name AS document_name, d.stored_path, d.source_url
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        JOIN documents d ON d.id = c.document_id
        WHERE chunks_fts MATCH ?"""
    params = [_match_expression(terms, all_terms)]
    if document_ids:
        sql += f" AND c.document_id IN ({','.join('?' * len(document_ids))})"
        params.extend(document_ids)
    sql += " ORDER BY bm25(chunks_fts) LIMIT ?"
    params.append(candidate_limit)
    return con.execute(sql, params).fetchall()


def _chunk_present(text, terms, ignore_turkish_case):
    body = normalize(text, ignore_turkish_case)
    words = body.split()
    return [t for t in terms if _term_matches(t, body, words)]


def _document_coverages(candidates, terms, ignore_turkish_case):
    """Belge bazında kapsam oranı: {document_id: oran}.

    Kapsam neden belge düzeyinde ölçülür? Çünkü kaynaklar satır/sayfa gibi
    küçük parçalar hâlinde saklanır ve bir sınav sorusu ya da paragraf tek
    parçaya sığmaz. Terimler belgeye yayıldığında parça bazlı kapsam düşük
    kalır (ör. soru metninde satır başına %40) ve "çoğu eşleşsin" kuralı boş
    sonuç verir. Belge düzeyinde ölçüldüğünde gerçek örtüşme görünür.
    """
    by_doc = {}
    for r in candidates:
        by_doc.setdefault(r["document_id"], []).append(r["text"])
    coverages = {}
    for doc_id, texts in by_doc.items():
        body = normalize(" ".join(texts), ignore_turkish_case)
        words = body.split()
        present = [t for t in terms if _term_matches(t, body, words)]
        coverages[doc_id] = len(present) / len(terms)
    return coverages


def _filter_candidates(candidates, terms, threshold, ignore_turkish_case):
    """Adayları kapsama göre süzer.

    threshold <= 0: parça bazında en az bir terim yeterli (klasik OR araması).
    threshold  > 0: belge bazında kapsam eşiği uygulanır; eşiği geçen belgenin
                    en az bir terim içeren parçaları döndürülür.
    """
    if threshold <= 0:
        return [r for r in candidates if _chunk_present(r["text"], terms, ignore_turkish_case)]
    coverages = _document_coverages(candidates, terms, ignore_turkish_case)
    return [r for r in candidates
            if coverages.get(r["document_id"], 0.0) >= threshold
            and _chunk_present(r["text"], terms, ignore_turkish_case)]


def _scan_candidates(con, document_ids=None):
    sql = """
        SELECT c.id AS chunk_id, c.document_id, c.location, c.text,
               d.name AS document_name, d.stored_path, d.source_url
        FROM chunks c JOIN documents d ON d.id=c.document_id"""
    params = []
    if document_ids:
        sql += f" WHERE c.document_id IN ({','.join('?' * len(document_ids))})"
        params = list(document_ids)
    return con.execute(sql, params).fetchall()


def _score(query, text, terms, ignore_turkish_case, doc_coverage=0.0):
    qnorm = normalize(query, ignore_turkish_case)
    body = normalize(text, ignore_turkish_case)
    body_words = body.split()
    present = [t for t in terms if _term_matches(t, body, body_words)]
    exact = 4.0 if qnorm in body else 0.0
    # Parça kısa olabileceği için kapsam, belge kapsamından düşük olamaz;
    # aksi hâlde ilgili belgenin tüm parçaları haksız yere düşük puan alır.
    coverage = max(len(present) / len(terms), doc_coverage)
    occurrences = sum(body.count(t) for t in present)
    return exact + coverage * 5.0 + min(occurrences, 10) * 0.12


# Eşleşme modu: (etiket, tüm_terimler_zorunlu_mu, gereken_kapsam)
# "Herhangi biri" klasik OR aramasıdır; diğerleri terimlerin en az o oranını
# ister. Böylece bir sınav sorusu verildiğinde "hepsi birebir eşleşsin" kuralı
# boş sonuç yerine ilgili parçaları bulur.
MATCH_CHOICES = (
    ("Herhangi biri", False, 0.0),
    ("Çoğu (%60)", True, 0.6),
    ("Çok (%80)", True, 0.8),
    ("Tümü (%100)", True, 1.0),
)


def match_from_label(label):
    for name, all_terms, coverage in MATCH_CHOICES:
        if name == label:
            return all_terms, coverage
    return False, 0.0


def label_from_settings(all_terms, min_coverage):
    for name, terms_required, coverage in MATCH_CHOICES:
        if terms_required == all_terms and coverage == min_coverage:
            return name
    return "Herhangi biri"


def search(query, limit=150, all_terms=False, ignore_turkish_case=True, use_fts=True,
           min_coverage=0.6, drop_stopwords=True, document_ids=None):
    """Kaynak parçalarını sorguyla ilgi sırasına göre döndürür.

    all_terms=False: terimlerden en az biri geçen parçalar (OR) — kapsam eşiği
                     uygulanmaz.
    all_terms=True:  terimlerin en az `min_coverage` oranını içeren parçalar.
                     1.0 -> hepsi birebir (eski "tüm kelimeler" davranışı).
    drop_stopwords:  durdurma kelimelerini ("soru", "için", "her"...) eler.
    document_ids:    yalnızca bu belgelerde ara (kaynak seçimi); boş/None ise tümü.
    """
    terms = content_terms(query, ignore_turkish_case) if drop_stopwords \
        else list(dict.fromkeys(tokens(query, ignore_turkish_case)))
    if not terms:
        return None, []
    document_ids = list(document_ids) if document_ids else None
    threshold = (1.0 if min_coverage is None else min_coverage) if all_terms else 0.0
    # FTS5 yalnızca önek eşleştirmesi yapar; "feshettiğinde" ile "feshederse"
    # gibi ortak kökleri bulamaz. Bu yüzden kapsam süzgeci gerektiğinde tam
    # tarama kullanılır, FTS ise varsayılan OR aramasında devrede kalır.
    use_fts = use_fts and ignore_turkish_case and fts_enabled() and threshold <= 0
    candidate_limit = min(max(limit * 5, 500), 2000)
    with db() as con:
        cur = con.execute("INSERT INTO searches(query, created_at) VALUES (?, datetime('now','localtime'))", (query,))
        search_id = cur.lastrowid
        if use_fts:
            # FTS indeksi katlanmış metin üzerinde olduğu için sorgu da katlanır.
            fts_terms = list(dict.fromkeys(content_terms(query, True))) if drop_stopwords \
                else list(dict.fromkeys(tokens(query, True)))
            candidates = _fts_candidates(con, fts_terms, False, candidate_limit, document_ids)
        else:
            candidates = _scan_candidates(con, document_ids)
        candidates = _filter_candidates(candidates, terms, threshold, ignore_turkish_case)
        coverages = _document_coverages(candidates, terms, ignore_turkish_case)
        scored = sorted(
            ((_score(query, r["text"], terms, ignore_turkish_case,
                     coverages.get(r["document_id"], 0.0)), r) for r in candidates),
            key=lambda x: x[0], reverse=True,
        )[:limit]
        con.executemany("INSERT INTO results(search_id, chunk_id, score) VALUES (?, ?, ?)",
                        [(search_id, r["chunk_id"], score) for score, r in scored])
    return search_id, [
        {"search_id": search_id, "chunk_id": r["chunk_id"], "document_id": r["document_id"],
         "document_name": r["document_name"], "stored_path": r["stored_path"], "source_url": r["source_url"],
         "location": r["location"], "text": r["text"], "score": score, "note": ""}
        for score, r in scored
    ]
