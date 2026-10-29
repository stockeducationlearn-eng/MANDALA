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
    last_body = {}
    reject_json_format = False
    reject_embed = False
    sequence = []

    def _json(self, obj):
        return json.dumps(obj).encode("utf-8")

    def _vector(self, text):
        """Metne bağlı, deterministik bir vektör üretir.

        Testte benzerlik sırası denetlenebilsin diye kelime içerikleri
        vektöre yansıtılır: aynı kelimeleri paylaşan metinler yakın vektör alır.
        """
        words = [w for w in text.lower().split() if w]
        dims = 8
        vector = [0.0] * dims
        for word in words:
            vector[hash(word) % dims] += 1.0
        if not any(vector):
            vector[0] = 1.0
        return vector

    def _handle_embed(self):
        payload = type(self).last_body
        if self.path == "/api/embed":
            if type(self).reject_embed:
                self.send_response(404)
                self.end_headers()
                return
            texts = payload.get("input") or []
            if isinstance(texts, str):
                texts = [texts]
            raw = self._json({"embeddings": [self._vector(t) for t in texts]})
        else:
            raw = self._json({"embedding": self._vector(payload.get("prompt", ""))})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

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
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        type(self).last_body = json.loads(body or b"{}")
        type(self).request_count += 1
        if self.path in ("/api/embed", "/api/embeddings"):
            self._handle_embed()
            return
        if self.path != "/api/generate":
            self.send_response(404)
            self.end_headers()
            return
        if type(self).reject_json_format and type(self).last_body.get("format"):
            raw = b'{"error": "invalid format"}'
            self.send_response(400)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
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
        chunks = type(self).chunks
        seq = type(self).sequence
        if seq:
            chunks = [seq.pop(0) if len(seq) > 1 else seq[0]]
        for i, chunk in enumerate(chunks):
            if type(self).delay and i == len(chunks) - 1:
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
    _OllamaHandler.reject_json_format = False
    _OllamaHandler.reject_embed = False
    _OllamaHandler.sequence = []
    _OllamaHandler.request_count = 0
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _OllamaHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    class Control:
        host = f"http://127.0.0.1:{port}"

        def set_response(self, text):
            """Yanıtı tek parça olarak ayarlar (JSON ayrıştırma testleri için)."""
            _OllamaHandler.chunks = [text]
            _OllamaHandler.raw_lines = []
            _OllamaHandler.sequence = []

        def set_stream(self, chunks, delay=0.0):
            """Yanıtı birden çok akış parçası olarak ayarlar."""
            _OllamaHandler.chunks = list(chunks)
            _OllamaHandler.raw_lines = []
            _OllamaHandler.sequence = []
            _OllamaHandler.delay = delay

        def set_raw_lines(self, lines):
            """Ham NDJSON satırları yazar (sunucu taraflı hata testi için)."""
            _OllamaHandler.raw_lines = list(lines)
            _OllamaHandler.sequence = []
            _OllamaHandler.delay = 0.0

        def set_status(self, code):
            _OllamaHandler.status = code

        def set_tags(self, names):
            _OllamaHandler.tags = list(names)

        def reject_format(self):
            """Eski Ollama gibi davran: format alanını 400 ile reddet."""
            _OllamaHandler.reject_json_format = True

        def legacy_embed_only(self):
            """/api/embed'i 404 yap; yalnızca /api/embeddings çalışsın."""
            _OllamaHandler.reject_embed = True

        def set_sequence(self, responses):
            """Sırayla farklı yanıtlar döndür (son yanıt tekrarlanır)."""
            _OllamaHandler.sequence = list(responses)

        def request_count(self):
            return _OllamaHandler.request_count

        def last_payload(self):
            return _OllamaHandler.last_body

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


def test_score_batch_raises_on_unparsable(fake_ollama):
    """Tek parti düzeyinde çözümlenemeyen yanıt hata olarak bildirilir."""
    fake_ollama.set_response("JSON yok")
    with pytest.raises(ai_helper.OllamaError):
        ai_helper._score_batch("s", [{"document_name": "a", "location": "1", "text": "x"}],
                               "test", fake_ollama.host, 300, "30m")


def test_rank_by_relevance_degrades_instead_of_raising(fake_ollama):
    """Arama düzeyinde bozuk yanıt istisna değil, puansız sonuç üretir."""
    fake_ollama.set_response("JSON yok")
    ranked = ai_helper.rank_by_relevance(
        "s", [{"document_name": "a", "location": "1", "text": "x"}],
        model="test", host=fake_ollama.host)
    assert len(ranked) == 1
    assert ranked[0]["ai_score"] is None


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


# --- JSON ayrıştırma sağlamlığı ------------------------------------------
# Şikâyet: küçük modeller geçerli JSON döndürmediği için "JSON olarak
# çözümlenemedi" hatası alınıyordu. Aşağıdaki biçimlerin tümü kabul edilmeli.

