import re
from database import db, fts_enabled
from text_utils import tr_fold_for_search, tr_lower

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def normalize(text, ignore_turkish_case=True):
    """Arama karşılaştırması için metni tek biçime indirir.

    ignore_turkish_case=True: Türkçe karakterler eşitlenir (ç->c, ı/i->i).
    ignore_turkish_case=False: yalnızca Türkçe küçük harfe çevrilir, aksanlar korunur.
    """
    return tr_fold_for_search(text) if ignore_turkish_case else tr_lower(text)


def tokens(text, ignore_turkish_case=True):
    return [t for t in _WORD.findall(normalize(text, ignore_turkish_case)) if len(t) > 1]


def _match_expression(terms, all_terms):
    # Türkçe ekler için önek eşleşmesi: "tazminat" -> "tazminatı"yı da bulur.
    quoted = [f'"{t}"*' for t in terms]
    return (" AND " if all_terms else " OR ").join(quoted)


def _fts_candidates(con, terms, all_terms, candidate_limit):
    return con.execute("""
        SELECT c.id AS chunk_id, c.document_id, c.location, c.text,
               d.name AS document_name, d.stored_path, d.source_url
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        JOIN documents d ON d.id = c.document_id
        WHERE chunks_fts MATCH ?
        ORDER BY bm25(chunks_fts)
        LIMIT ?
    """, (_match_expression(terms, all_terms), candidate_limit)).fetchall()


def _scan_candidates(con, terms, all_terms, ignore_turkish_case):
    rows = con.execute("""
        SELECT c.id AS chunk_id, c.document_id, c.location, c.text,
               d.name AS document_name, d.stored_path, d.source_url
        FROM chunks c JOIN documents d ON d.id=c.document_id
    """).fetchall()
    out = []
    for r in rows:
        body = normalize(r["text"], ignore_turkish_case)
        present = [t for t in terms if t in body]
        if not present or (all_terms and len(present) != len(terms)):
            continue
        out.append(r)
    return out


def _score(query, text, terms, ignore_turkish_case):
    qnorm = normalize(query, ignore_turkish_case)
    body = normalize(text, ignore_turkish_case)
    present = [t for t in terms if t in body]
    exact = 4.0 if qnorm in body else 0.0
    coverage = len(present) / len(terms)
    occurrences = sum(body.count(t) for t in present)
    return exact + coverage * 5.0 + min(occurrences, 10) * 0.12


def search(query, limit=150, all_terms=False, ignore_turkish_case=True, use_fts=True):
    terms = list(dict.fromkeys(tokens(query, ignore_turkish_case)))
    if not terms:
        return None, []
    use_fts = use_fts and ignore_turkish_case and fts_enabled()
    candidate_limit = min(max(limit * 5, 500), 2000)
    with db() as con:
        cur = con.execute("INSERT INTO searches(query, created_at) VALUES (?, datetime('now','localtime'))", (query,))
        search_id = cur.lastrowid
        if use_fts:
            # FTS indeksi katlanmış metin üzerinde olduğu için sorgu da katlanır.
            fts_terms = list(dict.fromkeys(tokens(query, True)))
            candidates = _fts_candidates(con, fts_terms, all_terms, candidate_limit)
        else:
            candidates = _scan_candidates(con, terms, all_terms, ignore_turkish_case)
        scored = sorted(
            ((_score(query, r["text"], terms, ignore_turkish_case), r) for r in candidates),
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
