from library import (normalize_name, find_conflict, is_identical,
                     suggest_name, split_study_and_archive)


def test_normalize_ignores_case_and_spacing():
    """Türkçe küçük harf ve fazla boşluk farkı adı değiştirmez."""
    assert normalize_name("Kıdem  TAZMİNATI.PDF") == normalize_name("kıdem tazminatı.pdf")


def test_normalize_keeps_turkish_dotless_i_distinct():
    """Türkçe kuralı: ASCII 'I' -> 'ı', 'İ' -> 'i'; ikisi ayrı harftir."""
    assert normalize_name("IĞDIR.pdf") == "ığdır.pdf"
    assert normalize_name("İZMİR.pdf") == "izmir.pdf"
    assert normalize_name("İSTANBUL.pdf") == normalize_name("istanbul.pdf")


def test_normalize_empty_is_empty():
    assert normalize_name("   ") == ""
    assert normalize_name(None) == ""


def test_find_conflict_matches_same_name():
    docs = [{"id": 1, "name": "rapor.pdf", "sha256": "a"}]
    assert find_conflict("RAPOR.pdf", docs)["id"] == 1


def test_find_conflict_returns_none_for_new_name():
    docs = [{"id": 1, "name": "rapor.pdf", "sha256": "a"}]
    assert find_conflict("baska.pdf", docs) is None


def test_find_conflict_ignores_empty_name():
    docs = [{"id": 1, "name": "rapor.pdf", "sha256": "a"}]
    assert find_conflict("   ", docs) is None


def test_is_identical_true_only_for_same_content():
    conflict = {"id": 1, "name": "rapor.pdf", "sha256": "abc"}
    assert is_identical(conflict, "abc") is True
    assert is_identical(conflict, "xyz") is False
    assert is_identical(None, "abc") is False


def test_suggest_name_adds_counter_before_extension():
    docs = [{"name": "rapor.pdf"}]
    assert suggest_name("rapor.pdf", docs) == "rapor (2).pdf"


def test_suggest_name_skips_taken_counters():
    docs = [{"name": "rapor.pdf"}, {"name": "rapor (2).pdf"}, {"name": "rapor (3).pdf"}]
    assert suggest_name("rapor.pdf", docs) == "rapor (4).pdf"


def test_suggest_name_handles_extensionless_name():
    docs = [{"name": "notlar"}]
    assert suggest_name("notlar", docs) == "notlar (2)"


def test_suggest_name_handles_multiple_dots():
    """Uzantı yalnızca son noktadan sonrasıdır."""
    docs = [{"name": "2024.rapor.pdf"}]
    assert suggest_name("2024.rapor.pdf", docs) == "2024.rapor (2).pdf"


def test_suggest_name_empty_falls_back():
    assert suggest_name("", []) == "belge (2)"


def test_suggest_name_is_case_insensitive():
    """Büyük/küçük harf farkı çakışma sayılır; sayaç ona göre artar."""
    docs = [{"name": "RAPOR.PDF"}]
    assert suggest_name("rapor.pdf", docs) == "rapor (2).pdf"


def test_split_study_and_archive_separates_lists():
    docs = [
        {"id": 1, "in_study": 1, "in_archive": 0},
        {"id": 2, "in_study": 0, "in_archive": 1},
    ]
    study, archive = split_study_and_archive(docs)
    assert [d["id"] for d in study] == [1]
    assert [d["id"] for d in archive] == [2]
