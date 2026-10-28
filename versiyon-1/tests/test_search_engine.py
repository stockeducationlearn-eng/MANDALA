import database
from search_engine import search


def _add(con, name, chunks):
    cur = con.execute(
        "INSERT INTO documents(name, stored_path, file_type, sha256, added_at) "
        "VALUES (?, ?, '.txt', ?, datetime('now','localtime'))",
        (name, f"/tmp/{name}", name),
    )
    doc_id = cur.lastrowid
    database.add_chunks(con, doc_id, chunks)
    return doc_id


def _seed(temp_db):
    with temp_db.db() as con:
        _add(con, "hukuk.txt", [
            ("Satır 1", "İşçinin kıdem tazminatı koşulları düzenlenmiştir."),
            ("Satır 2", "İstanbul IĞDIR arası çalışma ilişkisi."),
        ])
        _add(con, "saglik.txt", [
            ("Satır 1", "Sağlık hizmetlerinde ödeme ve şeker hastalığı."),
        ])


def test_fts_table_is_created(temp_db):
    assert temp_db.fts_enabled()


def test_index_stays_in_sync_with_chunks(temp_db):
    _seed(temp_db)
    with temp_db.db() as con:
        fts = con.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
        chunks = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    assert fts == chunks == 3


def test_search_finds_turkish_variants(temp_db):
    _seed(temp_db)
    for query in ("İstanbul", "istanbul", "ISTANBUL", "ıstanbul"):
        _, results = search(query)
        assert any("İstanbul" in r["text"] for r in results), query


def test_search_merges_dotted_and_dotless_i(temp_db):
    _seed(temp_db)
    _, results = search("igdir")
    assert any("IĞDIR" in r["text"] for r in results)


def test_search_matches_without_diacritics(temp_db):
    _seed(temp_db)
    _, results = search("calisma")
    assert any("çalışma" in r["text"] for r in results)


def test_turkish_sensitive_mode_keeps_diacritics(temp_db):
    _seed(temp_db)
    _, insensitive = search("calisma", ignore_turkish_case=True)
    _, sensitive = search("calisma", ignore_turkish_case=False)
    assert any("çalışma" in r["text"] for r in insensitive)
    assert sensitive == []


def test_fts_and_fallback_agree(temp_db):
    _seed(temp_db)
    _, via_fts = search("tazminat", use_fts=True)
    _, via_scan = search("tazminat", use_fts=False)
    assert [r["chunk_id"] for r in via_fts] == [r["chunk_id"] for r in via_scan]
    assert via_fts


def test_all_terms_requires_every_word(temp_db):
    _seed(temp_db)
    _, both = search("kıdem tazminatı", all_terms=True)
    _, missing = search("kıdem şeker", all_terms=True)
    assert both and not missing


def test_search_records_history(temp_db):
    _seed(temp_db)
    sid, results = search("tazminat")
    with temp_db.db() as con:
        stored = con.execute("SELECT COUNT(*) FROM results WHERE search_id=?", (sid,)).fetchone()[0]
    assert stored == len(results)


def test_empty_query_returns_nothing(temp_db):
    _seed(temp_db)
    assert search("   ") == (None, [])


def test_db_context_closes_connection(temp_db):
    import sqlite3
    import pytest
    con = None
    with temp_db.db() as c:
        con = c
    with pytest.raises(sqlite3.ProgrammingError):
        con.execute("SELECT 1")


def test_search_falls_back_without_fts(temp_db, monkeypatch):
    _seed(temp_db)
    monkeypatch.setattr("search_engine.fts_enabled", lambda: False)
    _, results = search("tazminat")
    assert any("tazminat" in r["text"] for r in results)


# --- Sınav sorusu / eşleşme oranı davranışı -------------------------------

QUESTION = """Soru: İşçi kıdem tazminatına hangi durumda hak kazanır?
A) İşçi kendi isteğiyle işten ayrıldığında her zaman
B) İşveren iş sözleşmesini haklı neden olmaksızın feshettiğinde ve işçi en az bir yıl çalışmışsa
C) İşçi bir aydan fazla çalıştığında
D) İşçi istifa ettiğinde
E) İşveren işçiyi geçici olarak başka işte çalıştırdığında"""


def _seed_law(temp_db):
    with temp_db.db() as con:
        _add(con, "is_kanunu.txt", [
            ("Satır 1", "İşçinin kıdem tazminatına hak kazanabilmesi için en az bir yıl çalışmış olması gerekir."),
            ("Satır 2", "İşveren iş sözleşmesini haklı bir neden olmaksızın feshederse kıdem tazminatı ödemekle yükümlüdür."),
            ("Satır 3", "Kıdem tazminatı her tam yıl için son giydirilmiş brüt ücretin otuz günlük tutarıdır."),
            ("Satır 4", "İşçinin kendi isteğiyle işten ayrılması hâlinde kıdem tazminatı ödenmez."),
        ])
        _add(con, "saglik.txt", [
            ("Satır 1", "Sağlık hizmetlerinde ödeme ve şeker hastalığı tedavisi görülür."),
        ])


def test_all_terms_no_longer_returns_empty_for_exam_question(temp_db):
    """Asıl şikâyet: soru metniyle 'hepsi eşleşsin' boş sonuç veriyordu."""
    _seed_law(temp_db)
    _, strict = search(QUESTION, all_terms=True, min_coverage=1.0)
    _, balanced = search(QUESTION, all_terms=True, min_coverage=0.6)
    assert strict == []
    assert balanced, "önerilen eşikte ilgili kaynak bulunmalı"
    assert all(r["document_name"] == "is_kanunu.txt" for r in balanced)


def test_coverage_threshold_excludes_unrelated_document(temp_db):
    _seed_law(temp_db)
    _, results = search(QUESTION, all_terms=True, min_coverage=0.6)
    assert results
    assert "saglik.txt" not in {r["document_name"] for r in results}


def test_stopwords_are_dropped_from_terms(temp_db):
    _seed_law(temp_db)
    _, results = search("kıdem tazminatı için hangi durumda hak", all_terms=True, min_coverage=0.6)
    assert results


def test_drop_stopwords_can_be_disabled(temp_db):
    from search_engine import content_terms, tokens
    query = "işçi için kıdem"
    assert "icin" not in content_terms(query)
    assert "icin" in tokens(query)


def test_turkish_suffix_variants_match_across_chunks(temp_db):
    """'feshettiğinde' (soru) ile 'feshederse' (kaynak) aynı kökten eşleşmeli."""
    _seed_law(temp_db)
    _, results = search("işveren sözleşmeyi feshettiğinde", all_terms=True, min_coverage=1.0)
    assert any("feshederse" in r["text"] for r in results)


def test_query_of_only_stopwords_does_not_crash(temp_db):
    """Sorgu tamamen durdurma kelimesiyse ham terimlere düşülür."""
    _seed_law(temp_db)
    sid, results = search("için ve ile", all_terms=True, min_coverage=0.6)
    assert isinstance(results, list)  # hata vermemeli


def test_short_query_still_matches_with_coverage_mode(temp_db):
    _seed_law(temp_db)
    _, results = search("kıdem", all_terms=True, min_coverage=0.6)
    assert results


