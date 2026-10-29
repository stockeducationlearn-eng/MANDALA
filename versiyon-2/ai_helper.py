import json
import re

import requests

# Bağlantı kurma kısa, yanıt bekleme uzun olabilir; bu yüzden ayrı zaman aşımları
# kullanılır. Akışlı (stream) istekte okuma zaman aşımı her parça için geçerlidir,
# yani model yavaş üretse de toplam süre sınırsız kalır.
CONNECT_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 300
DEFAULT_KEEP_ALIVE = "30m"


class OllamaError(RuntimeError):
    """Ollama isteği başarısız oldu; kullanıcıya gösterilecek Türkçe mesaj taşır."""


def _classify(exc, host, model, read_timeout):
    """Alt seviye istisnayı, kullanıcının ne yapacağını anlatan mesaja çevirir."""
    text = str(exc)
    if isinstance(exc, requests.exceptions.HTTPError):
        status = getattr(exc.response, "status_code", "?")
        detail = ""
        try:
            detail = (exc.response.text or "")[:300]
        except Exception:
            pass
        hint = ""
        if status == 404:
            hint = f"\n'{model}' modeli bulunamadı. 'ollama pull {model}' ile indirin."
        return OllamaError(f"Ollama isteği reddedildi (HTTP {status}).{hint}\nAyrıntı: {detail}")
    if isinstance(exc, requests.exceptions.Timeout) or "timed out" in text.lower():
        return OllamaError(
            f"Model {read_timeout} saniye içinde yanıt üretemedi (zaman aşımı).\n"
            "Ollama çalışıyor, ancak yanıt yetişmedi. Şunları deneyin:\n"
            "• Daha küçük/hızlı bir model kullanın (ör. qwen2.5:1.5b veya llama3.2:3b).\n"
            "• Ayarlar > 'Ollama yanıt süresi (sn)' değerini artırın.\n"
            "• İlk çağrı modeli belleğe yükler ve yavaştır; ikinci deneme genelde hızlı olur.\n"
            "• Model belleğe sığmıyorsa sürekli diskten yüklenir; daha küçük model seçin."
        )
    if isinstance(exc, requests.exceptions.ConnectionError):
        return OllamaError(
            f"Ollama sunucusuna ulaşılamadı ({host}).\n"
            "Ollama kurulu ve çalışıyor mu? Kurulumdan sonra 'ollama serve' komutunu "
            "veya Ollama uygulamasını başlatın."
        )
    return OllamaError(f"Ollama isteği başarısız oldu: {text}")


def _stream_generate(url, payload, read_timeout, progress):
    """Akışlı isteği gönderir ve üretilen metni birleştirir."""
    response = requests.post(
        url, json=payload,
        timeout=(CONNECT_TIMEOUT, read_timeout), stream=True,
    )
    response.raise_for_status()
    pieces = []
    produced = 0
    for line in response.iter_lines():
        if not line:
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        error = data.get("error")
        if error:
            raise OllamaError(f"Ollama hata döndürdü: {error}")
        piece = data.get("response", "")
        if piece:
            pieces.append(piece)
            produced += len(piece)
            if progress:
                progress(produced)
        if data.get("done"):
            break
    return "".join(pieces).strip()


def _ollama_generate(prompt, model, host, temperature=0.2,
                     read_timeout=DEFAULT_READ_TIMEOUT, keep_alive=DEFAULT_KEEP_ALIVE,
                     progress=None, json_mode=False):
    """Ollama'ya akışlı istek gönderir ve üretilen metni döndürür.

    Akış kullanmanın nedeni: `stream=False` isteğinde sunucu tüm yanıtı tek
    parçada gönderir, uzun bir üretimde okuma zaman aşımına takılır ve kullanıcı
    "bağlanılamadı" hatası görür (oysa bağlantı kurulmuştur). Akışta her parça
    ayrı geldiği için yavaş modellerde de istek tamamlanır; ayrıca ilerleme
    bildirilebilir.

    `json_mode=True` iken Ollama'nın `format="json"` kısıtı kullanılır; küçük
    modeller düz metin içine gömülü JSON üretmeye çalışsa da sunucu geçerli JSON
    üretmeye zorlanır. Alanı desteklemeyen eski Ollama sürümleri 400 döndürürse
    kısıt olmadan bir kez daha denenir.
    """
    url = f"{host.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": True,
               "keep_alive": keep_alive, "options": {"temperature": temperature}}
    if json_mode:
        payload["format"] = "json"
    try:
        try:
            return _stream_generate(url, payload, read_timeout, progress)
        except requests.exceptions.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if json_mode and status in (400, 404):
                payload.pop("format", None)  # eski Ollama: kısıtsız yeniden dene
                return _stream_generate(url, payload, read_timeout, progress)
            raise
    except OllamaError:
        raise
    except Exception as exc:
        raise _classify(exc, host, model, read_timeout) from exc


