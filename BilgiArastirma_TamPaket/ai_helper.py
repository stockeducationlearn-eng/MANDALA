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


def _ollama_generate(prompt, model, host, temperature=0.2,
                     read_timeout=DEFAULT_READ_TIMEOUT, keep_alive=DEFAULT_KEEP_ALIVE,
                     progress=None):
    """Ollama'ya akışlı istek gönderir ve üretilen metni döndürür.

    Akış kullanmanın nedeni: `stream=False` isteğinde sunucu tüm yanıtı tek
    parçada gönderir, uzun bir üretimde okuma zaman aşımına takılır ve kullanıcı
    "bağlanılamadı" hatası görür (oysa bağlantı kurulmuştur). Akışta her parça
    ayrı geldiği için yavaş modellerde de istek tamamlanır; ayrıca ilerleme
    bildirilebilir.
    """
    url = f"{host.rstrip('/')}/api/generate"
    try:
        response = requests.post(
            url,
            json={"model": model, "prompt": prompt, "stream": True,
                  "keep_alive": keep_alive, "options": {"temperature": temperature}},
            timeout=(CONNECT_TIMEOUT, read_timeout), stream=True,
        )
        response.raise_for_status()
        pieces = []
        produced = 0
        for line in response.iter_lines():
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            error = payload.get("error")
            if error:
                raise OllamaError(f"Ollama hata döndürdü: {error}")
            piece = payload.get("response", "")
            if piece:
                pieces.append(piece)
                produced += len(piece)
                if progress:
                    progress(produced)
            if payload.get("done"):
                break
        return "".join(pieces).strip()
    except OllamaError:
        raise
    except Exception as exc:
        raise _classify(exc, host, model, read_timeout) from exc


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

Yalnızca JSON döndür, başka açıklama yazma:
{{"konu": "kısa konu adı", "kavramlar": ["kavram 1", "kavram 2", "kavram 3"]}}

En fazla 6 kavram yaz; her kavram 1-3 kelime olsun.

SORU:
{question}
"""
    raw = _ollama_generate(prompt, model, host, temperature=0.0,
                           read_timeout=read_timeout, keep_alive=keep_alive)
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    concepts = [str(c).strip() for c in data.get("kavramlar", []) if str(c).strip()]
    return {"konu": str(data.get("konu", "")).strip(), "kavramlar": concepts[:6]} or None


def _score_batch(question, batch, model, host, read_timeout, keep_alive):
    """Tek bir istekte bir grup parçayı puanlar; {indeks: puan} döndürür."""
    listing = "\n".join(
        f"[{i}] {r['document_name']} | {r['location']}\n{r['text'][:600]}"
        for i, r in enumerate(batch)
    )
    prompt = f"""Aşağıda bir soru ve kaynak parçaları verilmiştir. Her parçanın bu soruyla
ilgisini 0-10 arasında puanla (10 = soruyu doğrudan yanıtlıyor, 0 = ilgisiz).
Kelimeler aynı olmasa da anlam yakınsa yüksek puan ver.

Yalnızca JSON döndür, başka açıklama yazma:
{{"puanlar": {{"0": 7, "1": 2}}}}
Her parça için bir puan yaz. Puanlar 0-10 arası tam sayı olsun.

SORU:
{question}

KAYNAK PARÇALARI:
{listing}
"""
    raw = _ollama_generate(prompt, model, host, temperature=0.0,
                           read_timeout=read_timeout, keep_alive=keep_alive)
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise OllamaError("Model geçerli bir puan listesi döndürmedi.")
    try:
        return json.loads(match.group(0)).get("puanlar", {})
    except ValueError as exc:
        raise OllamaError("Model yanıtı JSON olarak çözümlenemedi.") from exc


def rank_by_relevance(question, results, model="qwen2.5:3b", host="http://localhost:11434",
                      max_candidates=30, batch_size=10,
                      read_timeout=DEFAULT_READ_TIMEOUT, keep_alive=DEFAULT_KEEP_ALIVE,
                      progress=None):
    """Aday parçaları, soruyla anlamsal ilgilerine göre puanlatır.

    Kelime eşleşmesinin yakalayamadığı durumlar (eşanlamlılar, farklı çekimler)
    burada yakalanır. Model "arayıcı" değil "jüri"dir: adaylar zaten kelime
    tabanlı aramayla getirilmiştir; model yalnızca sıralar.

    Puanlama küçük gruplar hâlinde yapılır; tek büyük istek yavaş donanımda
    zaman aşımına uğradığı için bu, isteği güvenilir kılar.
    """
    if not results:
        return []
    candidates = results[:max_candidates]
    scored = []
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start:start + batch_size]
        scores = _score_batch(question, batch, model, host, read_timeout, keep_alive)
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
    return scored


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
