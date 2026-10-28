import requests

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
        timeout=600
    )
    response.raise_for_status()
    answer = response.json().get("response", "").strip()
    return answer + "\n\n--- KULLANILAN KAYNAKLAR ---\n" + "\n".join(source_index)
