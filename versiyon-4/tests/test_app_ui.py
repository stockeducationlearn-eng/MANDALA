"""Arayüz kurulumunu Tk penceresi açmadan doğrular.

Ortamda Tk kütüphanesi bulunmadığı için gerçek pencere açılamıyor. Burada
tkinter'ın yerine, çağrıları kaydeden küçük bir taklit konur; böylece menü,
sekme ve tablo kablolaması gerçek koddan geçirilerek sınanır. Amaç görsel
doğrulama değil, kurulum sırasının ve veri biçimlerinin doğruluğudur.
"""

import sys
import types

import pytest


class _Widget:
    """Tüm widget'lar için ortak, çağrıları kaydeden basit taklit."""

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.children = []
        self.items = []          # Treeview satırları / Notebook sekmeleri / Menu öğeleri
        self.selection_value = ()
        self.value = kwargs.get("textvariable")
        self.menu_items = []     # yalnızca menü çubuğu için
        self.configured = []     # configure() çağrıları
        self.state_history = []
        self.packed = False      # pack/pack_forget durumu
        self.master = None       # Panedwindow.add gibi çağrılarda ata

    # -- ortak no-op'lar -------------------------------------------------
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        def _call(*a, **k):
            return None
        return _call

    def pack(self, *a, **k):
        self.packed = True
        parent = a[0] if a and isinstance(a[0], _Widget) else None
        if parent is not None:
            parent.children.append(self)

    def pack_forget(self):
        self.packed = False

    def grid(self, *a, **k):
        pass

    def bind(self, *a, **k):
        pass

    def configure(self, *a, **k):
        self.configured.append((a, k))

    config = configure

    def state(self, spec=None):
        if spec is not None:
            self.state_history.append(tuple(spec))

    # -- Treeview / Listbox / Text ---------------------------------------
    def insert(self, *a, **k):
        # Treeview: insert(parent, index, iid=..., text=..., values=...)
        self.items.append({"args": a, "kwargs": k})

    def delete(self, *a, **k):
        self.items.clear()

    def get_children(self):
        return list(range(len(self.items)))

    def selection(self):
        return self.selection_value

    def curselection(self):
        return self.selection_value

    def heading(self, *a, **k):
        pass

    def column(self, *a, **k):
        pass

    def identify_region(self, x, y):
        return "cell"

    def identify_column(self, x):
        return "#1"

    def identify_row(self, y):
        return "1"

    # -- Menu -------------------------------------------------------------
    def add_cascade(self, label=None, menu=None, **k):
        self.menu_items.append(("cascade", label, menu))

    def add_command(self, label=None, command=None, **k):
        self.menu_items.append(("command", label, command))

    def add_separator(self, **k):
        self.menu_items.append(("separator", None, None))

    # -- Notebook / Panedwindow -------------------------------------------
    def add(self, child=None, text=None, **k):
        self.items.append((child, text))
        if child is not None:
            child.master = self

    def select(self, tab=None):
        self.selected = tab

    # -- değer tutan nesneler --------------------------------------------
    def get(self, *a, **k):
        return self._value if hasattr(self, "_value") else ""

    def set(self, value):
        self._value = value


class _Var:
    def __init__(self, value=None, **k):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class _Menu(_Widget):
    pass


class _Notebook(_Widget):
    pass


class _Treeview(_Widget):
    pass


class _Text(_Widget):
    def get(self, *a, **k):
        return self._value if hasattr(self, "_value") else ""

    def insert(self, index, text, *a, **k):
        self._value = (getattr(self, "_value", "") or "") + text


class _Listbox(_Widget):
    pass


@pytest.fixture
def fake_tk(monkeypatch, tmp_path):
    """tkinter ve alt modüllerini taklitleriyle değiştirir, sonra app'i yükler."""
    tk = types.ModuleType("tkinter")
    ttk = types.ModuleType("tkinter.ttk")
    filedialog = types.ModuleType("tkinter.filedialog")
    messagebox = types.ModuleType("tkinter.messagebox")

    tk.Tk = _Widget
    tk.Toplevel = _Widget
    tk.Menu = _Menu
    tk.Text = _Text
    tk.Listbox = _Listbox
    tk.StringVar = _Var
    tk.BooleanVar = _Var
    tk.IntVar = _Var
    tk.END = "end"
    tk.Menu.__name__ = "Menu"

    for name in ("Frame", "Label", "Button", "Checkbutton", "Combobox",
                 "Entry", "Panedwindow", "Scrollbar", "LabelFrame", "Style"):
        setattr(ttk, name, type(name, (_Widget,), {}))
    ttk.Treeview = _Treeview
    ttk.Notebook = _Notebook

    filedialog.askopenfilenames = lambda **k: ()
    filedialog.askopenfilename = lambda **k: ""
    filedialog.asksaveasfilename = lambda **k: ""
    filedialog.askdirectory = lambda **k: ""

    shown = []
    messagebox.showinfo = lambda *a, **k: shown.append(("info", a))
    messagebox.showwarning = lambda *a, **k: shown.append(("warning", a))
    messagebox.showerror = lambda *a, **k: shown.append(("error", a))
    messagebox.askyesno = lambda *a, **k: True

    tk.ttk = ttk
    tk.filedialog = filedialog
    tk.messagebox = messagebox
    monkeypatch.setitem(sys.modules, "tkinter", tk)
    monkeypatch.setitem(sys.modules, "tkinter.ttk", ttk)
    monkeypatch.setitem(sys.modules, "tkinter.filedialog", filedialog)
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", messagebox)
    monkeypatch.delitem(sys.modules, "app", raising=False)

    import app as app_module
    # Ayarları geçici klasöre yönlendir; gerçek kullanıcı ayarına dokunma.
    monkeypatch.setattr(app_module, "SETTINGS", tmp_path / "settings.json")
    return types.SimpleNamespace(module=app_module, shown=shown)


