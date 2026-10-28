from text_utils import tr_lower, tr_upper, tr_fold_for_search


def test_tr_lower_uses_dotted_and_dotless_i():
    assert tr_lower("İSTANBUL") == "istanbul"
    assert tr_lower("IĞDIR") == "ığdır"
    assert tr_lower("İIıi") == "iııi"


def test_tr_upper_uses_dotted_and_dotless_i():
    assert tr_upper("istanbul") == "İSTANBUL"
    assert tr_upper("ığdır") == "IĞDIR"
    assert tr_upper("iiıİ") == "İİIİ"


def test_fold_merges_dotted_and_dotless_i():
    # i / İ / I / ı hepsi tek biçime inmeli
    assert tr_fold_for_search("İstanbul") == "istanbul"
    assert tr_fold_for_search("ISTANBUL") == "istanbul"
    assert tr_fold_for_search("ıstanbul") == "istanbul"
    assert tr_fold_for_search("IĞDIR") == "igdir"
    assert tr_fold_for_search("ığdır") == "igdir"


def test_fold_strips_turkish_diacritics():
    assert tr_fold_for_search("çalışma") == "calisma"
    assert tr_fold_for_search("ÖĞÜN") == "ogun"
    assert tr_fold_for_search("şeker") == "seker"


def test_fold_is_idempotent():
    once = tr_fold_for_search("Çalışma İstanbul IĞDIR")
    assert tr_fold_for_search(once) == once
