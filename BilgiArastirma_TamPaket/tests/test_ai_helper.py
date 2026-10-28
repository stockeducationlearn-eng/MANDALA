import http.server
import json
import socket
import threading
import time

import pytest

import ai_helper


class _OllamaHandler(http.server.BaseHTTPRequestHandler):
    """Gerçek bir HTTP uç noktası; akış (NDJSON) ve /api/tags davranışını taklit eder."""

    chunks = ["{}"]
    raw_lines = []
    delay = 0.0
    status = 200
    tags = []
    request_count = 0

    def _json(self, obj):
        return json.dumps(obj).encode("utf-8")

    def do_GET(self):
        if self.path != "/api/tags":
            self.send_response(404)
            self.end_headers()
            return
        raw = self._json({"models": [{"name": n} for n in type(self).tags]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))  # gövdeyi tüket
        type(self).request_count += 1
        if self.path != "/api/generate":
            self.send_response(404)
            self.end_headers()
            return
        if type(self).status != 200:
            raw = b"model not found"
            self.send_response(type(self).status)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        if type(self).raw_lines:
            for line in type(self).raw_lines:
                self.wfile.write((line + "\n").encode("utf-8"))
                self.wfile.flush()
            return
        for i, chunk in enumerate(type(self).chunks):
            if type(self).delay and i == len(type(self).chunks) - 1:
                time.sleep(type(self).delay)  # son parçayı geciktir -> okuma zaman aşımı
            self.wfile.write((json.dumps({"response": chunk, "done": False}) + "\n").encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b'{"response": "", "done": true}\n')
        self.wfile.flush()

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_ollama():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    _OllamaHandler.chunks, _OllamaHandler.delay = ["{}"], 0.0
    _OllamaHandler.raw_lines = []
    _OllamaHandler.status, _OllamaHandler.tags = 200, []
    _OllamaHandler.request_count = 0
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _OllamaHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    class Control:
        host = f"http://127.0.0.1:{port}"

        def set_response(self, text):
            """Yanıtı tek parça olarak ayarlar (JSON ayrıştırma testleri için)."""
            _OllamaHandler.chunks = [text]
            _OllamaHandler.raw_lines = []

        def set_stream(self, chunks, delay=0.0):
            """Yanıtı birden çok akış parçası olarak ayarlar."""
            _OllamaHandler.chunks = list(chunks)
            _OllamaHandler.raw_lines = []
            _OllamaHandler.delay = delay

        def set_raw_lines(self, lines):
            """Ham NDJSON satırları yazar (sunucu taraflı hata testi için)."""
            _OllamaHandler.raw_lines = list(lines)
            _OllamaHandler.delay = 0.0

        def set_status(self, code):
            _OllamaHandler.status = code

        def set_tags(self, names):
            _OllamaHandler.tags = list(names)

        def request_count(self):
            return _OllamaHandler.request_count

    control = Control()
    yield control
    server.shutdown()
    server.server_close()


def test_expand_query_parses_concepts(fake_ollama):
    fake_ollama.set_response(
        'Elbette: {"konu": "kıdem tazminatı", "kavramlar": ["kıdem tazminatı", "hak kazanma", "bir yıl"]}')
    result = ai_helper.expand_query("Soru metni", model="test", host=fake_ollama.host)
    assert result["konu"] == "kıdem tazminatı"
    assert result["kavramlar"] == ["kıdem tazminatı", "hak kazanma", "bir yıl"]


def test_expand_query_returns_none_on_garbage(fake_ollama):
    fake_ollama.set_response("bunu anlamadım")
    assert ai_helper.expand_query("Soru", model="test", host=fake_ollama.host) is None


def test_rank_by_relevance_sorts_by_ai_score(fake_ollama):
    fake_ollama.set_response('{"puanlar": {"0": 2, "1": 9, "2": 5}}')
    results = [
        {"document_name": "a.txt", "location": "Satır 1", "text": "alakasız"},
        {"document_name": "b.txt", "location": "Satır 2", "text": "tam ilgili"},
        {"document_name": "c.txt", "location": "Satır 3", "text": "kısmen"},
    ]
    ranked = ai_helper.rank_by_relevance("soru", results, model="test", host=fake_ollama.host)
    assert [r["document_name"] for r in ranked] == ["b.txt", "c.txt", "a.txt"]
    assert ranked[0]["ai_score"] == 9.0
    # Özgün sözlükler değiştirilmemeli
    assert "ai_score" not in results[0]


def test_rank_by_relevance_clamps_out_of_range_scores(fake_ollama):
    fake_ollama.set_response('{"puanlar": {"0": 99, "1": -5}}')
    results = [{"document_name": "a", "location": "1", "text": "x"},
               {"document_name": "b", "location": "2", "text": "y"}]
    ranked = ai_helper.rank_by_relevance("s", results, model="test", host=fake_ollama.host)
    assert ranked[0]["ai_score"] == 10.0
    assert ranked[1]["ai_score"] == 0.0


