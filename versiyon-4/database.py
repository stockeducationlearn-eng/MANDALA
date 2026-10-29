import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from text_utils import tr_fold_for_search

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "pdf_arastirma.db"

def connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con

@contextmanager
def db():
    """Bağlantıyı garanti altında kapatır; hata durumunda rollback yapar."""
    con = connect()
    try:
        with con:
            yield con
    finally:
        con.close()

def _table_exists(con, name):
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE name=? AND type IN ('table','view')", (name,)
    ).fetchone() is not None

def _fts5_available():
    try:
        with closing(connect()) as con:
            con.execute("CREATE VIRTUAL TABLE temp.__fts5_probe USING fts5(x)")
            con.execute("DROP TABLE temp.__fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            stored_path TEXT NOT NULL UNIQUE,
            file_type TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            added_at TEXT NOT NULL,
            char_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Hazır'
        );
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            location TEXT NOT NULL,
            text TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
            chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            score REAL NOT NULL,
            note TEXT DEFAULT '',
            UNIQUE(search_id, chunk_id)
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
            chunk_id INTEGER REFERENCES chunks(id) ON DELETE CASCADE,
            title TEXT DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS research_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'Otomatik',
            body TEXT NOT NULL,
            sources TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        """)
        if _fts5_available():
            _setup_fts(con)
            _migrate_fts(con)
        _migrate_schema(con)


def _migrate_schema(con):
    """Eski veritabanlarına eksik sütunları ekler."""
    cols = {row["name"] for row in con.execute("PRAGMA table_info(documents)")}
    if "source_url" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN source_url TEXT DEFAULT ''")
    added = False
    if "in_study" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN in_study INTEGER DEFAULT 0")
        added = True
    if "in_archive" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN in_archive INTEGER DEFAULT 0")
        added = True
    if added:
        # Eski kayıtlar hem aramaya açık hem arşivde sayılır; böylece
        # yükseltmeden sonra kullanıcının aramaları boş dönmez.
        con.execute("UPDATE documents SET in_study=1, in_archive=1")

def _setup_fts(con):
    """Türkçe katlanmış metin üzerinde FTS5 indeksi.

    unicode61 tokenizer i/ı ayrımını çözmediği için indekse ham metni değil,
    `tr_fold_for_search` ile sadeleştirilmiş metni yazarız.
    """
    existing = con.execute(
        "SELECT sql FROM sqlite_master WHERE name='chunks_fts'"
    ).fetchone()
    if existing and "content=" in (existing["sql"] or ""):
        # Eski (harici içerikli) indeks şeması uyumsuz; baştan kur.
        con.execute("DROP TABLE chunks_fts")
        existing = None
    if not existing:
        con.execute("""
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                text,
                tokenize="unicode61"
            )
        """)

def add_chunks(con, doc_id, items):
    """chunk'ları ve FTS indeksini birlikte yazar. items: [(location, text)]."""
    ids = []
    for location, text in items:
        cur = con.execute("INSERT INTO chunks(document_id, location, text) VALUES (?, ?, ?)",
                          (doc_id, location, text))
        chunk_id = cur.lastrowid
        con.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                    (chunk_id, tr_fold_for_search(text)))
        ids.append(chunk_id)
    return ids

def _migrate_fts(con):
    """FTS indeksini chunk tablosuyla senkronla (sayı uyuşmuyorsa yeniden kur)."""
    chunk_count = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    fts_count = con.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    if chunk_count == fts_count:
        return
    con.execute("DELETE FROM chunks_fts")
    for row in con.execute("SELECT id, text FROM chunks"):
        con.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                    (row["id"], tr_fold_for_search(row["text"])))

def fts_enabled():
    return _fts5_available() and _table_exists_safe("chunks_fts")

def _table_exists_safe(name):
    try:
        with closing(connect()) as con:
            return _table_exists(con, name)
    except sqlite3.Error:
        return False

def list_documents():
    with db() as con:
        return con.execute("""
        SELECT d.*, COUNT(c.id) AS chunk_count
        FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
        GROUP BY d.id ORDER BY d.added_at DESC
        """).fetchall()


_DOC_WITH_CHUNKS = """
SELECT d.*, COUNT(c.id) AS chunk_count
FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
WHERE {where}
GROUP BY d.id ORDER BY d.added_at DESC
"""


def list_study_documents():
    """Geçerli çalışmaya alınmış kaynaklar (1. adımın üst bölümü)."""
    with db() as con:
        return con.execute(_DOC_WITH_CHUNKS.format(where="d.in_study=1")).fetchall()


def list_archive_documents():
    """Arşivdeki kaynaklar (1. adımın alt bölümü).

    Çalışma listesindeki bir kayıt arşivde de işaretliyse (eski veritabanı
    yükseltmesi) yalnızca üst listede gösterilir; iki listede birden görünmez.
    """
    with db() as con:
        return con.execute(
            _DOC_WITH_CHUNKS.format(where="d.in_archive=1 AND d.in_study=0")).fetchall()


def document_names():
    """Ad çakışması denetimi için kimlik/ad/içerik özeti listesi."""
    with db() as con:
        return [dict(row) for row in con.execute("SELECT id, name, sha256 FROM documents")]


def set_in_study(doc_ids, flag=True):
    """Kaynakları çalışma listesine ekler ya da çıkarır."""
    ids = list(doc_ids)
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with db() as con:
        con.execute(f"UPDATE documents SET in_study=? WHERE id IN ({placeholders})",
                    [1 if flag else 0, *ids])


def set_in_archive(doc_ids, flag=True):
    """Kaynakları arşive ekler ya da çıkarır."""
    ids = list(doc_ids)
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with db() as con:
        con.execute(f"UPDATE documents SET in_archive=? WHERE id IN ({placeholders})",
                    [1 if flag else 0, *ids])


def rename_document(doc_id, new_name):
    with db() as con:
        con.execute("UPDATE documents SET name=? WHERE id=?", (new_name, doc_id))

def list_searches():
    with db() as con:
        return con.execute("SELECT * FROM searches ORDER BY id DESC LIMIT 100").fetchall()

def delete_document(doc_id):
    with db() as con:
        row = con.execute("SELECT stored_path FROM documents WHERE id=?", (doc_id,)).fetchone()
        con.execute("DELETE FROM chunks_fts WHERE rowid IN (SELECT id FROM chunks WHERE document_id=?)",
                    (doc_id,))
        con.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        return row["stored_path"] if row else None
