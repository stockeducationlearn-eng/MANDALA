import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database  # noqa: E402


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Her test için izole, geçici bir veritabanı."""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    database.init_db()
    return database


@pytest.fixture
def ingest_dir(tmp_path, monkeypatch):
    """ingest'in belge arşivini geçici klasöre yönlendir."""
    import ingest
    docs = tmp_path / "documents"
    docs.mkdir(exist_ok=True)
    monkeypatch.setattr(ingest, "DOC_DIR", docs)
    return ingest