@pytest.mark.parametrize("raw", [
    '{"puanlar": {"0": 7, "1": 2}}',
    '```json\n{"puanlar": {"0": 7, "1": 2}}\n```',
    '```\n{"puanlar": {"0": 7, "1": 2}}\n```',
    'Elbette! {"puanlar": {"0": 7, "1": 2}} Umarım yardımcı olur.',
    "İşte sonuç:\n{'puanlar': {'0': 7, '1': 2}}\n",
    '{"puanlar": {"0": 7, "1": 2,}}',
    'Asagidaki {soru} icin: {"puanlar": {"0": 7, "1": 2}}',
    '{"puanlar": {"0": 7, "1": 2',
])
def test_score_parsing_survives_common_model_outputs(fake_ollama, raw):
    fake_ollama.set_response(raw)
    ranked = ai_helper.rank_by_relevance(
        "s", [{"document_name": "a", "location": "1", "text": "x"},
              {"document_name": "b", "location": "2", "text": "y"}],
        model="test", host=fake_ollama.host)
    assert [r["ai_score"] for r in ranked] == [7.0, 2.0]


def test_score_parsing_accepts_list_form(fake_ollama):
    """Model sözlük yerine liste döndürürse de çalışmalı."""
    fake_ollama.set_response('{"puanlar": [7, 2]}')
    ranked = ai_helper.rank_by_relevance(
        "s", [{"document_name": "a", "location": "1", "text": "x"},
              {"document_name": "b", "location": "2", "text": "y"}],
        model="test", host=fake_ollama.host)
    assert [r["ai_score"] for r in ranked] == [7.0, 2.0]


def test_score_parsing_keeps_apostrophe_in_content(fake_ollama):
    """Tek tırnak onarımı metin içi kesme işaretini bozmamalı."""
    fake_ollama.set_response('{"puanlar": {"0": 5, "1": 3}}')
    ranked = ai_helper.rank_by_relevance(
        "s", [{"document_name": "İşçi'nin", "location": "1", "text": "x"},
              {"document_name": "b", "location": "2", "text": "y"}],
        model="test", host=fake_ollama.host)
    assert [r["ai_score"] for r in ranked] == [5.0, 3.0]


def test_expand_query_survives_markdown_and_prose(fake_ollama):
    fake_ollama.set_response(
        'Tabii:\n```json\n{"konu": "kıdem", "kavramlar": ["kıdem tazminatı", "hak"]}\n```')
    result = ai_helper.expand_query("soru", model="test", host=fake_ollama.host)
    assert result["konu"] == "kıdem"
    assert result["kavramlar"] == ["kıdem tazminatı", "hak"]


def test_expand_query_accepts_single_string_concept(fake_ollama):
    fake_ollama.set_response('{"konu": "x", "kavramlar": "kıdem tazminatı"}')
    result = ai_helper.expand_query("soru", model="test", host=fake_ollama.host)
    assert result["kavramlar"] == ["kıdem tazminatı"]


def test_expand_query_returns_none_when_no_json_at_all(fake_ollama):
    fake_ollama.set_response("Yalnızca düz metin, hiç JSON yok.")
    assert ai_helper.expand_query("soru", model="test", host=fake_ollama.host) is None


def test_json_mode_is_requested_for_structured_calls(fake_ollama):
    """Ollama'nın format='json' kısıtı, yapısal çağrılarda istenmeli."""
    fake_ollama.set_response('{"konu": "x", "kavramlar": ["y"]}')
    ai_helper.expand_query("soru", model="test", host=fake_ollama.host)
    assert fake_ollama.last_payload().get("format") == "json"


def test_free_text_call_does_not_force_json(fake_ollama):
    """Not üretimi serbest metin; JSON kısıtı dayatılmamalı."""
    fake_ollama.set_stream(["düz metin yanıt"])
    ai_helper.explain_with_ollama(
        "s", [{"document_name": "a", "location": "1", "text": "t"}],
        model="test", host=fake_ollama.host)
    assert "format" not in fake_ollama.last_payload()


def test_json_mode_falls_back_when_server_rejects_format(fake_ollama):
    """format='json' desteklemeyen eski Ollama'da kısıtsız yeniden denenmeli."""
    fake_ollama.reject_format()
    fake_ollama.set_response('{"konu": "x", "kavramlar": ["y"]}')
    result = ai_helper.expand_query("soru", model="test", host=fake_ollama.host)
    assert result["kavramlar"] == ["y"]
    assert fake_ollama.request_count() == 2  # önce format'lı, sonra kısıtsız
    assert "format" not in fake_ollama.last_payload()


# --- Parti dayanıklılığı --------------------------------------------------