def test_ui_builds_with_three_steps(fake_tk, temp_db):
    app = fake_tk.module.App()
    assert len(app.step_frames) == 3
    assert app.current_step == 0


def test_first_step_is_source_selection(fake_tk, temp_db):
    app = fake_tk.module.App()
    assert hasattr(app, "doc_tree")
    assert app.doc_tree.kwargs["columns"] == ("use", "type", "chunks")


def test_step_navigation_moves_forward_and_back(fake_tk, temp_db):
    app = fake_tk.module.App()
    assert app.current_step == 0
    app.next_step()
    assert app.current_step == 1
    app.next_step()
    assert app.current_step == 2
    app.next_step()                 # son adımda ileri gitmez
    assert app.current_step == 2
    app.prev_step()
    assert app.current_step == 1
    app.prev_step()
    app.prev_step()                 # ilk adımda geri gitmez
    assert app.current_step == 0


def test_search_lives_in_second_step_with_own_tabs(fake_tk, temp_db):
    app = fake_tk.module.App()
    tabs = [text.strip() for _child, text in app.search_notebook.items]
    assert tabs == ["Sorgu ve sonuçlar", "Son aramalar"]
    assert hasattr(app, "result_tree")


def test_result_and_reports_share_third_step(fake_tk, temp_db):
    app = fake_tk.module.App()
    tabs = [text.strip() for _child, text in app.result_notebook.items]
    assert tabs == ["Kaynak metni ve not", "Raporlar"]


def test_only_current_step_is_visible(fake_tk, temp_db):
    app = fake_tk.module.App()
    visible = [i for i, f in enumerate(app.step_frames) if f.packed]
    assert visible == [0]
    app.next_step()
    visible = [i for i, f in enumerate(app.step_frames) if f.packed]
    assert visible == [1]
    app.show_step(2)
    visible = [i for i, f in enumerate(app.step_frames) if f.packed]
    assert visible == [2]


def test_out_of_range_step_is_clamped(fake_tk, temp_db):
    app = fake_tk.module.App()
    app.show_step(99)
    assert app.current_step == 2
    app.show_step(-5)
    assert app.current_step == 0


def test_menubar_has_expected_menus(fake_tk, temp_db):
    app = fake_tk.module.App()
    labels = [label for kind, label, _m in app.menubar.menu_items if kind == "cascade"]
    assert labels == ["Dosya", "Ara", "Kaynaklar", "Rapor", "Görünüm", "Yardım"]


def test_report_table_columns(fake_tk, temp_db):
    app = fake_tk.module.App()
    assert app.report_tree.kwargs["columns"] == ("kind", "size", "modified", "name")


def _row_texts(tree):
    """Treeview satırlarındaki belge adlarını döndürür."""
    return [row["kwargs"].get("text", "") for row in tree.items]


def _insert_doc(db, name, sha=None, in_study=1, in_archive=0, path=None):
    """Test veritabanına bir kaynak ekler (çalışma/arşiv bayraklarıyla)."""
    with db.db() as con:
        con.execute("INSERT INTO documents(name, stored_path, file_type, sha256, added_at, "
                    "in_study, in_archive) VALUES (?, ?, '.txt', ?, datetime('now','localtime'), ?, ?)",
                    (name, path or f"/tmp/{name}", sha or name, in_study, in_archive))
        con.commit()
    with db.db() as con:
        return con.execute("SELECT id FROM documents WHERE name=?", (name,)).fetchone()["id"]


def test_step_buttons_show_source_count(fake_tk, temp_db):
    app = fake_tk.module.App()
    _insert_doc(temp_db, "a.txt")
    app.refresh_step_hints()
    label = app.step_buttons[0].configured[-1][1]["text"]
    assert label == "1 · Kaynak ekle ve seç (1)"


def test_first_step_has_study_and_archive_sections(fake_tk, temp_db):
    app = fake_tk.module.App()
    assert app.study_section is not None
    assert hasattr(app, "archive_tree")