def _balanced_regions(text):
    """Metindeki dengeli `{...}` ve `[...]` bölgelerini (uzundan kısaya) döndürür."""
    regions = []
    for opener, closer in (("{", "}"), ("[", "]")):
        stack = []
        in_string = False
        escaped = False
        for i, ch in enumerate(text):
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == opener:
                stack.append(i)
            elif ch == closer and stack:
                start = stack.pop()
                regions.append(text[start:i + 1])
    regions.sort(key=len, reverse=True)
    return regions


def _repair_json(text):
    """Küçük modellerin yaygın JSON hatalarını onarır (tırnak, sondaki virgül, kesik)."""
    fixed = text
    # Tek tırnaklı JSON: kelime içi kesme işaretini (İşçi'nin) koruyarak çevir.
    if '"' not in fixed and "'" in fixed:
        fixed = re.sub(r"(?<=\w)'(?=\w)", "\u2019", fixed)
        fixed = fixed.replace("'", '"')
        fixed = fixed.replace("\u2019", "'")
    # Sondaki virgüller: {"a": 1,} -> {"a": 1}
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
    # Python/JS kalıntıları: None/True/False
    fixed = re.sub(r"\bNone\b", "null", fixed)
    fixed = re.sub(r"\bTrue\b", "true", fixed)
    fixed = re.sub(r"\bFalse\b", "false", fixed)
    return fixed


def _extract_json(raw):
    """Serbest model metninden JSON değerini çıkarır; bulamazsa None.

    Model yanıtı çoğu zaman saf JSON olmaz: markdown kod bloğu, öncesinde/
    sonrasında açıklama, tek tırnak veya sondaki virgül içerebilir. Sıra:
    kod bloğu -> doğrudan ayrıştırma -> dengeli bölge taraması -> onarım.
    """
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.S | re.I)
    texts = ([fence.group(1)] if fence else []) + [raw]
    for text in texts:
        stripped = text.strip()
        for candidate in (stripped, _repair_json(stripped)):
            try:
                return json.loads(candidate)
            except ValueError:
                pass
        for region in _balanced_regions(stripped):
            for candidate in (region, _repair_json(region)):
                try:
                    return json.loads(candidate)
                except ValueError:
                    pass
    # Kesik yanıt: eksik kapanışları ekleyerek son bir deneme.
    for text in texts:
        closed = _repair_json(text.strip())
        for _ in range(4):
            closed += "}" if closed.count("{") > closed.count("}") else "]"
            try:
                return json.loads(closed)
            except ValueError:
                continue
    return None


def _as_score_map(data):
    """Model yanıtını {indeks: puan} sözlüğüne normalleştirir.

    Model `puanlar` alanını sözlük yerine liste olarak döndürebilir; her iki
    biçim de kabul edilir.
    """
    if not isinstance(data, dict):
        return {}
    scores = data.get("puanlar", data)
    if isinstance(scores, list):
        return {str(i): v for i, v in enumerate(scores)}
    if isinstance(scores, dict):
        return scores
    return {}


def check_ollama(host="http://localhost:11434", model=None, timeout=5):
    """Ollama erişilebilir mi ve istenen model yüklü mü? Hata yükseltmez.

    Uzun bir isteğe başlamadan önce hızlı bir ön kontrol yapmak, kullanıcıyı
    dakikalarca bekletip sonunda hata görmekten kurtarır.
    """
    try:
        response = requests.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
        response.raise_for_status()
        names = [m.get("name", "") for m in response.json().get("models", [])]
    except Exception:
        return {"ok": False, "model_present": False, "models": [],
                "message": f"Ollama sunucusuna ulaşılamadı ({host}).\n"
                           "Ollama kurulu ve çalışıyor mu? 'ollama serve' komutunu deneyin."}
    if model:
        base = model.split(":")[0]
        if not any(n == model or n.split(":")[0] == base for n in names):
            return {"ok": True, "model_present": False, "models": names,
                    "message": f"'{model}' modeli yüklü görünmüyor.\n"
                               f"İndirmek için: ollama pull {model}\n"
                               f"Yüklü modeller: {', '.join(names) if names else 'yok'}"}
    return {"ok": True, "model_present": True, "models": names, "message": ""}


