import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading, os, json, sys, subprocess, traceback

import database
from database import db
from ingest import add_file, NameConflictError
from search_engine import (search, MATCH_CHOICES, match_from_label,
                           label_from_settings)
from ai_helper import (explain_with_ollama, expand_query, rank_by_relevance,
                       check_ollama, OllamaError, rank_by_embedding, filter_by_score)
from exporter import (export_csv, export_results, backup_project,
                      list_reports, human_size)
from scope import (resolve_scope, toggle_selection, scope_text,
                   selection_after_delete)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SETTINGS = DATA / "settings.json"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

APP_VERSION = "4.0"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        database.init_db()
        self.title(f"Bilgi Araştırma {APP_VERSION} — Kaynaklı Yerel Arama")
        self.geometry("1380x900")
        self.minsize(1000, 700)
        self.last_results = []
        self.last_search_id = None
        self.selected_result_index = None
        self.settings = self.load_settings()
        self.report_list = []
        self._build_ui()
        self.refresh_documents()
        self.refresh_history()
        self.refresh_reports()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def load_settings(self):
        defaults = {"tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    "ocr_lang": "tur+eng", "ollama_model": "qwen2.5:3b",
                    "ollama_timeout": 300, "ollama_keep_alive": "30m",
                    "all_terms": False, "min_coverage": 0.0, "turkish_sensitive": False}
        if SETTINGS.exists():
            try:
                defaults.update(json.loads(SETTINGS.read_text(encoding="utf-8")))
            except Exception:
                pass
        # Eski sürümde yalnızca "all_terms" vardı. Onay kutusu kaldırıldığı için
        # eski True değeri, boş sonuç veren %100 yerine önerilen %60'a taşınır.
        if "min_coverage" not in defaults or (
                defaults["all_terms"] and not defaults.get("min_coverage")):
            defaults["min_coverage"] = 0.6 if defaults.get("all_terms") else 0.0
        return defaults

    def save_settings_file(self):
        SETTINGS.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_ui(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except Exception: pass
        self._build_menu()
        self._build_header()
        self._build_stepper()
        self.step_frames = []
        self._build_step_sources()
        self._build_step_search()
        self._build_step_result()
        self._build_navbar()
        self.show_step(0)

    def _build_header(self):
        top = ttk.Frame(self, padding=(12, 10, 12, 0))
        top.pack(fill="x")
        ttk.Label(top, text="BİLGİ ARAŞTIRMA", font=("Segoe UI", 17, "bold")).pack(side="left")
        ttk.Label(top, text=f"sürüm {APP_VERSION}", foreground="#777").pack(side="left", padx=(8, 0))
        ttk.Label(top, text="PDF • Word • TXT • Resim • SQLite • Yerel OCR",
                  foreground="#555").pack(side="left", padx=16)
        ttk.Button(top, text="Yedek oluştur", command=self.backup).pack(side="right", padx=3)
        ttk.Button(top, text="Ayarlar", command=self.open_settings).pack(side="right", padx=3)

    def _build_stepper(self):
        """Adım göstergesi: hangi ekranda olduğunuzu gösterir, tıklayınca geçer."""
        bar = ttk.Frame(self, padding=(12, 8, 12, 0))
        bar.pack(fill="x")
        self.step_buttons = []
        for i, label in enumerate(("1 · Kaynak ekle ve seç", "2 · Ara", "3 · Sonuç ve rapor")):
            b = ttk.Button(bar, text=label, width=25,
                           command=lambda i=i: self.show_step(i))
            b.pack(side="left", padx=(0, 6))
            self.step_buttons.append(b)
        self.step_hint_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.step_hint_var, foreground="#555").pack(side="right")

    def _build_navbar(self):
        bar = ttk.Frame(self, padding=(12, 6, 12, 10))
        bar.pack(fill="x", side="bottom")
        self.back_btn = ttk.Button(bar, text="‹ Geri", width=12, command=self.prev_step)
        self.back_btn.pack(side="left")
        self.next_btn = ttk.Button(bar, text="İleri ›", width=12, command=self.next_step)
        self.next_btn.pack(side="right")

    def show_step(self, index):
        """Verilen adımı gösterir; diğerlerini gizler."""
        index = max(0, min(index, len(self.step_frames) - 1))
        self.current_step = index
        for i, frame in enumerate(self.step_frames):
            if i == index:
                frame.pack(fill="both", expand=True, padx=12, pady=(8, 0))
            else:
                frame.pack_forget()
        for i, button in enumerate(self.step_buttons):
            button.state(["disabled"] if i == index else ["!disabled"])
        self.step_hint_var.set(f"Adım {index + 1} / {len(self.step_frames)}")
        self.back_btn.state(["disabled"] if index == 0 else ["!disabled"])
        self.next_btn.state(["disabled"] if index == len(self.step_frames) - 1 else ["!disabled"])
        self.refresh_step_hints()

    def next_step(self):
        self.show_step(self.current_step + 1)

    def prev_step(self):
        self.show_step(self.current_step - 1)

    def open_reports(self):
        """Raporlar listesinin bulunduğu son adımı açar."""
        self.show_step(2)
        self.result_notebook.select(self.reports_tab)

    def refresh_step_hints(self):
        """Adım düğmelerinde kısa durum bilgisi (kaynak ve sonuç sayısı) gösterir."""
        docs = len(database.list_study_documents())
        self.step_buttons[0].configure(text=f"1 · Kaynak ekle ve seç ({docs})")
        self.step_buttons[2].configure(text=f"3 · Sonuç ve rapor ({len(self.last_results)})")

    def _build_step_sources(self):
        frame = ttk.Frame(self)
        self.step_frames.append(frame)
        ttk.Label(frame, text="1. ADIM — KAYNAK EKLE VE SEÇ",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Yeni bir çalışma için kaynak ekleyin; aramada kullanmak istediklerinizi "
                              "işaretleyin. Arşivdeki eski kaynakları üst listeye sürükleyerek alabilirsiniz.",
                  foreground="#555").pack(anchor="w", pady=(2, 8))

        # --- Üst bölüm: yeni çalışma (arama kapsamı) -----------------------
        study = ttk.LabelFrame(frame, text=" YENİ DÖKÜMAN EKLE — aramada kullanılacak kaynaklar ",
                               padding=8)
        study.pack(fill="both", expand=True)
        self.study_section = study
        add = ttk.Frame(study)
        add.pack(fill="x")
        ttk.Button(add, text="＋ Kaynak ekle…", command=self.add_sources).pack(side="left")
        ttk.Button(add, text="Girdi kaynağından al…",
                   command=self.open_input_dialog).pack(side="left", padx=6)
        ttk.Button(add, text="Tümünü işaretle", width=16,
                   command=lambda: self.set_all_documents(True)).pack(side="right")
        ttk.Button(add, text="İşaretleri kaldır", width=17,
                   command=lambda: self.set_all_documents(False)).pack(side="right", padx=4)
        ttk.Label(study, text="'Aramada' sütununa tıklayarak kaynağı işaretleyin. Arama yalnızca "
                              "işaretli kaynaklarda yapılır. Satırları çoklu seçip alttaki düğmeleri kullanın.",
                  foreground="#555", wraplength=1100, justify="left").pack(anchor="w", pady=(6, 0))
        self.doc_tree = ttk.Treeview(study, columns=("use", "type", "chunks"),
                                     show="tree headings", height=9, selectmode="extended")
        self.doc_tree.heading("#0", text="Belge")
        self.doc_tree.heading("use", text="Aramada")
        self.doc_tree.heading("type", text="Tür")
        self.doc_tree.heading("chunks", text="Bölüm")
        self.doc_tree.column("#0", width=430)
        self.doc_tree.column("use", width=80, anchor="center")
        self.doc_tree.column("type", width=80)
        self.doc_tree.column("chunks", width=70)
        self.doc_tree.pack(fill="both", expand=True, pady=6)
        self.doc_tree.bind("<Button-1>", self.on_doc_click)
        doc_btns = ttk.Frame(study)
        doc_btns.pack(fill="x")
        ttk.Button(doc_btns, text="Seçilileri arşive ekle",
                   command=self.archive_selected).pack(side="left")
        ttk.Button(doc_btns, text="Seçilileri sil (toplu)",
                   command=self.delete_selected).pack(side="left", padx=5)
        self.scope_summary_var = tk.StringVar(value="")
        ttk.Label(doc_btns, textvariable=self.scope_summary_var,
                  foreground="#555").pack(side="right")

        # --- Alt bölüm: döküman arşivi -------------------------------------
        arch = ttk.LabelFrame(frame, text=" DÖKÜMAN ARŞİVİ — daha önce kullanılan kaynaklar ",
                              padding=8)
        arch.pack(fill="both", expand=True, pady=(8, 0))
        head = ttk.Frame(arch)
        head.pack(fill="x")
        ttk.Label(head, text="Sürükleyip yukarıdaki listeye bırakın ya da seçip "
                             "'Aramaya ekle' düğmesini kullanın.",
                  foreground="#555").pack(side="left")
        ttk.Button(head, text="Aramaya ekle",
                   command=self.add_archive_selected_to_study).pack(side="right")
        self.archive_tree = ttk.Treeview(arch, columns=("type", "chunks"),
                                         show="tree headings", height=8, selectmode="extended")
        self.archive_tree.heading("#0", text="Belge")
        self.archive_tree.heading("type", text="Tür")
        self.archive_tree.heading("chunks", text="Bölüm")
        self.archive_tree.column("#0", width=500)
        self.archive_tree.column("type", width=80)
        self.archive_tree.column("chunks", width=70)
        self.archive_tree.pack(fill="both", expand=True, pady=6)
        self.archive_tree.bind("<ButtonPress-1>", self._archive_drag_start)
        self.archive_tree.bind("<ButtonRelease-1>", self._archive_drag_drop)
        ttk.Button(arch, text="Seçilileri arşivden çıkar",
                   command=self.remove_archive_selected).pack(side="left")

    def _build_step_search(self):
        frame = ttk.Frame(self)
        self.step_frames.append(frame)
        ttk.Label(frame, text="2. ADIM — ARA", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Soruyu ya da anahtar kelimeleri yazıp arayın.",
                  foreground="#555").pack(anchor="w", pady=(2, 8))
        nb = ttk.Notebook(frame)
        self.search_notebook = nb
        nb.pack(fill="both", expand=True)
        qtab = ttk.Frame(nb, padding=8)
        nb.add(qtab, text="  Sorgu ve sonuçlar  ")
        htab = ttk.Frame(nb, padding=8)
        nb.add(htab, text="  Son aramalar  ")

        ttk.Label(qtab, text="SORU / ANAHTAR KELİMELER", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        qbox = ttk.Frame(qtab)
        qbox.pack(fill="x", pady=5)
        self.query_entry = tk.Text(qbox, height=4, wrap="word", font=("Segoe UI", 11))
        self.query_entry.pack(side="left", fill="x", expand=True)
        self.query_entry.bind("<Control-Return>", lambda _e: (self.run_search(), "break")[1])
        qbtns = ttk.Frame(qbox)
        qbtns.pack(side="left", padx=(6, 0), fill="y")
        ttk.Button(qbtns, text="Ara", command=self.run_search).pack(fill="x")
        ttk.Button(qbtns, text="Akıllı ara (Ollama)", command=self.ai_smart_search).pack(fill="x", pady=(4, 0))
        ttk.Button(qbtns, text="Girdi kaynağı…", command=self.open_input_dialog).pack(fill="x", pady=(4, 0))
        ttk.Button(qbtns, text="Temizle",
                   command=lambda: self.query_entry.delete("1.0", "end")).pack(fill="x", pady=(4, 0))
        ttk.Label(qtab, text="Çok satırlı giriş: Ctrl+Enter ile arar. Girdiyi elle yazabilir, bir dökümandan "
                             "paragraf seçebilir, resim/ekran görüntüsünden OCR ile ya da web adresinden alabilirsiniz.",
                  foreground="#555", wraplength=980, justify="left").pack(anchor="w")
        mode_row = ttk.Frame(qtab)
        mode_row.pack(fill="x", pady=(4, 4))
        ttk.Label(mode_row, text="Araştırma türü:").pack(side="left", padx=(0, 4))
        self.mode_var = tk.StringVar(value="Otomatik")
        self.mode_combo = ttk.Combobox(mode_row, textvariable=self.mode_var, state="readonly", width=19,
                                       values=("Otomatik", "Çıkmış soru", "Paragraf / metin", "Kavram"))
        self.mode_combo.pack(side="left", padx=(0, 6))
        ttk.Label(mode_row, text="Soru/seçenek, paragraf veya tek kavram girebilirsiniz.",
                  foreground="#555").pack(side="left", padx=8)
        self.match_var = tk.StringVar(value=label_from_settings(
            bool(self.settings.get("all_terms", False)),
            self.settings.get("min_coverage", 0.0)))
        ttk.Label(mode_row, text="Eşleşme:").pack(side="left", padx=(10, 2))
        self.match_combo = ttk.Combobox(mode_row, textvariable=self.match_var, state="readonly", width=14,
                                        values=[name for name, _a, _c in MATCH_CHOICES])
        self.match_combo.pack(side="left")
        self.match_combo.bind("<<ComboboxSelected>>", self.on_match_change)
        self.turkish_sensitive_var = tk.BooleanVar(value=bool(self.settings.get("turkish_sensitive", False)))
        ttk.Checkbutton(mode_row, text="Türkçe karakter duyarlı", variable=self.turkish_sensitive_var,
                        command=self.on_turkish_toggle).pack(side="left", padx=8)
        self.fast_smart_var = tk.BooleanVar(value=bool(self.settings.get("ai_fast_mode", True)))
        ttk.Checkbutton(mode_row, text="Hızlı akıllı arama (gömme)", variable=self.fast_smart_var,
                        command=self.on_fast_toggle).pack(side="left", padx=8)
        self.status_var = tk.StringVar(value="Hazır — önce kaynak dosyalarınızı ekleyin.")
        ttk.Label(qtab, textvariable=self.status_var).pack(anchor="w", pady=(2, 5))

        cols = ("source", "location", "score", "preview")
        self.result_tree = ttk.Treeview(qtab, columns=cols, show="headings", height=14)
        for col, title in [("source","Kaynak"),("location","Sayfa / Konum"),("score","Puan"),("preview","Kaynak metni")]:
            self.result_tree.heading(col, text=title)
        self.result_tree.column("source", width=185)
        self.result_tree.column("location", width=115)
        self.result_tree.column("score", width=58)
        self.result_tree.column("preview", width=520)
        self.result_tree.pack(fill="both", expand=True, pady=5)
        self.result_tree.bind("<<TreeviewSelect>>", self.show_selected_result)
        ttk.Label(qtab, text="Bir sonuca çift tıklayarak 3. adımda ayrıntısını ve rapor seçeneklerini açabilirsiniz.",
                  foreground="#555").pack(anchor="w")
        self.result_tree.bind("<Double-1>", lambda _e: self.open_result_detail())

        ttk.Label(htab, text="SON ARAMALAR", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(htab, text="Bir aramayı seçtiğinizde sorgu yüklenir ve yeniden çalıştırılır.",
                  foreground="#555").pack(anchor="w", pady=(2, 6))
        self.history = tk.Listbox(htab, height=18)
        self.history.pack(fill="both", expand=True)
        self.history.bind("<<ListboxSelect>>", self.open_history)

    def open_result_detail(self):
        """Seçili sonucun ayrıntısını 3. adımda gösterir."""
        if not self.result_tree.selection():
            return
        self.show_selected_result()
        self.show_step(2)

    def _build_step_result(self):
        frame = ttk.Frame(self)
        self.step_frames.append(frame)
        ttk.Label(frame, text="3. ADIM — SONUÇ VE RAPOR",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Seçili kaynağı inceleyin, konu notu oluşturun ve rapor üretin.",
                  foreground="#555").pack(anchor="w", pady=(2, 8))
        nb = ttk.Notebook(frame)
        self.result_notebook = nb
        nb.pack(fill="both", expand=True)
        dtab = ttk.Frame(nb, padding=8)
        nb.add(dtab, text="  Kaynak metni ve not  ")
        self._build_reports_tab(nb)

        action = ttk.Frame(dtab)
        action.pack(fill="x", pady=(0, 6))
        ttk.Button(action, text="Kaynaklardan konu notu oluştur (Ollama)", command=self.ai_explain).pack(side="left")
        ttk.Button(action, text="Konu notunu arşivle", command=self.save_research_note).pack(side="left", padx=5)
        ttk.Button(action, text="PDF raporu", command=lambda: self.export_report("pdf")).pack(side="left", padx=3)
        ttk.Button(action, text="Word raporu", command=lambda: self.export_report("docx")).pack(side="left", padx=3)
        ttk.Button(action, text="TXT raporu", command=lambda: self.export_report("txt")).pack(side="left", padx=3)
        ttk.Button(action, text="CSV", command=self.export_results).pack(side="left", padx=3)
        ttk.Button(action, text="Kaynak dosyayı aç", command=self.open_source).pack(side="left", padx=3)

        ttk.Label(dtab, text="SEÇİLİ SONUÇ / KAYNAK METNİ", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 2))
        self.detail = tk.Text(dtab, height=16, wrap="word", font=("Segoe UI", 10))
        self.detail.pack(fill="both", expand=True)
        self.current_ai_answer = ""
        note_row = ttk.Frame(dtab)
        note_row.pack(fill="x", pady=4)
        ttk.Label(note_row, text="Not:").pack(side="left")
        self.note_entry = ttk.Entry(note_row)
        self.note_entry.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(note_row, text="Notu kaydet", command=self.save_note).pack(side="right")

    def _build_menu(self):
        menubar = tk.Menu(self)

        dosya = tk.Menu(menubar, tearoff=0)
        dosya.add_command(label="Kaynak ekle…", accelerator="Ctrl+O", command=self.add_sources)
        dosya.add_command(label="Girdi kaynağından al…", accelerator="Ctrl+G", command=self.open_input_dialog)
        dosya.add_separator()
        dosya.add_command(label="Yedek oluştur (ZIP)", command=self.backup)
        dosya.add_command(label="Çıkış", accelerator="Ctrl+Q", command=self.on_close)
        menubar.add_cascade(label="Dosya", menu=dosya)

        ara = tk.Menu(menubar, tearoff=0)
        ara.add_command(label="Ara", accelerator="Ctrl+Enter", command=self.run_search)
        ara.add_command(label="Akıllı ara (Ollama)", accelerator="Ctrl+Shift+Enter", command=self.ai_smart_search)
        ara.add_separator()
        ara.add_command(label="Sorguyu temizle", command=lambda: self.query_entry.delete("1.0", "end"))
        ara.add_command(label="Son aramalar", command=self.refresh_history)
        menubar.add_cascade(label="Ara", menu=ara)

        kaynak = tk.Menu(menubar, tearoff=0)
        kaynak.add_command(label="Tüm kaynakları aramaya dâhil et", command=lambda: self.set_all_documents(True))
        kaynak.add_command(label="Hiçbir kaynağı kullanma", command=lambda: self.set_all_documents(False))
        kaynak.add_separator()
        kaynak.add_command(label="Seçilileri arşive ekle", command=self.archive_selected)
        kaynak.add_command(label="Arşivden aramaya ekle", command=self.add_archive_selected_to_study)
        kaynak.add_command(label="Seçilileri arşivden çıkar", command=self.remove_archive_selected)
        kaynak.add_separator()
        kaynak.add_command(label="Seçilileri sil (toplu)", command=self.delete_selected)
        kaynak.add_command(label="Kaynak dosyayı aç", command=self.open_source)
        menubar.add_cascade(label="Kaynaklar", menu=kaynak)

        rapor = tk.Menu(menubar, tearoff=0)
        rapor.add_command(label="Raporlar listesini aç", accelerator="Ctrl+R",
                          command=self.open_reports)
        rapor.add_separator()
        rapor.add_command(label="PDF raporu", command=lambda: self.export_report("pdf"))
        rapor.add_command(label="Word raporu", command=lambda: self.export_report("docx"))
        rapor.add_command(label="TXT raporu", command=lambda: self.export_report("txt"))
        rapor.add_command(label="CSV tablo", command=self.export_results)
        rapor.add_separator()
        rapor.add_command(label="Konu notunu arşivle", command=self.save_research_note)
        rapor.add_command(label="Rapor listesini yenile", command=self.refresh_reports)
        menubar.add_cascade(label="Rapor", menu=rapor)

        gorunum = tk.Menu(menubar, tearoff=0)
        gorunum.add_command(label="1 · Kaynak ekle ve seç", accelerator="Ctrl+1",
                            command=lambda: self.show_step(0))
        gorunum.add_command(label="2 · Ara", accelerator="Ctrl+2",
                            command=lambda: self.show_step(1))
        gorunum.add_command(label="3 · Sonuç ve rapor", accelerator="Ctrl+3",
                            command=lambda: self.show_step(2))
        gorunum.add_separator()
        gorunum.add_command(label="Ayarlar…", command=self.open_settings)
        menubar.add_cascade(label="Görünüm", menu=gorunum)

        yardim = tk.Menu(menubar, tearoff=0)
        yardim.add_command(label="Hakkında", command=self.show_about)
        menubar.add_cascade(label="Yardım", menu=yardim)

        self.config(menu=menubar)
        self.menubar = menubar      # menü çubuğuna referans tutulmazsa çöp toplanabilir
        self.bind("<Control-o>", lambda _e: self.add_sources())
        self.bind("<Control-g>", lambda _e: self.open_input_dialog())
        self.bind("<Control-q>", lambda _e: self.on_close())
        self.bind("<Control-r>", lambda _e: self.open_reports())
        self.bind("<Control-Key-1>", lambda _e: self.show_step(0))
        self.bind("<Control-Key-2>", lambda _e: self.show_step(1))
        self.bind("<Control-Key-3>", lambda _e: self.show_step(2))
        self.bind("<Control-Return>", lambda _e: self.run_search())
        self.bind("<Control-Shift-Return>", lambda _e: self.ai_smart_search())

    def _build_reports_tab(self, notebook):
        tab = ttk.Frame(notebook)
        self.reports_tab = tab
        notebook.add(tab, text="  Raporlar  ")
        head = ttk.Frame(tab, padding=(10, 10, 10, 0))
        head.pack(fill="x")
        ttk.Label(head, text="OLUŞTURULAN RAPORLAR", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(head, text="Klasörü aç", command=self.open_reports_folder).pack(side="right", padx=3)
        ttk.Button(head, text="Yenile", command=self.refresh_reports).pack(side="right", padx=3)
        ttk.Button(head, text="Sil", command=self.delete_report).pack(side="right", padx=3)
        ttk.Button(head, text="Aç", command=self.open_report).pack(side="right", padx=3)
        self.report_count_var = tk.StringVar(value="")
        ttk.Label(tab, textvariable=self.report_count_var, foreground="#555",
                  padding=(10, 4)).pack(anchor="w")
        cols = ("kind", "size", "modified", "name")
        self.report_tree = ttk.Treeview(tab, columns=cols, show="headings", height=14)
        for col, title, width in [("kind", "Tür", 150), ("size", "Boyut", 90),
                                  ("modified", "Oluşturulma", 160), ("name", "Dosya adı", 560)]:
            self.report_tree.heading(col, text=title)
            self.report_tree.column(col, width=width, anchor="w")
        self.report_tree.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.report_tree.bind("<Double-1>", lambda _e: self.open_report())
        ttk.Label(tab, text="Listeden bir rapora çift tıklayarak açabilirsiniz. Yeni raporlar "
                            "Arama sekmesindeki 'PDF / Word / TXT raporu' düğmeleriyle üretilir.",
                  foreground="#555", padding=(10, 0, 10, 10)).pack(anchor="w")

    def refresh_reports(self):
        """exports klasörünü tarayıp rapor listesini günceller."""
        self.report_tree.delete(*self.report_tree.get_children())
        reports = list_reports()
        for i, r in enumerate(reports):
            self.report_tree.insert("", "end", iid=str(i),
                values=(r["kind"], human_size(r["size"]),
                        r["modified"].strftime("%Y-%m-%d %H:%M"), r["name"]))
        self.report_list = reports
        if reports:
            self.report_count_var.set(f"{len(reports)} rapor bulundu — en yeni: {reports[0]['name']}")
        else:
            self.report_count_var.set("Henüz rapor oluşturulmadı. Arama sekmesinden rapor üretebilirsiniz.")
        return reports

    def _selected_report(self):
        sel = self.report_tree.selection()
        if not sel:
            messagebox.showinfo("Raporlar", "Listeden bir rapor seçin.")
            return None
        return self.report_list[int(sel[0])]

    def open_report(self):
        r = self._selected_report()
        if not r:
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(r["path"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(r["path"])])
            else:
                subprocess.Popen(["xdg-open", str(r["path"])])
        except Exception as exc:
            messagebox.showerror("Rapor açılamadı", str(exc))

    def delete_report(self):
        r = self._selected_report()
        if not r:
            return
        if not messagebox.askyesno("Raporu sil", f"'{r['name']}' silinsin mi?"):
            return
        try:
            r["path"].unlink()
        except Exception as exc:
            messagebox.showerror("Rapor silinemedi", str(exc))
            return
        self.refresh_reports()

    def open_reports_folder(self):
        """Raporların bulunduğu klasörü dosya yöneticisinde açar."""
        from exporter import EXPORT_DIR
        try:
            if sys.platform.startswith("win"):
                os.startfile(EXPORT_DIR)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(EXPORT_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(EXPORT_DIR)])
        except Exception as exc:
            messagebox.showinfo("Rapor klasörü", f"Klasör açılamadı.\nYol: {EXPORT_DIR}\n{exc}")

    def show_about(self):
        messagebox.showinfo(
            "Hakkında",
            f"Bilgi Araştırma — Kaynaklı Yerel Arama\nSürüm {APP_VERSION}\n\n"
            "PDF, Word, TXT, resim (OCR) ve web kaynaklarında arama;\n"
            "isteğe bağlı yerel Ollama modeliyle konu notu ve akıllı arama.\n\n"
            "Tüm veriler bilgisayarınızda kalır; internet gerekmez.")

    def get_query(self):
        """Çok satırlı girdi kutusundaki sorguyu döndürür."""
        return self.query_entry.get("1.0", "end").strip()

    def set_query(self, text):
        self.query_entry.delete("1.0", "end")
        self.query_entry.insert("1.0", text or "")

    def open_input_dialog(self):
        """Girdiyi farklı kaynaklardan alma penceresi."""
        InputSourceDialog(self)

    def _append_query(self, text, replace=False):
        if not text:
            return
        if replace or not self.get_query():
            self.set_query(text)
        else:
            self.query_entry.insert("end", "\n" + text)
        self.status_var.set("Girdi güncellendi.")

    def add_sources(self):
        paths = filedialog.askopenfilenames(
            title="Kaynak dosyalarını seç",
            filetypes=[("Desteklenen kaynaklar", "*.pdf *.docx *.txt *.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
                       ("Tüm dosyalar", "*.*")]
        )
        if not paths: return
        self.status_var.set("Kaynaklar ekleniyor ve metinleri çıkarılıyor…")
        self.configure(cursor="watch")
        def worker():
            msgs = []
            for p in paths:
                try:
                    _, msg = add_file(p, self.settings.get("tesseract_path", ""),
                                      self.settings.get("ocr_lang", "tur+eng"))
                    msgs.append(f"{Path(p).name}: {msg}")
                except NameConflictError as exc:
                    # Aynı adda kayıt var: yeniden adlandırma diyaloğu ana iş
                    # parçacığında açılmalı, bu yüzden kararı oraya taşırız.
                    new_name = self._ask_rename(exc)
                    if not new_name:
                        msgs.append(f"{Path(p).name}: işlem iptal edildi.")
                        continue
                    try:
                        _, msg = add_file(p, self.settings.get("tesseract_path", ""),
                                          self.settings.get("ocr_lang", "tur+eng"),
                                          display_name=new_name)
                        msgs.append(f"{Path(p).name} → {new_name}: {msg}")
                    except Exception as exc2:
                        msgs.append(f"{Path(p).name}: HATA - {exc2}")
                except Exception as exc:
                    msgs.append(f"{Path(p).name}: HATA - {exc}")
                    with open(LOG_DIR / "errors.log", "a", encoding="utf-8") as log:
                        log.write(traceback.format_exc() + "\n")
            self.after(0, lambda: self.finish_ingest(msgs))
        threading.Thread(target=worker, daemon=True).start()

    def _ask_rename(self, conflict):
        """Ana iş parçacığından yeniden adlandırma diyaloğunu çalıştırır."""
        result = {}
        done = threading.Event()
        def ask():
            result["name"] = self._rename_conflict(conflict)
            done.set()
        self.after(0, ask)
        done.wait(timeout=600)
        return result.get("name")

    def finish_ingest(self, msgs):
        self.configure(cursor="")
        self.status_var.set("Kaynak ekleme tamamlandı.")
        self.refresh_documents()
        messagebox.showinfo("Kaynak ekleme", "\n".join(msgs[:30]))

    def refresh_documents(self):
        """Her iki listeyi (yeni çalışma ve arşiv) tazeler."""
        self.doc_tree.delete(*self.doc_tree.get_children())
        active = self.settings.get("active_document_ids")
        for d in database.list_study_documents():
            mark = "✓" if active is None or d["id"] in active else ""
            self.doc_tree.insert("", "end", iid=str(d["id"]), text=d["name"],
                                 values=(mark, d["file_type"], d["chunk_count"]))
        self.archive_tree.delete(*self.archive_tree.get_children())
        for d in database.list_archive_documents():
            self.archive_tree.insert("", "end", iid=str(d["id"]), text=d["name"],
                                     values=(d["file_type"], d["chunk_count"]))
        self.scope_summary_var.set(
            f"Aramada: {self.active_scope_text()} · Arşivde: {len(database.list_archive_documents())} kaynak")
        self.refresh_step_hints()

    def on_doc_click(self, event):
        """'Aramada' sütununa tıklanınca kaynağı aramaya dâhil eder / çıkarır."""
        if self.doc_tree.identify_region(event.x, event.y) != "cell":
            return
        if self.doc_tree.identify_column(event.x) != "#1":   # yalnızca "Aramada"
            return
        row = self.doc_tree.identify_row(event.y)
        if not row:
            return
        self.toggle_document(int(row))
        return "break"

    def toggle_document(self, doc_id):
        self.settings["active_document_ids"] = toggle_selection(
            self.settings.get("active_document_ids"),
            [d["id"] for d in database.list_study_documents()], doc_id)
        self.save_settings_file()
        self.refresh_documents()
        self.status_var.set(f"Aramaya dâhil kaynak: {self.active_scope_text()}")

    def set_all_documents(self, flag):
        self.settings["active_document_ids"] = None if flag else []
        self.save_settings_file()
        self.refresh_documents()
        self.status_var.set(f"Aramaya dâhil kaynak: {self.active_scope_text()}")

    def active_document_ids(self):
        """Aramada kullanılacak belge kimlikleri; None ise tümü."""
        return resolve_scope(self.settings.get("active_document_ids"),
                             [d["id"] for d in database.list_study_documents()])

    def active_scope_text(self):
        return scope_text(self.active_document_ids(), len(database.list_study_documents()))

    # --- Arşiv <-> çalışma listesi --------------------------------------

    def add_archive_selected_to_study(self, doc_ids=None):
        """Arşivdeki kaynakları aramaya ekler (çalışma listesine alır)."""
        ids = doc_ids if doc_ids is not None else self._selected_ids(self.archive_tree)
        if not ids:
            messagebox.showinfo("Döküman arşivi",
                                "Önce arşivden bir kaynak seçin ya da sürükleyip yukarı bırakın.")
            return
        # Kaynak ya aramada ya arşivde bulunur; iki listede birden görünmez.
        database.set_in_study(ids, True)
        database.set_in_archive(ids, False)
        # Yeni eklenenler aramada işaretli olsun.
        current = self.settings.get("active_document_ids")
        if current is not None:
            for i in ids:
                if i not in current:
                    current.append(i)
            self.save_settings_file()
        self.refresh_documents()
        self.status_var.set(f"{len(ids)} kaynak aramaya eklendi.")

    def archive_selected(self):
        """Çalışma listesindeki kaynakları arşive taşır."""
        return self.archive_selected_from_ids(self._selected_ids(self.doc_tree))

    def archive_selected_from_ids(self, ids):
        if not ids:
            messagebox.showinfo("Arşive ekle", "Önce üst listeden en az bir kaynak seçin.")
            return
        database.set_in_archive(ids, True)
        database.set_in_study(ids, False)
        self.refresh_documents()
        self.status_var.set(f"{len(ids)} kaynak arşive eklendi.")

    def remove_archive_selected(self):
        """Seçili kaynakları arşivden çıkarır (arşiv listesinden kaldırır)."""
        return self.remove_archive_selected_from_ids(self._selected_ids(self.archive_tree))

    def remove_archive_selected_from_ids(self, ids):
        if not ids:
            messagebox.showinfo("Arşivden çıkar", "Önce arşivden en az bir kaynak seçin.")
            return
        database.set_in_archive(ids, False)
        self.refresh_documents()
        self.status_var.set(f"{len(ids)} kaynak arşivden çıkarıldı.")

    # --- Sürükle-bırak: arşivden aramaya --------------------------------

    def _archive_drag_start(self, event):
        """Arşiv listesinde basılan satırı sürükleme adayı olarak işaretler."""
        self._drag_ids = self._selected_ids(self.archive_tree) or (
            [int(self.archive_tree.identify_row(event.y))]
            if self.archive_tree.identify_row(event.y) else [])

    def _archive_drag_drop(self, event):
        """Bırakma noktası üst listedeyse seçili arşiv kaynaklarını ekler."""
        ids = getattr(self, "_drag_ids", [])
        self._drag_ids = []
        if not ids:
            return
        target = self.winfo_containing(event.x_root, event.y_root)
        if target is self.doc_tree or self._is_descendant(target, self.study_section):
            self.add_archive_selected_to_study(ids)

    @staticmethod
    def _is_descendant(widget, ancestor):
        while widget is not None:
            if widget is ancestor:
                return True
            widget = getattr(widget, "master", None)
        return False

    @staticmethod
    def _selected_ids(tree):
        return [int(i) for i in tree.selection()]

    def delete_selected(self):
        """Seçili kaynakları toplu olarak siler."""
        return self.delete_selected_ids(self._selected_ids(self.doc_tree))

    def delete_selected_ids(self, sel):
        if not sel:
            messagebox.showinfo("Kaynağı sil", "Önce üst listeden en az bir kaynak seçin.")
            return
        if not messagebox.askyesno("Kaynakları sil",
                                   f"{len(sel)} kaynak veritabanından ve arşiv klasöründen silinsin mi?"):
            return
        for doc_id in sel:
            stored = database.delete_document(doc_id)
            if stored:
                try: Path(stored).unlink(missing_ok=True)
                except Exception: pass
        remaining = [d["id"] for d in database.list_study_documents()]
        self.settings["active_document_ids"] = selection_after_delete(
            self.settings.get("active_document_ids"), sel, remaining)
        self.save_settings_file()
        self.refresh_documents()
        self.status_var.set(f"{len(sel)} kaynak silindi.")

    def _rename_conflict(self, conflict):
        """Ad çakışmasında yeniden adlandırma diyaloğunu açar; yeni adı döndürür."""
        return RenameDialog(self, conflict).result

    def run_search(self):
        q = self.get_query()
        if not q:
            messagebox.showwarning("Arama", "Bir soru veya anahtar kelime yazın.")
            return
        self.status_var.set("Aranıyor…")
        self.result_tree.delete(*self.result_tree.get_children())
        self.detail.delete("1.0", "end")
        self.all_terms_var_value, self.min_coverage_value = match_from_label(self.match_var.get())
        self.ignore_turkish_case_value = not self.turkish_sensitive_var.get()
        # Kaynak seçimi: yalnızca işaretli kaynaklarda ara. Hiçbiri seçili
        # değilse sessizce boş sonuç yerine kullanıcıyı uyar.
        scope = self.active_document_ids()
        if scope == []:
            messagebox.showwarning("Kaynak seçimi",
                                   "Hiçbir kaynak seçili değil. Sol listedeki 'Aramada' "
                                   "sütunundan en az bir kaynak seçin.")
            return
        def worker():
            try:
                sid, results = search(q, all_terms=self.all_terms_var_value,
                                      min_coverage=self.min_coverage_value,
                                      ignore_turkish_case=self.ignore_turkish_case_value,
                                      document_ids=scope)
                self.after(0, lambda: self.finish_search(sid, results))
            except Exception as exc:
                err = str(exc)
                self.after(0, lambda: messagebox.showerror("Arama hatası", err))
                self.after(0, lambda: self.status_var.set("Arama başarısız."))
        threading.Thread(target=worker, daemon=True).start()

    def finish_search(self, sid, results):
        self.last_search_id, self.last_results = sid, results
        for i, r in enumerate(results):
            preview = " ".join(r["text"].split())
            if len(preview) > 300: preview = preview[:300] + "…"
            self.result_tree.insert("", "end", iid=str(i),
                values=(r["document_name"], r["location"], f'{r["score"]:.2f}', preview))
        self.status_var.set(f"{len(results)} ilgili metin bölümü bulundu "
                            f"({self.active_scope_text()}).")
        self.refresh_history()
        self.refresh_step_hints()
        if results and self.current_step == 1:
            self.status_var.set(self.status_var.get() + " Sonuçları görmek için “İleri”ye geçin.")

    def show_selected_result(self, _event=None):
        sel = self.result_tree.selection()
        if not sel: return
        idx = int(sel[0])
        self.selected_result_index = idx
        r = self.last_results[idx]
        self.detail.delete("1.0", "end")
        self.detail.insert("end", f"Kaynak: {r['document_name']}\nKonum: {r['location']}\n\n{r['text']}")
        with db() as con:
            row = con.execute("SELECT note FROM results WHERE search_id=? AND chunk_id=?",
                              (self.last_search_id, r["chunk_id"])).fetchone()
        self.note_entry.delete(0, "end")
        self.note_entry.insert(0, row["note"] if row else "")

    def save_note(self):
        sel = self.result_tree.selection()
        if not sel or self.last_search_id is None: 
            messagebox.showinfo("Not", "Önce bir arama sonucu seçin.")
            return
        r = self.last_results[int(sel[0])]
        note = self.note_entry.get()
        with db() as con:
            con.execute("UPDATE results SET note=? WHERE search_id=? AND chunk_id=?",
                        (note, self.last_search_id, r["chunk_id"]))
            con.execute("""INSERT INTO notes(document_id, chunk_id, title, body, updated_at)
                VALUES (?, ?, ?, ?, datetime('now','localtime'))""",
                (r["document_id"], r["chunk_id"], r["document_name"] + " - " + r["location"], note))
            con.commit()
        self.status_var.set("Not veritabanına kaydedildi.")

    def ollama_options(self):
        """Ayarlardan Ollama zaman aşımı ve keep_alive değerlerini üretir."""
        try:
            timeout = int(self.settings.get("ollama_timeout", 300))
        except (TypeError, ValueError):
            timeout = 300
        return {"read_timeout": max(30, timeout),
                "keep_alive": self.settings.get("ollama_keep_alive", "30m"),
                "host": self.settings.get("ollama_host", "http://localhost:11434")}

    def ai_smart_search(self):
        """Ollama ile sorguyu genişletip adayları anlamsal ilgiye göre sıralar."""
        q = self.get_query()
        if not q:
            messagebox.showwarning("Akıllı arama", "Bir soru veya anahtar kelime yazın.")
            return
        model = self.settings.get("ollama_model", "qwen2.5:3b")
        embed_model = self.settings.get("ollama_embed_model", "nomic-embed-text")
        fast = bool(self.fast_smart_var.get())
        try:
            min_score = float(self.settings.get("ai_min_score", 3))
        except (TypeError, ValueError):
            min_score = 3.0
        opts = self.ollama_options()
        self.status_var.set("Akıllı arama: Ollama kontrol ediliyor…")
        self.result_tree.delete(*self.result_tree.get_children())
        self.detail.delete("1.0", "end")
        ignore_case = not self.turkish_sensitive_var.get()

        def worker():
            try:
                # Uzun bir isteğe başlamadan önce hızlı ön kontrol: sunucu ayakta mı,
                # model yüklü mü? Böylece kullanıcı dakikalarca bekletilmez.
                # Hızlı modda metin üretilmediği için üretim modeli aranmaz.
                needed = embed_model if fast else model
                status = check_ollama(model=needed, host=opts["host"])
                if not status["ok"] or not status["model_present"]:
                    self.after(0, lambda: messagebox.showerror("Akıllı arama", status["message"]))
                    self.after(0, lambda: self.status_var.set("Akıllı arama: Ollama hazır değil."))
                    return
                concepts, warning, warnings = [], "", []
                if not fast:
                    self.after(0, lambda: self.status_var.set(
                        f"Akıllı arama: {model} sorudan kavramlar çıkarıyor…"))
                    try:
                        expanded = expand_query(q, model=model, **opts)
                        if expanded and expanded["kavramlar"]:
                            concepts = expanded["kavramlar"]
                    except OllamaError as exc:
                        warning = f"Sorgu genişletilemedi ({exc}); özgün sorguyla devam edildi. "
                # Geniş aday havuzu: özgün sorgu + modelin çıkardığı kavramlar.
                merged, seen = [], set()
                for probe in [q, " ".join(concepts)]:
                    if not probe.strip():
                        continue
                    _, found = search(probe, ignore_turkish_case=ignore_case,
                                      document_ids=self.active_document_ids())
                    for r in found:
                        if r["chunk_id"] not in seen:
                            seen.add(r["chunk_id"])
                            merged.append(r)
                if not merged:
                    self.after(0, lambda: self.finish_smart_search([], warning, concepts))
                    return

                def report(done, total):
                    self.after(0, lambda: self.status_var.set(
                        f"Akıllı arama: {model} ilgi puanlıyor… {done}/{total}"))

                def warn(text):
                    warnings.append(text)

                if fast:
                    # Gömme ile sıralama: metin üretilmez, vektör karşılaştırılır.
                    # Bu yüzden yavaş bilgisayarlarda bile saniyeler sürer.
                    self.after(0, lambda: self.status_var.set(
                        f"Akıllı arama (hızlı): {embed_model} benzerlik hesaplıyor…"))
                    ranked = rank_by_embedding(
                        q, merged, model=embed_model, host=opts.get("host", "http://localhost:11434"),
                        read_timeout=opts["read_timeout"],
                        progress=lambda n: self.after(0, lambda: self.status_var.set(
                            f"Akıllı arama (hızlı): {n} parça vektörlendi…")))
                else:
                    ranked = rank_by_relevance(q, merged, model=model, progress=report,
                                               on_warning=warn, **opts)
                if warnings:
                    warning += " ".join(warnings) + " "
                # 0 puanlı ilgisiz parçalar listeyi doldurup asıl kaynağı gizler.
                before = len(ranked)
                ranked = filter_by_score(ranked, min_score=min_score)
                if before and not ranked:
                    warning += "Hiçbir parça ilgi eşiğini geçemedi; eşiği düşürmeyi deneyin. "
                self.after(0, lambda: self.finish_smart_search(ranked, warning, concepts))
            except OllamaError as exc:
                msg = str(exc)
                self.after(0, lambda: messagebox.showerror("Akıllı arama", msg))
                self.after(0, lambda: self.status_var.set("Akıllı arama başarısız."))
            except Exception as exc:
                err = "Beklenmeyen hata: " + str(exc)
                self.after(0, lambda: messagebox.showerror("Akıllı arama", err))
                self.after(0, lambda: self.status_var.set("Akıllı arama başarısız."))
        threading.Thread(target=worker, daemon=True).start()

    def finish_smart_search(self, results, warning, concepts):
        self.last_results = results
        # Akıllı arama sonuçları da normal arama gibi kaydedilir; böylece not
        # ekleme ve geçmiş çalışmaya devam eder.
        with db() as con:
            cur = con.execute("INSERT INTO searches(query, created_at) VALUES (?, datetime('now','localtime'))",
                              ("[Akıllı] " + (self.get_query() or ""),))
            self.last_search_id = cur.lastrowid
            con.executemany("INSERT INTO results(search_id, chunk_id, score) VALUES (?, ?, ?)",
                            [(self.last_search_id, r["chunk_id"], r.get("ai_score") or 0.0) for r in results])
            con.commit()
        unscored = 0
        for i, r in enumerate(results):
            preview = " ".join(r["text"].split())
            if len(preview) > 300:
                preview = preview[:300] + "…"
            score = r.get("ai_score")
            if score is None:
                unscored += 1
                label = "—"
            else:
                label = f"{score:.0f}"
            self.result_tree.insert("", "end", iid=str(i),
                values=(r["document_name"], r["location"], label, preview))
        note = f" ({', '.join(concepts)})" if concepts else ""
        extra = f" {unscored} parça puanlanamadı." if unscored else ""
        self.status_var.set(warning + f"{len(results)} bölüm anlamsal ilgiye göre sıralandı{note}.{extra}")
        self.refresh_history()

    def ai_explain(self):
        if not self.last_results:
            messagebox.showinfo("Açıklama", "Önce arama yapın ve ilgili kaynakları bulun.")
            return
        model = self.settings.get("ollama_model", "qwen2.5:3b")
        opts = self.ollama_options()
        q = self.get_query()
        self.status_var.set(f"Yerel model yanıtı bekleniyor: {model}")
        def worker():
            try:
                status = check_ollama(model=model)
                if not status["ok"] or not status["model_present"]:
                    answer = status["message"]
                else:
                    def report(chars):
                        self.after(0, lambda: self.status_var.set(
                            f"Yerel model yanıt üretiyor: {model} ({chars} karakter)"))
                    answer = explain_with_ollama(q, self.last_results, model=model,
                                                 mode=self.mode_var.get(), progress=report, **opts)
            except OllamaError as exc:
                answer = str(exc)
            except Exception as exc:
                answer = "Beklenmeyen hata: " + str(exc)
            self.after(0, lambda: self.show_ai_answer(answer))
        threading.Thread(target=worker, daemon=True).start()

    def show_ai_answer(self, answer):
        self.current_ai_answer = answer
        self.detail.delete("1.0", "end")
        self.detail.insert("end", answer)
        self.status_var.set("Konu notu hazır. Metni düzenleyebilir ve arşivleyebilirsiniz.")

    def save_research_note(self):
        body = self.detail.get("1.0", "end").strip()
        query = self.get_query()
        if not body or not query:
            messagebox.showinfo("Konu notunu arşivle", "Önce arama yapıp Ollama ile bir konu notu oluşturun.")
            return
        sources = "\n".join(f"{r['document_name']} — {r['location']}" for r in self.last_results[:50])
        with db() as con:
            con.execute("INSERT INTO research_notes(query, mode, body, sources, created_at) VALUES (?, ?, ?, ?, datetime('now','localtime'))",
                        (query, self.mode_var.get(), body, sources))
            con.commit()
        exports = ROOT / "exports"
        exports.mkdir(exist_ok=True)
        from datetime import datetime
        safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in query).strip()[:60] or "Konu_Notu"
        path = exports / f"Konu_Notu_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path.write_text(f"Girdi: {query}\nAraştırma türü: {self.mode_var.get()}\nOluşturulma: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{body}\n\n--- Aramada bulunan kaynaklar ---\n{sources}\n", encoding="utf-8")
        self.status_var.set("Konu notu veritabanına ve Raporlar sekmesine kaydedildi.")
        self.refresh_reports()
        messagebox.showinfo("Konu notu arşivlendi", f"Not kalıcı olarak kaydedildi:\n{path}")

    def export_report(self, fmt):
        if not self.last_results and not self.detail.get("1.0", "end").strip():
            messagebox.showinfo("Rapor oluştur", "Önce arama yapın veya konu notu oluşturun.")
            return
        query = self.get_query() or "Konu_Notu"
        try:
            path = export_results(self.last_results, fmt=fmt, query=query,
                                  mode=self.mode_var.get(),
                                  ai_answer=self.detail.get("1.0", "end").strip() if self.current_ai_answer else "")
            messagebox.showinfo("Rapor hazır", f"Tek dosyalı rapor oluşturuldu:\n{path}\n\n"
                                                f"Dosya, Raporlar sekmesinden de açılabilir.")
            self.refresh_reports()
        except Exception as exc:
            messagebox.showerror("Rapor oluşturulamadı", f"{fmt.upper()} dışa aktarma hatası:\n{exc}")

    def export_results(self):
        if not self.last_results:
            messagebox.showinfo("Dışa aktar", "Önce arama yapın.")
            return
        path = export_csv(self.last_results)
        messagebox.showinfo("Dışa aktar", f"CSV dosyası oluşturuldu:\n{path}")
        self.refresh_reports()

    def open_source(self):
        sel = self.result_tree.selection()
        if not sel: return
        row = self.last_results[int(sel[0])]
        url = (row.get("source_url") or "").strip()
        path = url or row["stored_path"]
        try:
            if url:
                self._open_url(url)
            elif sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            messagebox.showerror("Dosya açılamadı", str(exc))

    def _open_url(self, url):
        import webbrowser
        if not webbrowser.open(url):
            raise RuntimeError("Tarayıcı açılamadı: " + url)

    def on_turkish_toggle(self):
        self.settings["turkish_sensitive"] = bool(self.turkish_sensitive_var.get())
        self.save_settings_file()
        self.status_var.set("Arama Türkçe karakter duyarlı." if self.turkish_sensitive_var.get()
                            else "Arama Türkçe karakter duyarsız (ç/ğ/ı/ş... eşitlenir).")

    def on_fast_toggle(self):
        self.settings["ai_fast_mode"] = bool(self.fast_smart_var.get())
        self.save_settings_file()
        self.status_var.set("Akıllı arama hızlı modda (gömme benzerliği)." if self.fast_smart_var.get()
                            else "Akıllı arama model puanlamasıyla (yavaş, daha ayrıntılı).")

    def on_match_change(self):
        all_terms, coverage = match_from_label(self.match_var.get())
        self.settings["all_terms"] = bool(all_terms)
        self.settings["min_coverage"] = coverage
        self.save_settings_file()
        if all_terms:
            self.status_var.set(f"Eşleşme: terimlerin en az %{int(coverage * 100)} kadarı aranır.")
        else:
            self.status_var.set("Eşleşme: terimlerden herhangi biri yeterli.")

    def refresh_history(self):
        self.history.delete(0, "end")
        self.history_ids = []
        for row in database.list_searches():
            self.history_ids.append(row["id"])
            self.history.insert("end", f'{row["created_at"]} | {row["query"]}')

    def open_history(self, _event=None):
        sel = self.history.curselection()
        if not sel: return
        search_id = self.history_ids[sel[0]]
        with db() as con:
            row = con.execute("SELECT query FROM searches WHERE id=?", (search_id,)).fetchone()
        if row:
            self.set_query(row["query"])
            self.run_search()

    def backup(self):
        try:
            path = backup_project()
            messagebox.showinfo("Yedekleme", f"Yedek oluşturuldu:\n{path}")
            self.refresh_reports()
        except Exception as exc:
            messagebox.showerror("Yedekleme hatası", str(exc))

    def open_settings(self):
        win = tk.Toplevel(self)
        win.title("Ayarlar")
        win.geometry("720x560")
        win.transient(self)
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Tesseract OCR dosya yolu:").grid(row=0, column=0, sticky="w", pady=5)
        tess = tk.StringVar(value=self.settings.get("tesseract_path", ""))
        ttk.Entry(frm, textvariable=tess, width=70).grid(row=1, column=0, sticky="ew")
        ttk.Button(frm, text="Gözat", command=lambda: tess.set(filedialog.askopenfilename())).grid(row=1, column=1, padx=5)
        ttk.Label(frm, text="OCR dilleri (ör. tur+eng):").grid(row=2, column=0, sticky="w", pady=(10, 2))
        lang = tk.StringVar(value=self.settings.get("ocr_lang", "tur+eng"))
        ttk.Entry(frm, textvariable=lang, width=25).grid(row=3, column=0, sticky="w")
        ttk.Label(frm, text="Ollama model adı:").grid(row=4, column=0, sticky="w", pady=(10, 2))
        model = tk.StringVar(value=self.settings.get("ollama_model", "qwen2.5:3b"))
        ttk.Entry(frm, textvariable=model, width=30).grid(row=5, column=0, sticky="w")
        ttk.Label(frm, text="Ollama yanıt süresi (saniye, en az 30):").grid(row=6, column=0, sticky="w", pady=(10, 2))
        timeout = tk.StringVar(value=str(self.settings.get("ollama_timeout", 300)))
        ttk.Entry(frm, textvariable=timeout, width=10).grid(row=7, column=0, sticky="w")
        ttk.Label(frm, text="Yavaş bilgisayarlarda model uzun süre yanıt üretmezse bu değeri artırın.",
                  foreground="#555").grid(row=8, column=0, sticky="w")
        ttk.Label(frm, text="Gömme modeli (hızlı akıllı arama için, ör. nomic-embed-text):").grid(
            row=9, column=0, sticky="w", pady=(10, 2))
        embed = tk.StringVar(value=self.settings.get("ollama_embed_model", "nomic-embed-text"))
        ttk.Entry(frm, textvariable=embed, width=30).grid(row=10, column=0, sticky="w")
        ttk.Label(frm, text="En düşük ilgi puanı (0-10 arası; altındaki sonuçlar gizlenir):").grid(
            row=11, column=0, sticky="w", pady=(10, 2))
        minscore = tk.StringVar(value=str(self.settings.get("ai_min_score", 3)))
        ttk.Entry(frm, textvariable=minscore, width=10).grid(row=12, column=0, sticky="w")
        def save():
            try:
                secs = max(30, int(float(timeout.get().strip())))
            except (TypeError, ValueError):
                secs = 300
            try:
                min_ai = max(0.0, min(10.0, float(minscore.get().strip().replace(",", "."))))
            except (TypeError, ValueError):
                min_ai = 3.0
            self.settings.update({"tesseract_path": tess.get().strip(), "ocr_lang": lang.get().strip() or "tur+eng",
                                  "ollama_model": model.get().strip() or "qwen2.5:3b",
                                  "ollama_embed_model": embed.get().strip() or "nomic-embed-text",
                                  "ai_min_score": min_ai,
                                  "ollama_timeout": secs})
            self.save_settings_file()
            win.destroy()
            messagebox.showinfo("Ayarlar", "Ayarlar kaydedildi.")
        ttk.Button(frm, text="Kaydet", command=save).grid(row=13, column=0, sticky="w", pady=12)

    def on_close(self):
        try:
            with db() as con:
                con.execute("PRAGMA wal_checkpoint(FULL)")
        except Exception:
            pass
        self.destroy()

class RenameDialog(tk.Toplevel):
    """Ad çakışmasında yeni ad isteyen pencere.

    Arşivde aynı isimde bir döküman bulunamaz; kullanıcı yeni bir ad girer
    ya da işlemi iptal eder. `result` yeni adı (iptalde boş dize) tutar.
    """

    def __init__(self, parent, conflict):
        """conflict: ingest.NameConflictError — çakışan kaydı ve öneriyi taşır."""
        super().__init__(parent)
        self.title("Aynı isimde kaynak var")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = ""

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Bu isimde bir kaynak arşivde zaten var:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(body, text=conflict.conflict["name"], foreground="#a33").pack(anchor="w", pady=(2, 8))
        ttk.Label(body, text="Devam etmek için yeni bir ad girin. Aynı isimle iki kaynak "
                             "tutulmaz; bu yüzden işlem yeniden adlandırılmadan sürmez.",
                  wraplength=420, justify="left", foreground="#555").pack(anchor="w")
        self.name_var = tk.StringVar(value=conflict.suggestion)
        entry = ttk.Entry(body, textvariable=self.name_var, width=52)
        entry.pack(fill="x", pady=(8, 2))
        entry.focus_set()
        entry.select_range(0, "end")
        ttk.Label(body, text="Önerilen ad önceden yazıldı; değiştirebilirsiniz.",
                  foreground="#555").pack(anchor="w")
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(12, 0))
        ttk.Button(bar, text="Yeni adla ekle", command=self._accept).pack(side="right")
        ttk.Button(bar, text="İptal", command=self._cancel).pack(side="right", padx=6)
        self.bind("<Return>", lambda _e: self._accept())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.wait_window()

    def _accept(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Ad gerekli", "Lütfen bir ad girin.", parent=self)
            return
        self.result = name
        self.destroy()

    def _cancel(self):
        self.result = ""
        self.destroy()


class InputSourceDialog(tk.Toplevel):
    """Girdiyi dökümandan, resimden, ekrandan veya web adresinden alan pencere."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Girdi kaynağı")
        self.geometry("820x560")
        self.transient(app)
        self.grab_set()
        self.result = ""
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        notebook.add(self._tab_paragraph(notebook), text="Dökümandan paragraf")
        notebook.add(self._tab_image(notebook), text="Resim (OCR)")
        notebook.add(self._tab_screen(notebook), text="Ekran görüntüsü")
        notebook.add(self._tab_web(notebook), text="Web adresi")
        bar = ttk.Frame(self, padding=(10, 0, 10, 10))
        bar.pack(fill="x")
        self.hint = tk.StringVar(value="Seçilen metin arama kutusuna eklenir.")
        ttk.Label(bar, textvariable=self.hint, foreground="#555").pack(side="left")
        ttk.Button(bar, text="Kapat", command=self.destroy).pack(side="right")

    def _preview_box(self, parent, height=12):
        box = tk.Text(parent, height=height, wrap="word", font=("Segoe UI", 10))
        return box

    def _use_text(self, text, replace=False):
        if not text or not text.strip():
            messagebox.showinfo("Girdi kaynağı", "Metin bulunamadı.")
            return
        self.app._append_query(text.strip(), replace=replace)
        self.destroy()

    def _tab_paragraph(self, parent):
        frame = ttk.Frame(parent, padding=10)
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Button(top, text="Döküman seç (PDF/DOCX/TXT)", command=self._choose_document).pack(side="left")
        self.doc_label = tk.StringVar(value="Döküman seçilmedi.")
        ttk.Label(top, textvariable=self.doc_label, foreground="#555").pack(side="left", padx=8)
        ttk.Label(frame, text="Paragraf / bölüm seçin:").pack(anchor="w", pady=(10, 2))
        listbox_frame = ttk.Frame(frame)
        listbox_frame.pack(fill="both", expand=True)
        self.para_list = tk.Listbox(listbox_frame, font=("Segoe UI", 10))
        scroll = ttk.Scrollbar(listbox_frame, orient="vertical", command=self.para_list.yview)
        self.para_list.configure(yscrollcommand=scroll.set)
        self.para_list.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.para_list.bind("<<ListboxSelect>>", self._show_paragraph)
        self.para_blocks = []
        ttk.Label(frame, text="Seçilen paragraf:").pack(anchor="w", pady=(8, 2))
        self.para_preview = self._preview_box(frame, height=8)
        self.para_preview.pack(fill="both", expand=True)
        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Arama kutusuna aktar",
                   command=lambda: self._use_text(self.para_preview.get("1.0", "end"))).pack(side="left")
        ttk.Button(btns, text="Kaynak olarak arşive ekle",
                   command=lambda: self._archive(self.para_preview.get("1.0", "end"))).pack(side="left", padx=6)
        return frame

    def _choose_document(self):
        path = filedialog.askopenfilename(
            title="Döküman seç",
            filetypes=[("Dökümanlar", "*.pdf *.docx *.txt"), ("Tüm dosyalar", "*.*")])
        if not path:
            return
        try:
            from text_sources import list_paragraphs, preview
            blocks = list_paragraphs(path)
        except Exception as exc:
            messagebox.showerror("Döküman", f"Metin çıkarılamadı:\n{exc}")
            return
        if not blocks:
            messagebox.showinfo("Döküman", "Bu dökümanda metin bulunamadı.")
            return
        self.para_blocks = blocks
        self.para_list.delete(0, "end")
        for loc, text in blocks:
            self.para_list.insert("end", f"[{loc}] {preview(text)}")
        self.doc_label.set(f"{Path(path).name} — {len(blocks)} bölüm")

    def _show_paragraph(self, _event=None):
        sel = self.para_list.curselection()
        if not sel:
            return
        text = self.para_blocks[sel[0]][1]
        self.para_preview.delete("1.0", "end")
        self.para_preview.insert("1.0", text)

    def _tab_image(self, parent):
        frame = ttk.Frame(parent, padding=10)
        ttk.Button(frame, text="Resim seç (PNG/JPG/BMP/TIFF)", command=self._choose_image).pack(anchor="w")
        self.image_label = tk.StringVar(value="Resim seçilmedi. OCR için Tesseract gerekir.")
        ttk.Label(frame, textvariable=self.image_label, foreground="#555").pack(anchor="w", pady=6)
        self.image_preview = self._preview_box(frame, height=14)
        self.image_preview.pack(fill="both", expand=True)
        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Arama kutusuna aktar",
                   command=lambda: self._use_text(self.image_preview.get("1.0", "end"))).pack(side="left")
        ttk.Button(btns, text="Kaynak olarak arşive ekle",
                   command=lambda: self._archive(self.image_preview.get("1.0", "end"), "Resim (OCR)")).pack(side="left", padx=6)
        return frame

    def _choose_image(self):
        path = filedialog.askopenfilename(
            title="Resim seç",
            filetypes=[("Resimler", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("Tüm dosyalar", "*.*")])
        if not path:
            return
        self._run_ocr(lambda: self._image_text(path), self.image_preview, Path(path).name)

    def _image_text(self, path):
        from text_sources import image_file_text
        return image_file_text(path, lang=self.app.settings.get("ocr_lang", "tur+eng"),
                               tesseract_path=self.app.settings.get("tesseract_path", ""))

    def _tab_screen(self, parent):
        frame = ttk.Frame(parent, padding=10)
        ttk.Label(frame, text="Ekranın tamamı veya seçtiğiniz bir bölge OCR ile metne çevrilir.",
                  foreground="#555").pack(anchor="w")
        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Tüm ekranı yakala", command=lambda: self._capture(None)).pack(side="left")
        ttk.Button(btns, text="Bölge seç ve yakala", command=self._capture_region).pack(side="left", padx=6)
        self.screen_preview = self._preview_box(frame, height=14)
        self.screen_preview.pack(fill="both", expand=True)
        btns2 = ttk.Frame(frame)
        btns2.pack(fill="x", pady=6)
        ttk.Button(btns2, text="Arama kutusuna aktar",
                   command=lambda: self._use_text(self.screen_preview.get("1.0", "end"))).pack(side="left")
        ttk.Button(btns2, text="Kaynak olarak arşive ekle",
                   command=lambda: self._archive(self.screen_preview.get("1.0", "end"), "Ekran görüntüsü")).pack(side="left", padx=6)
        return frame

    def _capture_region(self):
        self.withdraw()
        self.update()
        region = RegionSelector(self).select()
        self.deiconify()
        if region:
            self._capture(region)

    def _capture(self, region):
        self._run_ocr(lambda: self._screen_text(region), self.screen_preview, "ekran görüntüsü")

    def _screen_text(self, region):
        from text_sources import capture_screen_text
        return capture_screen_text(lang=self.app.settings.get("ocr_lang", "tur+eng"),
                                   tesseract_path=self.app.settings.get("tesseract_path", ""),
                                   region=region)

    def _run_ocr(self, func, target, label):
        self.hint.set(f"{label}: OCR çalışıyor…")
        self.configure(cursor="watch")
        def worker():
            try:
                text = func()
            except Exception as exc:
                err = str(exc)
                self.after(0, lambda: self._ocr_failed(err))
                return
            self.after(0, lambda: self._ocr_done(text, target, label))
        threading.Thread(target=worker, daemon=True).start()

    def _ocr_done(self, text, target, label):
        self.configure(cursor="")
        self.hint.set("Seçilen metin arama kutusuna eklenir.")
        if not text.strip():
            messagebox.showinfo("OCR", f"{label}: metin bulunamadı.")
            return
        target.delete("1.0", "end")
        target.insert("1.0", text)

    def _ocr_failed(self, message):
        self.configure(cursor="")
        self.hint.set("Seçilen metin arama kutusuna eklenir.")
        messagebox.showerror("OCR hatası", message)

    def _tab_web(self, parent):
        frame = ttk.Frame(parent, padding=10)
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Label(row, text="Adres:").pack(side="left")
        self.url_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.url_var)
        entry.pack(side="left", fill="x", expand=True, padx=6)
        entry.bind("<Return>", lambda _e: self._fetch_url())
        ttk.Button(row, text="Getir", command=self._fetch_url).pack(side="left")
        self.web_label = tk.StringVar(value="http:// veya https:// ile başlayan bir adres girin.")
        ttk.Label(frame, textvariable=self.web_label, foreground="#555").pack(anchor="w", pady=6)
        self.web_preview = self._preview_box(frame, height=14)
        self.web_preview.pack(fill="both", expand=True)
        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Arama kutusuna aktar",
                   command=lambda: self._use_text(self.web_preview.get("1.0", "end"))).pack(side="left")
        ttk.Button(btns, text="Kaynağı arşive ekle",
                   command=self._archive_url).pack(side="left", padx=6)
        return frame

    def _fetch_url(self):
        url = self.url_var.get().strip()
        if not url:
            return
        self.web_label.set("Sayfa indiriliyor…")
        self.configure(cursor="watch")
        def worker():
            try:
                from text_sources import fetch_url_text
                text = fetch_url_text(url)
            except Exception as exc:
                err = str(exc)
                self.after(0, lambda: self._fetch_failed(err))
                return
            self.after(0, lambda: self._fetch_done(text))
        threading.Thread(target=worker, daemon=True).start()

    def _fetch_done(self, text):
        self.configure(cursor="")
        self.web_label.set(f"{len(text)} karakter indirildi.")
        self.web_preview.delete("1.0", "end")
        self.web_preview.insert("1.0", text)

    def _fetch_failed(self, message):
        self.configure(cursor="")
        self.web_label.set("Adres getirilemedi.")
        messagebox.showerror("Web adresi", message)

    def _archive(self, text, name="Girdi"):
        if not text.strip():
            messagebox.showinfo("Arşiv", "Eklenecek metin yok.")
            return
        try:
            from ingest import add_text
            _, msg = add_text(text.strip(), name=name)
        except Exception as exc:
            messagebox.showerror("Arşiv", str(exc))
            return
        self.app.refresh_documents()
        messagebox.showinfo("Arşiv", msg)

    def _archive_url(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo("Arşiv", "Önce bir adres girin.")
            return
        try:
            from ingest import add_url
            _, msg = add_url(url)
        except Exception as exc:
            messagebox.showerror("Arşiv", str(exc))
            return
        self.app.refresh_documents()
        messagebox.showinfo("Arşiv", msg)


class RegionSelector(tk.Toplevel):
    """Ekrandan fare ile dikdörtgen bölge seçtiren yarı saydam pencere."""

    def __init__(self, parent):
        super().__init__(parent)
        self.region = None
        self.start = None
        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.3)
        self.configure(cursor="crosshair", bg="black")
        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _on_press(self, event):
        self.start = (event.x_root, event.y_root)
        self.rect = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2)

    def _on_drag(self, event):
        if self.start:
            self.canvas.coords(self.rect, self.start[0] - self.winfo_rootx(), self.start[1] - self.winfo_rooty(),
                               event.x, event.y)

    def _on_release(self, event):
        if not self.start:
            return
        x1, y1 = self.start
        x2, y2 = event.x_root, event.y_root
        x, y = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1), abs(y2 - y1)
        self.region = (x, y, w, h) if w > 5 and h > 5 else None
        self.destroy()

    def select(self):
        self.wait_window()
        return self.region


if __name__ == "__main__":
    App().mainloop()