def test_rank_by_relevance_raises_on_unparsable(fake_ollama):
    fake_ollama.set_response("JSON yok")
    with pytest.raises(ai_helper.OllamaError):
        ai_helper.rank_by_relevance("s", [{"document_name": "a", "location": "1", "text": "x"}],
                                    model="test", host=fake_ollama.host)


def test_rank_by_relevance_empty_results_short_circuits(fake_ollama):
    assert ai_helper.rank_by_relevance("s", [], model="test", host=fake_ollama.host) == []


def test_rank_by_relevance_batches_requests(fake_ollama):
    """Çok aday tek istekte gönderilmemeli; zaman aşımını önlemek için gruplanır."""
    fake_ollama.set_response('{"puanlar": {"0": 5, "1": 5}}')
    results = [{"document_name": f"d{i}", "location": str(i), "text": "x"} for i in range(5)]
    ranked = ai_helper.rank_by_relevance("s", results, model="test", host=fake_ollama.host,
                                         batch_size=2)
    assert len(ranked) == 5
    assert fake_ollama.request_count() == 3  # 2 + 2 + 1


def test_rank_by_relevance_reports_progress(fake_ollama):
    fake_ollama.set_response('{"puanlar": {"0": 5, "1": 5}}')
    seen = []
    results = [{"document_name": f"d{i}", "location": str(i), "text": "x"} for i in range(4)]
    ai_helper.rank_by_relevance("s", results, model="test", host=fake_ollama.host,
                                batch_size=2, progress=lambda d, t: seen.append((d, t)))
    assert seen == [(2, 4), (4, 4)]


def test_streaming_assembles_multiple_ndjson_chunks(fake_ollama):
    """Akış protokolü: parçalar birleşip tek yanıt olmalı."""
    fake_ollama.set_stream(['{"konu": "kıdem tazminatı", "kavram', 'lar": ["hak", "yıl"]}'])
    result = ai_helper.expand_query("soru", model="test", host=fake_ollama.host)
    assert result["konu"] == "kıdem tazminatı"
    assert result["kavramlar"] == ["hak", "yıl"]


def test_server_side_error_in_stream_becomes_ollama_error(fake_ollama):
    fake_ollama.set_raw_lines(['{"error": "model requires more system memory"}'])
    with pytest.raises(ai_helper.OllamaError, match="system memory"):
        ai_helper.expand_query("soru", model="test", host=fake_ollama.host)


def test_timeout_is_reported_as_timeout_not_connection_error(fake_ollama):
    """Asıl şikâyet: zaman aşımı yanlışlıkla 'bağlanılamadı' diye gösteriliyordu."""
    fake_ollama.set_stream(["{"], delay=3)
    with pytest.raises(ai_helper.OllamaError) as info:
        ai_helper.expand_query("soru", model="test", host=fake_ollama.host, read_timeout=1)
    message = str(info.value)
    assert "zaman aşımı" in message
    assert "ulaşılamadı" not in message


def test_missing_server_is_reported_as_connection_error(fake_ollama):
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dead = s.getsockname()[1]
    with pytest.raises(ai_helper.OllamaError, match="ulaşılamadı"):
        ai_helper.expand_query("soru", model="test", host=f"http://127.0.0.1:{dead}")


def test_http_error_includes_model_hint(fake_ollama):
    fake_ollama.set_status(404)
    with pytest.raises(ai_helper.OllamaError, match="bulunamadı"):
        ai_helper.expand_query("soru", model="yokmodel", host=fake_ollama.host)


def test_explain_with_ollama_reports_streaming_progress(fake_ollama):
    """Not üretimi en uzun işlem; kullanıcı beklerken ilerleme görmeli."""
    fake_ollama.set_stream(["kıdem ", "tazminatı ", "notu"])
    seen = []
    answer = ai_helper.explain_with_ollama(
        "soru",
        [{"document_name": "a.txt", "location": "Satır 1", "text": "kıdem tazminatı metni"}],
        model="test", host=fake_ollama.host, progress=lambda n: seen.append(n))
    assert "kıdem tazminatı notu" in answer
    assert seen == [6, 16, 20]  # her parçadan sonra kümülatif karakter sayısı


def test_check_ollama_reports_missing_model(fake_ollama):
    fake_ollama.set_tags(["qwen2.5:3b"])
    status = ai_helper.check_ollama(model="yokmodel:1b", host=fake_ollama.host)
    assert status["ok"] and not status["model_present"]
    assert "ollama pull yokmodel:1b" in status["message"]


def test_check_ollama_accepts_matching_tag(fake_ollama):
    fake_ollama.set_tags(["qwen2.5:3b", "llama3.2:latest"])
    status = ai_helper.check_ollama(model="qwen2.5:3b", host=fake_ollama.host)
    assert status["ok"] and status["model_present"]
    assert status["message"] == ""


def test_check_ollama_reports_unreachable_server(fake_ollama):
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dead = s.getsockname()[1]
    status = ai_helper.check_ollama(model="x", host=f"http://127.0.0.1:{dead}")
    assert not status["ok"]
    assert "ulaşılamadı" in status["message"]
