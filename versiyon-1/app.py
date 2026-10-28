import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading, os, json, sys, subprocess, traceback

import database
from database import db
from ingest import add_file
from search_engine import search
from ai_helper import explain_with_ollama
from exporter import export_csv, export_results, backup_project

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SETTINGS = DATA / "settings.json"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        database.init_db()
        self.title("Bilgi Araştırma — Kaynaklı Yerel Arama")
        self.geometry("1380x900")
        self.minsize(1000, 700)
        self.last_results = []
        self.last_search_id = None
        self.selected_result_index = None
        self.settings = self.load_settings()
        self._build_ui()
        self.refresh_documents()
        self.refresh_history()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def load_settings(self):
        defaults = {"tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    "ocr_lang": "tur+eng", "ollama_model": "qwen2.5:3b",
                    "all_terms": False, "turkish_sensitive": False}
        if SETTINGS.exists():
            try:
                defaults.update(json.loads(SETTINGS.read_text(encoding="utf-8")))
            except Exception:
                pass
        return defaults

    def save_settings_file(self):
        SETTINGS.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_ui(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except Exception: pass
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="BİLGİ ARAŞTIRMA", font=("Segoe UI", 17, "bold")).pack(side="left")
        ttk.Label(top, text="PDF • Word • TXT • Resim • SQLite • Yerel OCR",
                  foreground="#555").pack(side="left", padx=16)
        ttk.Button(top, text="＋ Kaynak ekle", command=self.add_sources).pack(side="right", padx=3)
        ttk.Button(top, text="Yedek oluştur", command=self.backup).pack(side="right", padx=3)
        ttk.Button(top, text="Ayarlar", command=self.open_settings).pack(side="right", padx=3)

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        left = ttk.Frame(main, padding=6)
        right = ttk.Frame(main, padding=6)
        main.add(left, weight=1)
        main.add(right, weight=3)

        ttk.Label(left, text="KAYNAK KÜTÜPHANESİ", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.doc_tree = ttk.Treeview(left, columns=("type", "chunks"), show="tree headings", height=15)
        self.doc_tree.heading("#0", text="Belge")
        self.doc_tree.heading("type", text="Tür")
        self.doc_tree.heading("chunks", text="Bölüm")
        self.doc_tree.column("#0", width=205)
        self.doc_tree.column("type", width=58)
        self.doc_tree.column("chunks", width=58)
        self.doc_tree.pack(fill="x", pady=5)
        ttk.Button(left, text="Seçili kaynağı sil", command=self.delete_selected).pack(anchor="w")
        ttk.Label(left, text="SON ARAMALAR", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(14, 2))
        self.history = tk.Listbox(left, height=12)
        self.history.pack(fill="both", expand=True)
        self.history.bind("<<ListboxSelect>>", self.open_history)

        ttk.Label(right, text="SORU / ANAHTAR KELİMELER", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        qrow = ttk.Frame(right)
        qrow.pack(fill="x", pady=5)
        self.query_var = tk.StringVar()
        self.query_entry = ttk.Entry(qrow, textvariable=self.query_var, font=("Segoe UI", 11))
        self.query_entry.pack(side="left", fill="x", expand=True)
        self.query_entry.bind("<Return>", lambda _e: self.run_search())
        ttk.Button(qrow, text="Ara", command=self.run_search).pack(side="left", padx=(6, 0))
        mode_row = ttk.Frame(right)
        mode_row.pack(fill="x", pady=(0, 4))
        ttk.Label(mode_row, text="Araştırma türü:").pack(side="left", padx=(0, 4))
        self.mode_var = tk.StringVar(value="Otomatik")
        self.mode_combo = ttk.Combobox(mode_row, textvariable=self.mode_var, state="readonly", width=19,
                                       values=("Otomatik", "Çıkmış soru", "Paragraf / metin", "Kavram"))
        self.mode_combo.pack(side="left", padx=(0, 6))
        ttk.Label(mode_row, text="Soru/seçenek, paragraf veya tek kavram girebilirsiniz.", foreground="#555").pack(side="left", padx=8)
        self.all_terms_var = tk.BooleanVar(value=bool(self.settings.get("all_terms", False)))
        ttk.Checkbutton(qrow, text="Tüm kelimeler eşleşsin", variable=self.all_terms_var).pack(side="left", padx=8)
        self.turkish_sensitive_var = tk.BooleanVar(value=bool(self.settings.get("turkish_sensitive", False)))
        ttk.Checkbutton(qrow, text="Türkçe karakter duyarlı", variable=self.turkish_sensitive_var,
                        command=self.on_turkish_toggle).pack(side="left", padx=8)
        self.status_var = tk.StringVar(value="Hazır — önce kaynak dosyalarınızı ekleyin.")
        ttk.Label(right, textvariable=self.status_var).pack(anchor="w", pady=(2, 5))

        cols = ("source", "location", "score", "preview")
        self.result_tree = ttk.Treeview(right, columns=cols, show="headings", height=15)
        for col, title in [("source","Kaynak"),("location","Sayfa / Konum"),("score","Puan"),("preview","Kaynak metni")]:
            self.result_tree.heading(col, text=title)
        self.result_tree.column("source", width=185)
        self.result_tree.column("location", width=115)
        self.result_tree.column("score", width=58)
        self.result_tree.column("preview", width=520)
        self.result_tree.pack(fill="both", expand=True, pady=5)
        self.result_tree.bind("<<TreeviewSelect>>", self.show_selected_result)

        action = ttk.Frame(right)
        action.pack(fill="x", pady=4)
        ttk.Button(action, text="Kaynaklardan konu notu oluştur (Ollama)", command=self.ai_explain).pack(side="left")
        ttk.Button(action, text="Konu notunu arşivle", command=self.save_research_note).pack(side="left", padx=5)
        ttk.Button(action, text="PDF raporu", command=lambda: self.export_report("pdf")).pack(side="left", padx=3)
        ttk.Button(action, text="Word raporu", command=lambda: self.export_report("docx")).pack(side="left", padx=3)
        ttk.Button(action, text="TXT raporu", command=lambda: self.export_report("txt")).pack(side="left", padx=3)
        ttk.Button(action, text="CSV", command=self.export_results).pack(side="left", padx=3)
        ttk.Button(action, text="Kaynak dosyayı aç", command=self.open_source).pack(side="left", padx=3)

        ttk.Label(right, text="SEÇİLİ SONUÇ / KAYNAK METNİ", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        self.detail = tk.Text(right, height=12, wrap="word", font=("Segoe UI", 10))
        self.detail.pack(fill="both", expand=True)
        self.current_ai_answer = ""
        note_row = ttk.Frame(right)
        note_row.pack(fill="x", pady=4)
        ttk.Label(note_row, text="Not:").pack(side="left")
        self.note_entry = ttk.Entry(note_row)
        self.note_entry.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(note_row, text="Notu kaydet", command=self.save_note).pack(side="right")

    def add_sources(self):
        paths = filedialog.askopenfilenames(
            title="Kaynak dosyalarını seç",
            filetypes=[("Desteklenen kaynaklar", "*.pdf *.docx *.txt *.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
                       ("Tüm dosyalar", "*.*")]
        )
        if not paths: return
        self.status_var.set("Kaynaklar arşive ekleniyor ve metinleri çıkarılıyor…")
        self.configure(cursor="watch")
        def worker():
            msgs = []
            for p in paths:
                try:
                    _, msg = add_file(p, self.settings.get("tesseract_path", ""), self.settings.get("ocr_lang", "tur+eng"))
                    msgs.append(f"{Path(p).name}: {msg}")
                except Exception as exc:
                    msgs.append(f"{Path(p).name}: HATA - {exc}")
                    with open(LOG_DIR / "errors.log", "a", encoding="utf-8") as log:
                        log.write(traceback.format_exc() + "\n")
            self.after(0, lambda: self.finish_ingest(msgs))
        threading.Thread(target=worker, daemon=True).start()

    def finish_ingest(self, msgs):
        self.configure(cursor="")
        self.status_var.set("Kaynak ekleme tamamlandı.")
        self.refresh_documents()
        messagebox.showinfo("Kaynak ekleme", "\n".join(msgs[:30]))

    def refresh_documents(self):
        self.doc_tree.delete(*self.doc_tree.get_children())
        for d in database.list_documents():
            self.doc_tree.insert("", "end", iid=str(d["id"]), text=d["name"],
                                 values=(d["file_type"], d["chunk_count"]))

    def delete_selected(self):
        sel = self.doc_tree.selection()
        if not sel: return
        doc_id = int(sel[0])
        if not messagebox.askyesno("Kaynağı sil", "Kaynağı veritabanından ve arşiv klasöründen silmek istiyor musunuz?"):
            return
        stored = database.delete_document(doc_id)
        if stored:
            try: Path(stored).unlink(missing_ok=True)
            except Exception: pass
        self.refresh_documents()
        self.status_var.set("Kaynak silindi.")

    def run_search(self):
        q = self.query_var.get().strip()
        if not q:
            messagebox.showwarning("Arama", "Bir soru veya anahtar kelime yazın.")
            return
        self.status_var.set("Aranıyor…")
        self.result_tree.delete(*self.result_tree.get_children())
        self.detail.delete("1.0", "end")
        self.all_terms_var_value = self.all_terms_var.get()
        self.ignore_turkish_case_value = not self.turkish_sensitive_var.get()
        def worker():
            try:
                sid, results = search(q, all_terms=self.all_terms_var_value,
                                      ignore_turkish_case=self.ignore_turkish_case_value)
                self.after(0, lambda: self.finish_search(sid, results))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Arama hatası", str(exc)))
                self.after(0, lambda: self.status_var.set("Arama başarısız."))
        threading.Thread(target=worker, daemon=True).start()

    def finish_search(self, sid, results):
        self.last_search_id, self.last_results = sid, results
        for i, r in enumerate(results):
            preview = " ".join(r["text"].split())
            if len(preview) > 300: preview = preview[:300] + "…"
            self.result_tree.insert("", "end", iid=str(i),
                values=(r["document_name"], r["location"], f'{r["score"]:.2f}', preview))
        self.status_var.set(f"{len(results)} ilgili metin bölümü bulundu.")
        self.refresh_history()

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

    def ai_explain(self):
        if not self.last_results:
            messagebox.showinfo("Açıklama", "Önce arama yapın ve ilgili kaynakları bulun.")
            return
        model = self.settings.get("ollama_model", "qwen2.5:3b")
        q = self.query_var.get().strip()
        self.status_var.set(f"Yerel model yanıtı bekleniyor: {model}")
        def worker():
            try:
                answer = explain_with_ollama(q, self.last_results, model=model, mode=self.mode_var.get())
            except Exception as exc:
                answer = ("Ollama'ya bağlanılamadı. Ollama kurulu, çalışır ve model indirilmiş olmalı.\n\n"
                          "Kurulum komutu örneği: ollama pull qwen2.5:3b\n\nTeknik ayrıntı: " + str(exc))
            self.after(0, lambda: self.show_ai_answer(answer))
        threading.Thread(target=worker, daemon=True).start()

    def show_ai_answer(self, answer):
        self.current_ai_answer = answer
        self.detail.delete("1.0", "end")
        self.detail.insert("end", answer)
        self.status_var.set("Konu notu hazır. Metni düzenleyebilir ve arşivleyebilirsiniz.")

    def save_research_note(self):
        body = self.detail.get("1.0", "end").strip()
        query = self.query_var.get().strip()
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
        self.status_var.set("Konu notu veritabanına ve exports klasörüne kaydedildi.")
        messagebox.showinfo("Konu notu arşivlendi", f"Not kalıcı olarak kaydedildi:\n{path}")

    def export_report(self, fmt):
        if not self.last_results and not self.detail.get("1.0", "end").strip():
            messagebox.showinfo("Rapor oluştur", "Önce arama yapın veya konu notu oluşturun.")
            return
        query = self.query_var.get().strip() or "Konu_Notu"
        try:
            path = export_results(self.last_results, fmt=fmt, query=query,
                                  mode=self.mode_var.get(),
                                  ai_answer=self.detail.get("1.0", "end").strip() if self.current_ai_answer else "")
            messagebox.showinfo("Rapor hazır", f"Tek dosyalı rapor oluşturuldu:\n{path}\n\nDosya, exports klasörüne kaydedildi.")
        except Exception as exc:
            messagebox.showerror("Rapor oluşturulamadı", f"{fmt.upper()} dışa aktarma hatası:\n{exc}")

    def export_results(self):
        if not self.last_results:
            messagebox.showinfo("Dışa aktar", "Önce arama yapın.")
            return
        path = export_csv(self.last_results)
        messagebox.showinfo("Dışa aktar", f"CSV dosyası oluşturuldu:\n{path}")

    def open_source(self):
        sel = self.result_tree.selection()
        if not sel: return
        path = self.last_results[int(sel[0])]["stored_path"]
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            messagebox.showerror("Dosya açılamadı", str(exc))

    def on_turkish_toggle(self):
        self.settings["turkish_sensitive"] = bool(self.turkish_sensitive_var.get())
        self.save_settings_file()
        self.status_var.set("Arama Türkçe karakter duyarlı." if self.turkish_sensitive_var.get()
                            else "Arama Türkçe karakter duyarsız (ç/ğ/ı/ş... eşitlenir).")

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
            self.query_var.set(row["query"])
            self.run_search()

    def backup(self):
        try:
            path = backup_project()
            messagebox.showinfo("Yedekleme", f"Yedek oluşturuldu:\n{path}")
        except Exception as exc:
            messagebox.showerror("Yedekleme hatası", str(exc))

    def open_settings(self):
        win = tk.Toplevel(self)
        win.title("Ayarlar")
        win.geometry("720x330")
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
        def save():
            self.settings.update({"tesseract_path": tess.get().strip(), "ocr_lang": lang.get().strip() or "tur+eng",
                                  "ollama_model": model.get().strip() or "qwen2.5:3b"})
            self.save_settings_file()
            win.destroy()
            messagebox.showinfo("Ayarlar", "Ayarlar kaydedildi.")
        ttk.Button(frm, text="Kaydet", command=save).grid(row=6, column=0, sticky="w", pady=12)

    def on_close(self):
        try:
            with db() as con:
                con.execute("PRAGMA wal_checkpoint(FULL)")
        except Exception:
            pass
        self.destroy()

if __name__ == "__main__":
    App().mainloop()
