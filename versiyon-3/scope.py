"""Kaynak seçiminin (arama kapsamı) saf mantığı.

Arayüzden bağımsız tutulur; böylece Tk penceresi açmadan test edilebilir.
"""


def resolve_scope(active, valid_ids):
    """Seçime göre arama kapsamını belirler.

    active:    ayarda saklanan seçim. None -> tüm kaynaklar; liste -> o kimlikler.
    valid_ids: arşivde hâlâ bulunan belge kimlikleri.
    Dönen:     None (süzgeç yok) veya belge kimliklerinin listesi.

    Seçili belgelerin tümü arşivden silinmişse kullanıcıyı çıkmaz sokakta
    bırakmamak için süzgeç kaldırılır; ama kullanıcı bilinçli olarak "hiçbiri"
    demişse (boş liste) bu korunur.
    """
    if active is None:
        return None
    valid = set(valid_ids)
    kept = [i for i in active if i in valid]
    if kept:
        return kept
    return [] if not active else None


def toggle_selection(active, valid_ids, doc_id):
    """Tek bir kaynağı aramaya dâhil eder ya da çıkarır."""
    valid = list(valid_ids)
    if active is None:                     # hepsi seçiliydi; yalnız bu biri çıkar
        return [i for i in valid if i != doc_id]
    kept = [i for i in active if i in set(valid)]
    if doc_id in kept:
        kept = [i for i in kept if i != doc_id]
    else:
        kept.append(doc_id)
    return kept


def scope_text(scope, total):
    """Kapsamı kullanıcıya gösterilecek kısa metne çevirir."""
    if scope is None:
        return f"tüm kaynaklar ({total})" if total else "tüm kaynaklar"
    if not scope:
        return "hiçbir kaynak (en az bir kaynak seçin)"
    return f"{len(scope)}/{total} kaynak seçili"