def expand_query(question, model="qwen2.5:3b", host="http://localhost:11434",
                 read_timeout=DEFAULT_READ_TIMEOUT, keep_alive=DEFAULT_KEEP_ALIVE):
    """Soru metnini, kaynakta aranacak kısa anahtar kavramlara indirir.

    Sınav sorularında seçenekler birbirinin çeldiricisidir; hepsini birlikte
    aramak doğru kaynağı bulmayı zorlaştırır. Modelden yalnızca sorunun ölçtüğü
    konuyu istemek, arama sorgusunu temizler.
    """
    prompt = f"""Aşağıdaki sınav sorusunu incele. Sorunun ölçtüğü konuyu ve cevap için
aranması gereken anahtar kavramları çıkar. Seçeneklerdeki çeldirici ayrıntıları YOK SAY.

Yanıtı yalnızca şu şemada JSON olarak ver:
{{"konu": "kısa konu adı", "kavramlar": ["kavram 1", "kavram 2", "kavram 3"]}}

En fazla 6 kavram yaz; her kavram 1-3 kelime olsun.

SORU:
{question}
"""
    raw = _ollama_generate(prompt, model, host, temperature=0.0,
                           read_timeout=read_timeout, keep_alive=keep_alive, json_mode=True)
    data = _extract_json(raw)
    if not isinstance(data, dict):
        return None
    raw_concepts = data.get("kavramlar") or data.get("kavram") or []
    if isinstance(raw_concepts, str):
        raw_concepts = [raw_concepts]
    concepts = [str(c).strip() for c in raw_concepts if str(c).strip()]
    konu = data.get("konu") or data.get("konu_adi") or ""
    if not concepts and not konu:
        return None
    return {"konu": str(konu).strip(), "kavramlar": concepts[:6]}


def _score_batch(question, batch, model, host, read_timeout, keep_alive):
    """Tek bir istekte bir grup parçayı puanlar; {indeks: puan} döndürür."""
    listing = "\n\n".join(
        f"[{i}] {r['document_name']} — {r['location']}\n{r['text'][:600]}"
        for i, r in enumerate(batch)
    )
    prompt = f"""Aşağıda bir soru ve kaynak parçaları verilmiştir. Her parçanın bu soruyla
ilgisini 0-10 arasında puanla (10 = soruyu doğrudan yanıtlıyor, 0 = ilgisiz).
Kelimeler aynı olmasa da anlam yakınsa yüksek puan ver.

Yanıtı yalnızca şu şemada JSON olarak ver:
{{"puanlar": {{"0": 7, "1": 2}}}}
Her parça için bir puan yaz. Puanlar 0-10 arası tam sayı olsun.

SORU:
{question}

KAYNAK PARÇALARI:
{listing}
"""
    raw = _ollama_generate(prompt, model, host, temperature=0.0,
                           read_timeout=read_timeout, keep_alive=keep_alive, json_mode=True)
    scores = _as_score_map(_extract_json(raw))
    if not scores:
        raise OllamaError("Model geçerli bir puan listesi döndürmedi.")
    return scores


def rank_by_relevance(question, results, model="qwen2.5:3b", host="http://localhost:11434",
                      max_candidates=30, batch_size=10,
                      read_timeout=DEFAULT_READ_TIMEOUT, keep_alive=DEFAULT_KEEP_ALIVE,
                      progress=None, on_warning=None):
    """Aday parçaları, soruyla anlamsal ilgilerine göre puanlatır.

    Kelime eşleşmesinin yakalayamadığı durumlar (eşanlamlılar, farklı çekimler)
    burada yakalanır. Model "arayıcı" değil "jüri"dir: adaylar zaten kelime
    tabanlı aramayla getirilmiştir; model yalnızca sıralar.

    Puanlama küçük gruplar hâlinde yapılır; tek büyük istek yavaş donanımda
    zaman aşımına uğradığı için bu, isteği güvenilir kılar. Bir parti
    çözümlenemezse bir kez yeniden denenir, yine olmazsa o parti atlanır:
    tek bir bozuk yanıt tüm aramayı düşürmemelidir.
    """
    if not results:
        return []
    candidates = results[:max_candidates]
    scored = []
    unscored = []
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start:start + batch_size]
        scores = None
        for attempt in (1, 2):
            try:
                scores = _score_batch(question, batch, model, host, read_timeout, keep_alive)
                break
            except OllamaError as exc:
                if attempt == 2:
                    if on_warning:
                        on_warning(f"{len(batch)} parça puanlanamadı ({exc})")
                    for r in batch:
                        item = dict(r)
                        item["ai_score"] = None
                        unscored.append(item)
        if scores is not None:
            for offset, r in enumerate(batch):
                try:
                    value = float(scores.get(str(offset), 0))
                except (TypeError, ValueError):
                    value = 0.0
                item = dict(r)
                item["ai_score"] = max(0.0, min(10.0, value))
                scored.append(item)
        if progress:
            progress(min(start + batch_size, len(candidates)), len(candidates))
    scored.sort(key=lambda r: r["ai_score"], reverse=True)
    # Puanlanamayanlar, puanlananların ardında özgün sıralarını korur.
    return scored + unscored


