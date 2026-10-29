from scope import resolve_scope, scope_text, toggle_selection


def test_none_means_every_source():
    assert resolve_scope(None, [1, 2, 3]) is None


def test_selected_ids_are_kept():
    assert resolve_scope([1, 3], [1, 2, 3]) == [1, 3]


def test_empty_means_no_source():
    """Kullanıcı bilinçli olarak 'hiçbiri' derse kapsam boş kalır."""
    assert resolve_scope([], [1, 2, 3]) == []


def test_stale_ids_are_dropped():
    """Silinmiş kaynağın kimliği kapsamdan çıkarılır."""
    assert resolve_scope([2, 99], [1, 2, 3]) == [2]


def test_all_stale_falls_back_to_everything():
    """Tüm seçili kaynaklar silindiyse arama çıkmaz sokakta kalmamalı."""
    assert resolve_scope([97, 98], [1, 2, 3]) is None


def test_toggle_removes_from_all_selected():
    assert toggle_selection(None, [1, 2, 3], 2) == [1, 3]


def test_toggle_adds_back():
    assert toggle_selection([1], [1, 2, 3], 3) == [1, 3]


def test_toggle_removes_existing():
    assert toggle_selection([1, 3], [1, 2, 3], 3) == [1]


def test_toggle_drops_stale_before_adding():
    assert toggle_selection([99], [1, 2, 3], 2) == [2]


def test_toggle_can_empty_the_selection():
    assert toggle_selection([1], [1, 2, 3], 1) == []


def test_scope_text_describes_each_case():
    assert scope_text(None, 3) == "tüm kaynaklar (3)"
    assert scope_text([1, 2], 3) == "2/3 kaynak seçili"
    assert "hiçbir kaynak" in scope_text([], 3)
