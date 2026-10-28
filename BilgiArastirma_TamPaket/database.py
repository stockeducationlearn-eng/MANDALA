import sqlite3
from pathlib import Path
from datetime import datetime

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

def init_db():
    with connect() as con:
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
        con.commit()

def list_documents():
    with connect() as con:
        return con.execute("""
        SELECT d.*, COUNT(c.id) AS chunk_count
        FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
        GROUP BY d.id ORDER BY d.added_at DESC
        """).fetchall()

def list_searches():
    with connect() as con:
        return con.execute("SELECT * FROM searches ORDER BY id DESC LIMIT 100").fetchall()

def delete_document(doc_id):
    with connect() as con:
        row = con.execute("SELECT stored_path FROM documents WHERE id=?", (doc_id,)).fetchone()
        con.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        con.commit()
        return row["stored_path"] if row else None