def embed_texts(texts, model="nomic-embed-text", host="http://localhost:11434",
                read_timeout=DEFAULT_READ_TIMEOUT, progress=None):
    """Metinleri vektöre çevirir (Ollama `/api/embed`).

    Gömme üretimi, metin üretiminden çok daha hızlıdır: model tek geçişte
    vektör verir, token token yanıt üretmez. Bu yüzden anlamsal sıralama için
    puanlama istemek yerine benzerlik ölçmek tercih edilir.

    Yeni Ollama sürümleri `/api/embed` ile toplu girdi kabul eder; eski
    sürümlerde `/api/embeddings` tek tek çağrılır.
    """
    texts = list(texts)
    if not texts:
        return []
    url = f"{host.rstrip('/')}/api/embed"
    try:
        try:
            response = requests.post(
                url, json={"model": model, "input": texts},
                timeout=(CONNECT_TIMEOUT, read_timeout),
            )
            response.raise_for_status()
            vectors = response.json().get("embeddings")
            if not vectors:
                raise OllamaError("Gömme modeli vektör döndürmedi.")
            if progress:
                progress(len(texts))
            return vectors
        except requests.exceptions.HTTPError as exc:
            if getattr(exc.response, "status_code", None) not in (400, 404):
                raise
            # Eski Ollama: tek tek /api/embeddings
            legacy = f"{host.rstrip('/')}/api/embeddings"
            vectors = []
            for i, text in enumerate(texts, 1):
                resp = requests.post(legacy, json={"model": model, "prompt": text},
                                     timeout=(CONNECT_TIMEOUT, read_timeout))
                resp.raise_for_status()
                vectors.append(resp.json().get("embedding") or [])
                if progress:
                    progress(i)
            if not any(vectors):
                raise OllamaError("Gömme modeli vektör döndürmedi.")
            return vectors
    except OllamaError:
        raise
    except Exception as exc:
        raise _classify(exc, host, model, read_timeout) from exc


def _cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def rank_by_embedding(question, results, model="nomic-embed-text",
                      host="http://localhost:11434", max_candidates=60,
                      read_timeout=DEFAULT_READ_TIMEOUT, progress=None):
    """Adayları gömme benzerliğine göre sıralar (üretim yapmadan, hızlı).

    Metin üretimi yerine vektör karşılaştırması kullanıldığı için tek bir
    istek yeter ve yanıt saniyeler içinde gelir. `ai_score` 0-10 aralığına
    ölçeklenmiş kosinüs benzerliğidir.
    """
    if not results:
        return []
    candidates = results[:max_candidates]
    vectors = embed_texts([question] + [r["text"][:2000] for r in candidates],
                          model=model, host=host, read_timeout=read_timeout,
                          progress=progress)
    if len(vectors) < len(candidates) + 1:
        raise OllamaError("Gömme sayısı aday sayısıyla uyuşmuyor.")
    question_vector = vectors[0]
    scored = []
    for r, vector in zip(candidates, vectors[1:]):
        similarity = _cosine(question_vector, vector)
        item = dict(r)
        item["ai_score"] = round(max(0.0, min(1.0, similarity)) * 10, 1)
        scored.append(item)
    scored.sort(key=lambda r: r["ai_score"], reverse=True)
    return scored


