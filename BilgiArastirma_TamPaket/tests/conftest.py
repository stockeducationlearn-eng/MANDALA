import http.server
import socket
import sys
import threading
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


class _PageHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGE if self.path == "/sayfa" else "düz metin içerik"
        content_type = "text/html; charset=utf-8" if self.path == "/sayfa" else "text/plain; charset=utf-8"
        if self.path not in ("/sayfa", "/duz"):
            self.send_response(404)
            self.end_headers()
            return
        raw = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


@pytest.fixture
def web_server():
    """Gerçek bir yerel HTTP sunucusu (mock değil)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _PageHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


PAGE = """<!doctype html>
<html><head><title>Deneme</title>
<style>.x{color:red}</style>
<script>var gizli = "görünmemeli";</script>
</head>
<body>
<h1>Tazminat Hakkı</h1>
<p>İşçinin kıdem tazminatı koşulları bu sayfada açıklanmıştır.</p>
<p>IĞDIR ili örneği &amp; çalışma düzeni.</p>
</body></html>"""