def test_first_step_panels_are_side_by_side(fake_tk, temp_db):
    """İki panel yatay Panedwindow içinde yan yana durmalı, alt alta değil."""
    app = fake_tk.module.App()
    panes = app.sources_panes
    assert panes.kwargs.get("orient") == "horizontal"
    children = [child for child, _text in panes.items]
    assert app.study_section in children
    assert any(c is not app.study_section and c is not None for c in children)
    # Paneller doğrudan adım çerçevesine değil, paned window'a eklenir.
    assert app.study_section.master is panes


def test_refresh_documents_marks_all_selected_by_default(fake_tk, temp_db):
    app = fake_tk.module.App()
    _insert_doc(temp_db, "a.txt")
    app.refresh_documents()
    values = [row["kwargs"]["values"] for row in app.doc_tree.items]
    assert values and all(v[0] == "✓" for v in values)


def test_toggle_document_excludes_one_source(fake_tk, temp_db):
    app = fake_tk.module.App()
    ids = [_insert_doc(temp_db, "a.txt"), _insert_doc(temp_db, "b.txt")]
    app.toggle_document(ids[0])
    assert app.active_document_ids() == [ids[1]]
    assert "1/2 kaynak seçili" in app.active_scope_text()


def test_archive_holds_old_sources_not_in_study(fake_tk, temp_db):
    app = fake_tk.module.App()
    _insert_doc(temp_db, "eski.txt", in_study=0, in_archive=1)
    app.refresh_documents()
    assert app.doc_tree.items == []
    assert _row_texts(app.archive_tree) == ["eski.txt"]


def test_archive_to_study_moves_source(fake_tk, temp_db):
    app = fake_tk.module.App()
    doc_id = _insert_doc(temp_db, "eski.txt", in_study=0, in_archive=1)
    app.refresh_documents()
    app.set_all_documents(False)          # arama seçimini sıfırla
    app.add_archive_selected_to_study([doc_id])
    assert _row_texts(app.doc_tree) == ["eski.txt"]
    assert app.archive_tree.items == []
    assert app.active_document_ids() == [doc_id]


def test_archive_selected_marks_document_archived(fake_tk, temp_db):
    app = fake_tk.module.App()
    doc_id = _insert_doc(temp_db, "yeni.txt")
    app.refresh_documents()
    app.archive_selected_from_ids([doc_id])
    assert _row_texts(app.archive_tree) == ["yeni.txt"]
    assert app.doc_tree.items == []


def test_remove_archive_selected_clears_flag(fake_tk, temp_db):
    app = fake_tk.module.App()
    doc_id = _insert_doc(temp_db, "eski.txt", in_study=0, in_archive=1)
    app.refresh_documents()
    app.remove_archive_selected_from_ids([doc_id])
    assert app.archive_tree.items == []


def test_bulk_delete_removes_multiple_sources(fake_tk, temp_db, monkeypatch):
    app = fake_tk.module.App()
    ids = [_insert_doc(temp_db, "a.txt"), _insert_doc(temp_db, "b.txt"), _insert_doc(temp_db, "c.txt")]
    monkeypatch.setattr(fake_tk.module.messagebox, "askyesno", lambda *a, **k: True)
    app.settings["active_document_ids"] = list(ids)   # üçü de seçili
    app.refresh_documents()
    app.delete_selected_ids(ids[:2])
    assert _row_texts(app.doc_tree) == ["c.txt"]
    assert app.active_document_ids() == [ids[2]]


def test_archive_drop_on_study_area_adds_source(fake_tk, temp_db, monkeypatch):
    app = fake_tk.module.App()
    doc_id = _insert_doc(temp_db, "eski.txt", in_study=0, in_archive=1)
    app.refresh_documents()
    monkeypatch.setattr(app, "winfo_containing", lambda x, y: app.doc_tree, raising=False)
    app._drag_ids = [doc_id]
    app._archive_drag_drop(types.SimpleNamespace(x_root=0, y_root=0))
    assert _row_texts(app.doc_tree) == ["eski.txt"]


def test_search_without_selected_source_warns(fake_tk, temp_db):
    app = fake_tk.module.App()
    app.set_query("tazminat")
    app.set_all_documents(False)
    app.run_search()
    assert any(kind == "warning" for kind, _a in fake_tk.shown)


def test_refresh_reports_lists_exports(fake_tk, temp_db, tmp_path, monkeypatch):
    import exporter
    out = tmp_path / "exports"
    out.mkdir()
    monkeypatch.setattr(exporter, "EXPORT_DIR", out)
    (out / "Arama_Raporu_tazminat.txt").write_text("içerik", encoding="utf-8")
    app = fake_tk.module.App()
    app.refresh_reports()
    assert len(app.report_list) == 1
    values = app.report_tree.items[0]["kwargs"]["values"]
    assert values[0] == "Metin / konu notu"
    assert "1 rapor bulundu" in app.report_count_var.get()
