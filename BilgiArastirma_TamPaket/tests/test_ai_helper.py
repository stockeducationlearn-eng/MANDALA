import http.server
import json
import socket
import threading

import pytest

import ai_helper


class _OllamaHandler(http.server.BaseHTTPRequestHandler):
    """Gerçek bir HTTP uç noktası; /api/generate isteklerini yanıtlar."""

    response_text = "{}"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)  # gövdeyi tüket
        if self.path != "/api/generate":
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps({"response": type(self).response_text}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_ollama():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _OllamaHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    class Control:
        host = f"http://127.0.0.1:{port}"

        def set_response(self, text):
            _OllamaHandler.response_text = text

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
    with pytest.raises(ValueError):
        ai_helper.rank_by_relevance("s", [{"document_name": "a", "location": "1", "text": "x"}],
                                    model="test", host=fake_ollama.host)


def test_rank_by_relevance_empty_results_short_circuits(fake_ollama):
    assert ai_helper.rank_by_relevance("s", [], model="test", host=fake_ollama.host) == []
