import re
from database import connect

def tokens(text):
    return [t.casefold() for t in re.findall(r"[^\W_]+", text, flags=re.UNICODE) if len(t) > 1]

def search(query, limit=150, all_terms=False, ignore_turkish_case=True):
    terms = list(dict.fromkeys(tokens(query)))
    if not terms:
        return None, []
    with connect() as con:
        cur = con.execute("INSERT INTO searches(query, created_at) VALUES (?, datetime('now','localtime'))", (query,))
        search_id = cur.lastrowid
        rows = con.execute("""
            SELECT c.id AS chunk_id, c.document_id, c.location, c.text,
                   d.name AS document_name, d.stored_path
            FROM chunks c JOIN documents d ON d.id=c.document_id
        """).fetchall()
        scored = []
        qnorm = query.casefold()
        for r in rows:
            raw = r["text"]
            body = raw.casefold()
            present = [t for t in terms if t in body]
            if not present or (all_terms and len(present) != len(terms)):
                continue
            exact = 4.0 if qnorm in body else 0.0
            coverage = len(present) / len(terms)
            occurrences = sum(body.count(t) for t in present)
            score = exact + coverage * 5.0 + min(occurrences, 10) * 0.12
            scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = scored[:limit]
        con.executemany("INSERT INTO results(search_id, chunk_id, score) VALUES (?, ?, ?)",
                        [(search_id, r["chunk_id"], score) for score, r in selected])
        con.commit()
    return search_id, [
        {"search_id": search_id, "chunk_id": r["chunk_id"], "document_id": r["document_id"],
         "document_name": r["document_name"], "stored_path": r["stored_path"],
         "location": r["location"], "text": r["text"], "score": score, "note": ""}
        for score, r in selected
    ]