def _candidates(n):
    return [{"document_name": f"d{i}", "location": str(i), "text": f"metin {i}"}
            for i in range(n)]


def test_failed_batch_is_retried_once(fake_ollama):
    """Tek bozuk yanıt tüm aramayı düşürmemeli; parti bir kez yeniden denenir."""
    fake_ollama.set_sequence(["bu JSON değil", '{"puanlar": {"0": 6, "1": 4}}'])
    ranked = ai_helper.rank_by_relevance("s", _candidates(2), model="test",
                                         host=fake_ollama.host, batch_size=2)
    assert [r["ai_score"] for r in ranked] == [6.0, 4.0]
    assert fake_ollama.request_count() == 2  # ilk deneme + yeniden deneme


def test_unparseable_batch_does_not_abort_whole_search(fake_ollama):
    """İkinci parti hiç çözümlenemezse ilk partinin sonuçları korunur."""
    fake_ollama.set_sequence([
        '{"puanlar": {"0": 8, "1": 1}}',   # 1. parti (2 deneme)
        "bozuk", "bozuk",                   # 2. parti (2 deneme, ikisi de bozuk)
    ])
    warnings = []
    ranked = ai_helper.rank_by_relevance("s", _candidates(4), model="test",
                                         host=fake_ollama.host, batch_size=2,
                                         on_warning=warnings.append)
    assert len(ranked) == 4
    scored = [r for r in ranked if r["ai_score"] is not None]
    unscored = [r for r in ranked if r["ai_score"] is None]
    assert [r["ai_score"] for r in scored] == [8.0, 1.0]
    assert len(unscored) == 2
    # Puanlananlar önce gelmeli, puanlanamayanlar sonda
    assert ranked[0]["ai_score"] == 8.0
    assert warnings and "puanlanamadı" in warnings[0]


def test_unscored_results_keep_original_order(fake_ollama):
    fake_ollama.set_sequence(["bozuk"])
    ranked = ai_helper.rank_by_relevance("s", _candidates(3), model="test",
                                         host=fake_ollama.host, batch_size=1)
    assert [r["document_name"] for r in ranked] == ["d0", "d1", "d2"]
    assert all(r["ai_score"] is None for r in ranked)


# --- Gömme (embedding) ile hızlı sıralama ---------------------------------

def test_embed_texts_uses_batch_endpoint(fake_ollama):
    vectors = ai_helper.embed_texts(["kıdem tazminatı", "şeker hastalığı"],
                                    model="test", host=fake_ollama.host)
    assert len(vectors) == 2
    assert fake_ollama.request_count() == 1          # tek toplu istek
    assert fake_ollama.last_payload().get("input")


def test_rank_by_embedding_orders_by_similarity(fake_ollama):
    """Soruyla kelime paylaşan parça, paylaşmayanın önüne geçmeli."""
    results = [
        {"document_name": "alakasiz", "location": "1", "text": "şeker hastalığı tedavisi"},
        {"document_name": "ilgili", "location": "2", "text": "kıdem tazminatı hak"},
    ]
    ranked = ai_helper.rank_by_embedding("kıdem tazminatı", results,
                                         model="test", host=fake_ollama.host)
    assert ranked[0]["document_name"] == "ilgili"
    assert ranked[0]["ai_score"] > ranked[1]["ai_score"]


def test_rank_by_embedding_reports_progress(fake_ollama):
    seen = []
    ai_helper.rank_by_embedding("soru", _candidates(3), model="test",
                                host=fake_ollama.host, progress=seen.append)
    assert seen == [4]   # soru + 3 aday tek istekte vektörlendi


def test_rank_by_embedding_empty_results(fake_ollama):
    assert ai_helper.rank_by_embedding("s", [], model="test", host=fake_ollama.host) == []


def test_embed_falls_back_to_legacy_endpoint(fake_ollama):
    """Eski Ollama /api/embed yerine tek tek /api/embeddings bekler."""
    fake_ollama.legacy_embed_only()
    vectors = ai_helper.embed_texts(["bir", "iki"], model="test", host=fake_ollama.host)
    assert len(vectors) == 2
    assert fake_ollama.request_count() == 3   # 1 başarısız + 2 tek tek


# --- Puan süzgeci ---------------------------------------------------------

def test_filter_by_score_drops_zero_and_unscored():
    results = [{"ai_score": 9.0}, {"ai_score": 3.0}, {"ai_score": 0.0},
               {"ai_score": None}, {"ai_score": 2.9}]
    kept = ai_helper.filter_by_score(results, min_score=3.0)
    assert [r["ai_score"] for r in kept] == [9.0, 3.0]


def test_filter_by_score_default_hides_zeros():
    results = [{"ai_score": 0.0}, {"ai_score": 7.0}]
    assert [r["ai_score"] for r in ai_helper.filter_by_score(results)] == [7.0]
