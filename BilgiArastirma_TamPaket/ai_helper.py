import json
import re

import requests

_OLLAMA_TIMEOUT = 600


def _ollama_generate(prompt, model, host, temperature=0.2, timeout=_OLLAMA_TIMEOUT):
    response = requests.post(
        f"{host.rstrip('/')}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False,
              "options": {"temperature": temperature}},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def expand_query(question, model="qwen2.5:3b", host="http://localhost:11434"):
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
    raw = _ollama_generate(prompt, model, host, temperature=0.0, timeout=180)
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    concepts = [str(c).strip() for c in data.get("kavramlar", []) if str(c).strip()]
    return {"konu": str(data.get("konu", "")).strip(), "kavramlar": concepts[:6]} or None


def rank_by_relevance(question, results, model="qwen2.5:3b", host="http://localhost:11434",
                      max_candidates=40):
    """Aday parçaları, soruyla anlamsal ilgilerine göre puanlatır.

    Kelime eşleşmesinin yakalayamadığı durumlar (eşanlamlılar, farklı çekimler)
    burada yakalanır. Model "arayıcı" değil "jüri"dir: adaylar zaten kelime
    tabanlı aramayla getirilmiştir; model yalnızca sıralar.
    """
    if not results:
        return []
    candidates = results[:max_candidates]
    listing = "\n".join(
        f"[{i}] {r['document_name']} | {r['location']}\n{r['text'][:700]}"
        for i, r in enumerate(candidates)
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
    raw = _ollama_generate(prompt, model, host, temperature=0.0)
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("Model geçerli bir puan listesi döndürmedi.")
    try:
        scores = json.loads(match.group(0)).get("puanlar", {})
    except ValueError as exc:
        raise ValueError("Model yanıtı JSON olarak çözümlenemedi.") from exc
    ranked = []
    for i, r in enumerate(candidates):
        try:
            score = float(scores.get(str(i), 0))
        except (TypeError, ValueError):
            score = 0.0
        item = dict(r)
        item["ai_score"] = max(0.0, min(10.0, score))
        ranked.append(item)
    ranked.sort(key=lambda r: r["ai_score"], reverse=True)
    return ranked


def explain_with_ollama(question, results, model="qwen2.5:3b", host="http://localhost:11434", mode="Otomatik"):
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
    response = requests.post(
        f"{host.rstrip('/')}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}},
        timeout=_OLLAMA_TIMEOUT
    )
    response.raise_for_status()
    answer = response.json().get("response", "").strip()
    return answer + "\n\n--- KULLANILAN KAYNAKLAR ---\n" + "\n".join(source_index)
