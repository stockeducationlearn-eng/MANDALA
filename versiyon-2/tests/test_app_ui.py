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

    # -- ortak no-op'lar -------------------------------------------------
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        def _call(*a, **k):
            return None
        return _call

    def pack(self, *a, **k):
        parent = a[0] if a and isinstance(a[0], _Widget) else None
        if parent is not None:
            parent.children.append(self)

    def grid(self, *a, **k):
        pass

    def bind(self, *a, **k):
        pass

    def configure(self, *a, **k):
        pass

    config = configure

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

    # -- Notebook ---------------------------------------------------------
    def add(self, child=None, text=None, **k):
        self.items.append((child, text))

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


def test_ui_builds_with_menu_and_two_tabs(fake_tk, temp_db):
    app = fake_tk.module.App()
    assert app.notebook is not None
    tabs = [text.strip() for _child, text in app.notebook.items]
    assert tabs == ["Arama", "Raporlar"]


def test_menubar_has_expected_menus(fake_tk, temp_db):
    app = fake_tk.module.App()
    labels = [label for kind, label, _m in app.menubar.menu_items if kind == "cascade"]
    assert labels == ["Dosya", "Ara", "Kaynaklar", "Rapor", "Görünüm", "Yardım"]


def test_document_table_has_scope_column(fake_tk, temp_db):
    app = fake_tk.module.App()
    assert app.doc_tree.kwargs["columns"] == ("use", "type", "chunks")


def test_report_table_columns(fake_tk, temp_db):
    app = fake_tk.module.App()
    assert app.report_tree.kwargs["columns"] == ("kind", "size", "modified", "name")


def test_refresh_documents_marks_all_selected_by_default(fake_tk, temp_db):
    app = fake_tk.module.App()
    with temp_db.db() as con:
        con.execute("INSERT INTO documents(name, stored_path, file_type, sha256, added_at) "
                    "VALUES ('a.txt', '/tmp/a.txt', '.txt', 'a', datetime('now','localtime'))")
        con.commit()
    app.refresh_documents()
    values = [row["kwargs"]["values"] for row in app.doc_tree.items]
    assert values and all(v[0] == "✓" for v in values)


def test_toggle_document_excludes_one_source(fake_tk, temp_db):
    app = fake_tk.module.App()
    with temp_db.db() as con:
        for name in ("a.txt", "b.txt"):
            con.execute("INSERT INTO documents(name, stored_path, file_type, sha256, added_at) "
                        "VALUES (?, ?, '.txt', ?, datetime('now','localtime'))",
                        (name, f"/tmp/{name}", name))
        con.commit()
    ids = [d["id"] for d in temp_db.list_documents()]
    app.toggle_document(ids[0])
    assert app.active_document_ids() == [ids[1]]
    assert "1/2 kaynak seçili" in app.active_scope_text()


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