def filter_by_score(results, min_score=3.0):
    """Puanı eşiğin altında kalan sonuçları eler.

    Akıllı aramada model her adaya bir puan verir; ilgisiz parçalar 0 alır.
    Bunları göstermek listeyi doldurup asıl ilgili kaynağı gizlediği için
    varsayılan olarak elenir. Puanlanamayan (None) sonuçlar da gösterilmez.
    """
    kept = [r for r in results if (r.get("ai_score") or 0.0) >= min_score]
    return kept


def explain_with_ollama(question, results, model="qwen2.5:3b", host="http://localhost:11434",
                        mode="Otomatik", read_timeout=DEFAULT_READ_TIMEOUT,
                        keep_alive=DEFAULT_KEEP_ALIVE, progress=None):
    if not results:
        return "İlgili kaynak bulunamadı. Bu nedenle kaynaklara dayalı not oluşturulamadı."
    # İlk sıralardaki sonuçlara ek olarak, mümkün olduğunca farklı kaynaklardan parçalar seç.
    selected = []
    seen = set()
    per_document = {}
    for r in results:
        doc = r.get("document_name", "Bilinmeyen kaynak")
        key = (doc, r.get("location", ""), r.get("text", "")[:160])
        if key in seen or per_document.get(doc, 0) >= 5:
            continue
        seen.add(key)
        per_document[doc] = per_document.get(doc, 0) + 1
        selected.append(r)
        if len(selected) >= 18:
            break
    source_text = []
    source_index = []
    for i, r in enumerate(selected, 1):
        label = f"[Kaynak {i}] Dosya: {r['document_name']} | Konum: {r['location']}"
        source_text.append(label + "\n" + r['text'][:2200])
        source_index.append(f"[Kaynak {i}] {r['document_name']} — {r['location']}")
    mode_instructions = {
        "Çıkmış soru": "Sorunun kökünü ve tüm seçeneklerini birlikte değerlendir. Ölçülen konuyu belirle; doğru cevabı kaynaklar destekliyorsa açıkla, seçenekleri kaynaklar desteklediği ölçüde değerlendir. Kaynaklar olmadan cevap anahtarı uydurma.",
        "Paragraf / metin": "Metnin ana fikrini, önemli iddialarını, şartlarını, istisnalarını ve ilişkili kavramlarını çıkar; kaynaklardaki tamamlayıcı bilgileri bir araya getir.",
        "Kavram": "Kavramın kaynaklarda geçtiği farklı bağlamları birleştir; tanım, kapsam, türler, şartlar, istisnalar ve ilişkili kavramları ayır. Aynı bilgiyi gereksiz tekrar etme.",
        "Otomatik": "Girdinin bir sınav sorusu, paragraf veya kavram olup olmadığını belirle ve uygun analiz biçimini uygula."
    }.get(mode, "Girdiyi uygun biçimde analiz et.")
    prompt = f"""Sen kaynak temelli bir Türkçe araştırma ve sınav çalışma yardımcısısın.
ÖNCELİKLE VE YALNIZCA aşağıda verilen kaynak parçalarını kullan. Genel bilgini kaynakta olmayan olguları eklemek için kullanma.
Kaynaklarda bulunmayan bir bilgi için açıkça 'Verilen kaynak parçalarında doğrulanamadı' de. Kaynak etiketi, belge adı veya sayfa/konum uydurma.

Çalışma modu: {mode}
Yöntem: {mode_instructions}

Aşağıdaki başlıklarla düzenli ve öğretici bir not oluştur:
1. Konunun kısa özeti
2. Ayrıntılı açıklama ve temel kavramlar
3. Şartlar, türler, istisnalar ve önemli ayrımlar (kaynakta varsa)
4. Sınavda dikkat edilecek noktalar / olası çeldiriciler (yalnızca kaynakların desteklediği ölçüde)
5. Kaynaklara dayalı sonuç
6. Kaynakça: her kaynak etiketiyle birlikte dosya adı ve konum

Her önemli iddiadan sonra ilgili [Kaynak N] etiketini yaz. Kaynaklar çelişiyorsa bunu belirt; sessizce birini doğru kabul etme. Kaynak parçalarının sınırları nedeniyle eksik kalabilecek hususları açıkla. Türkçe yaz.

KULLANICININ GİRDİSİ:
{question}

KAYNAK PARÇALARI:
{chr(10).join(source_text)}
"""
    answer = _ollama_generate(prompt, model, host, temperature=0.2,
                              read_timeout=read_timeout, keep_alive=keep_alive,
                              progress=progress)
    return answer + "\n\n--- KULLANILAN KAYNAKLAR ---\n" + "\n".join(source_index)
