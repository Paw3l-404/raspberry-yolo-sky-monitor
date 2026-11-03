"""Interfejs graficzny (tkinter) — bez logiki biznesowej.

Układ:
- duży CURRENT (tu rysujesz i zoomujesz),
- małe PREV / NEXT z prawej (porównanie).

Stan i zapis etykiet są w logic.LabelAppLogic.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageEnhance, ImageTk

from logic import CLASSES, LabelAppLogic, LabelClass

CLASS_COLORS = {
    "meteor": "#f59e0b",
    "satelita": "#34d399",
    "flara satelitarna": "#38bdf8",
    "samolot": "#fb7185",
    "Cosmic ray": "#c084fc",
    "Sensor artefact": "#a8a29e",
}


class LabelAppGui:
    def __init__(self, root: tk.Tk, logic: LabelAppLogic) -> None:
        self.root = root
        self.logic = logic
        self.root.title("Przeglądarka stacków — etykietowanie 3 klatek")
        self.root.geometry("1400x860")
        self.root.minsize(1024, 700)

        self._photo_cur: ImageTk.PhotoImage | None = None
        self._photo_prev: ImageTk.PhotoImage | None = None
        self._photo_next: ImageTk.PhotoImage | None = None
        self._pil_cur: Image.Image | None = None
        self._pil_prev: Image.Image | None = None
        self._pil_next: Image.Image | None = None

        self._drag_start: tuple[float, float] | None = None
        self._drag_rect: int | None = None
        self._fit_cur: tuple[float, float, float, float] | None = None  # ox,oy,dw,dh
        self._zoom = 1.0  # dodatkowy zoom CURRENT (kółko myszy)
        self._contrast = 1.35  # lekko podbite dla ciemnych stacków
        self._blink_peer = tk.StringVar(value="prev")  # prev|next
        self._blink_on = False

        self._build()
        self._bind_keys()
        self.refresh()

    # --- budowa UI ----------------------------------------------------------

    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill=tk.X)

        ttk.Button(top, text="Otwórz folder…", command=self.on_open).pack(side=tk.LEFT)
        ttk.Button(top, text="Zapisz etykiety (S)", command=self.on_save).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(top, text="Ułóż zbiór…", command=self.on_build_dataset).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(top, text="Zoom −", command=lambda: self._bump_zoom(1 / 1.25)).pack(
            side=tk.LEFT, padx=(12, 0)
        )
        ttk.Button(top, text="Zoom +", command=lambda: self._bump_zoom(1.25)).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        ttk.Button(top, text="Reset zoom (0)", command=self._reset_zoom).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        ttk.Label(top, text="Blink z:").pack(side=tk.LEFT, padx=(12, 2))
        ttk.Radiobutton(top, text="prev", value="prev", variable=self._blink_peer).pack(
            side=tk.LEFT
        )
        ttk.Radiobutton(top, text="next", value="next", variable=self._blink_peer).pack(
            side=tk.LEFT
        )
        ttk.Label(top, text="(przytrzymaj Spację)").pack(side=tk.LEFT, padx=(4, 0))

        self.status_var = tk.StringVar(value="Wybierz folder ze stackami (PNG/JPG).")
        ttk.Label(top, textvariable=self.status_var).pack(side=tk.LEFT, padx=12)

        body = ttk.Frame(self.root, padding=(6, 0, 6, 6))
        body.pack(fill=tk.BOTH, expand=True)

        # lewy panel
        left = ttk.Frame(body, width=220)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        ttk.Label(left, text="Stacki (kolejność czasowa)").pack(anchor=tk.W)
        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        self.file_list = tk.Listbox(list_frame, exportselection=False)
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=scroll.set)
        self.file_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_list.bind("<<ListboxSelect>>", self.on_list_select)

        ttk.Label(left, text="Klasa etykiety").pack(anchor=tk.W)
        self.class_var = tk.StringVar(value="meteor")
        for cid, name, key in CLASSES:
            ttk.Radiobutton(
                left,
                text=f"{key}. {name}",
                value=cid,
                variable=self.class_var,
                command=self.on_class_change,
            ).pack(anchor=tk.W)

        btns = ttk.Frame(left)
        btns.pack(fill=tk.X, pady=8)
        ttk.Button(btns, text="← Poprzedni (A)", command=lambda: self.nav(-1)).pack(
            fill=tk.X, pady=2
        )
        ttk.Button(btns, text="Następny (D) →", command=lambda: self.nav(1)).pack(
            fill=tk.X, pady=2
        )
        ttk.Button(btns, text="Puste (E)", command=self.on_empty).pack(fill=tk.X, pady=2)
        ttk.Button(
            btns, text="Zapisz status + dalej (Enter)", command=self.on_reviewed_next
        ).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="Cofnij ostatni box (Backspace)", command=self.on_undo_box).pack(
            fill=tk.X, pady=2
        )

        contrast_row = ttk.Frame(left)
        contrast_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(contrast_row, text="Kontrast podglądu").pack(anchor=tk.W)
        self.contrast_scale = ttk.Scale(
            contrast_row,
            from_=0.8,
            to=2.5,
            value=self._contrast,
            command=self._on_contrast,
        )
        self.contrast_scale.pack(fill=tk.X)

        ttk.Label(
            left,
            text=(
                "Duży obraz = CURRENT.\n"
                "Kółko myszy = zoom.\n"
                "Spacja = blink z sąsiadem.\n"
                "Boxy tylko na CURRENT."
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

        # środek: duży CURRENT
        center = ttk.Frame(body)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        ttk.Label(center, text="CURRENT — rysuj tutaj", font=("Segoe UI", 10, "bold")).pack(
            anchor=tk.W
        )
        self.canvas_cur = tk.Canvas(
            center,
            bg="#05070d",
            highlightthickness=2,
            highlightbackground="#f59e0b",
        )
        self.canvas_cur.pack(fill=tk.BOTH, expand=True)
        self.canvas_cur.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas_cur.bind("<B1-Motion>", self.on_drag_move)
        self.canvas_cur.bind("<ButtonRelease-1>", self.on_drag_end)
        self.canvas_cur.bind("<MouseWheel>", self.on_mousewheel)  # Windows
        self.canvas_cur.bind("<Button-4>", lambda e: self.on_mousewheel_linux(1))
        self.canvas_cur.bind("<Button-5>", lambda e: self.on_mousewheel_linux(-1))
        self.canvas_cur.bind("<Configure>", lambda _e: self.refresh_images())

        # prawa kolumna: PREV / NEXT
        right = ttk.Frame(body, width=260)
        right.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        right.pack_propagate(False)

        ttk.Label(right, text="PREV").pack(anchor=tk.W)
        self.canvas_prev = tk.Canvas(
            right, height=200, bg="#05070d", highlightthickness=1, highlightbackground="#444"
        )
        self.canvas_prev.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.canvas_prev.bind("<Button-1>", lambda _e: self.nav(-1))

        ttk.Label(right, text="NEXT").pack(anchor=tk.W)
        self.canvas_next = tk.Canvas(
            right, height=200, bg="#05070d", highlightthickness=1, highlightbackground="#444"
        )
        self.canvas_next.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.canvas_next.bind("<Button-1>", lambda _e: self.nav(1))

        for c in (self.canvas_prev, self.canvas_next):
            c.bind("<Configure>", lambda _e: self.refresh_side_thumbs())

    def _bind_keys(self) -> None:
        self.root.bind("<Left>", lambda _e: self.nav(-1))
        self.root.bind("<Right>", lambda _e: self.nav(1))
        self.root.bind("a", lambda _e: self.nav(-1))
        self.root.bind("d", lambda _e: self.nav(1))
        self.root.bind("A", lambda _e: self.nav(-1))
        self.root.bind("D", lambda _e: self.nav(1))
        self.root.bind("e", lambda _e: self.on_empty())
        self.root.bind("E", lambda _e: self.on_empty())
        self.root.bind("s", lambda _e: self.on_save())
        self.root.bind("S", lambda _e: self.on_save())
        self.root.bind("0", lambda _e: self._reset_zoom())
        self.root.bind("<Return>", lambda _e: self.on_reviewed_next())
        self.root.bind("<BackSpace>", lambda _e: self.on_undo_box())
        self.root.bind("<space>", self._blink_press)
        self.root.bind("<KeyRelease-space>", self._blink_release)
        for cid, _name, key in CLASSES:
            self.root.bind(key, lambda _e, c=cid: self._set_class(c))

    # --- zoom / kontrast / blink --------------------------------------------

    def _bump_zoom(self, factor: float) -> None:
        self._zoom = min(max(self._zoom * factor, 1.0), 8.0)
        self.refresh_images()
        self._update_status()

    def _reset_zoom(self) -> None:
        self._zoom = 1.0
        self.refresh_images()
        self._update_status()

    def _on_contrast(self, _value: str) -> None:
        self._contrast = float(self.contrast_scale.get())
        self._reload_pils()
        self.refresh_images()
        self.refresh_side_thumbs()

    def on_mousewheel(self, event: tk.Event) -> None:
        if event.delta > 0:
            self._bump_zoom(1.15)
        else:
            self._bump_zoom(1 / 1.15)

    def on_mousewheel_linux(self, direction: int) -> None:
        self._bump_zoom(1.15 if direction > 0 else 1 / 1.15)

    def _blink_press(self, _event=None) -> str:
        self._blink_on = True
        self.refresh_images()
        return "break"

    def _blink_release(self, _event=None) -> None:
        self._blink_on = False
        self.refresh_images()

    # --- akcje --------------------------------------------------------------

    def on_open(self) -> None:
        folder = filedialog.askdirectory(title="Folder ze stackami")
        if not folder:
            return
        try:
            n = self.logic.open_folder(Path(folder))
        except OSError as exc:
            messagebox.showerror("Błąd", str(exc))
            return
        if n == 0:
            messagebox.showwarning("Pusto", "W folderze nie ma obrazów PNG/JPG.")
        self._zoom = 1.0
        self.refresh()

    def on_save(self) -> None:
        if not self.logic.files:
            messagebox.showinfo("Info", "Najpierw otwórz folder.")
            return

        mode = self._ask_export_mode()
        if mode is None:
            return

        default_name = (
            "etykiety_triplet.json" if mode == "triplet" else "etykiety_single.json"
        )
        path = filedialog.asksaveasfilename(
            title="Zapisz etykiety",
            defaultextension=".json",
            initialfile=default_name,
            initialdir=str(self.logic.folder) if self.logic.folder else None,
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        out = self.logic.save_labels(Path(path), mode=mode)
        messagebox.showinfo(
            "Zapisano",
            f"Tryb: {mode}\nEtykiety → {out}",
        )
        self._update_status()

    def _ask_export_mode(self) -> str | None:
        """Okno: single vs triplet. None = anulowano."""
        win = tk.Toplevel(self.root)
        win.title("Tryb eksportu")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        choice: dict[str, str | None] = {"mode": None}
        var = tk.StringVar(value="triplet")

        ttk.Label(
            win,
            text="Pod jaki trening zapisać JSON?",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W, padx=14, pady=(12, 6))

        ttk.Radiobutton(
            win,
            text="Jedna klatka (single) — tylko current + boxy",
            value="single",
            variable=var,
        ).pack(anchor=tk.W, padx=14, pady=2)
        ttk.Radiobutton(
            win,
            text="Triplet (3 klatki) — dopisz prev_file / next_file do każdej pozycji",
            value="triplet",
            variable=var,
        ).pack(anchor=tk.W, padx=14, pady=2)

        ttk.Label(
            win,
            text=(
                "Boxy zawsze dotyczą środkowej klatki (current).\n"
                "W trybie triplet brzegi listy mają complete=false."
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=14, pady=(8, 4))

        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, padx=14, pady=12)

        def ok() -> None:
            choice["mode"] = var.get()
            win.destroy()

        def cancel() -> None:
            choice["mode"] = None
            win.destroy()

        ttk.Button(btns, text="Anuluj", command=cancel).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Dalej", command=ok).pack(side=tk.RIGHT, padx=(0, 8))

        win.protocol("WM_DELETE_WINDOW", cancel)
        win.wait_window()
        return choice["mode"]

    def on_build_dataset(self) -> None:
        if not self.logic.files:
            messagebox.showinfo("Info", "Najpierw otwórz folder ze stackami.")
            return
        if not self.logic.labels:
            messagebox.showinfo(
                "Info",
                "Brak etykiet w pamięci. Oznacz klatki (box / puste) albo wczytaj JSON.",
            )
            return
        self._dataset_wizard()

    def _dataset_wizard(self) -> None:
        """Jedno okno: podział % + folder docelowy + przycisk Utwórz (zawsze widoczny na dole)."""
        win = tk.Toplevel(self.root)
        win.title("Ułóż zbiór train / val / test")
        win.transient(self.root)
        win.grab_set()
        win.minsize(480, 520)
        win.geometry("520x560")

        mode_var = tk.StringVar(value="triplet")
        empty_var = tk.BooleanVar(value=True)
        yolo_var = tk.BooleanVar(value=True)
        train_var = tk.DoubleVar(value=70)
        val_var = tk.DoubleVar(value=15)
        test_var = tk.DoubleVar(value=15)
        seed_var = tk.IntVar(value=42)
        preview_var = tk.StringVar(value="")
        dest_var = tk.StringVar(value="")

        # Dolny pasek przycisków — pack najpierw, żeby zawsze był widoczny
        bottom = ttk.Frame(win, padding=(14, 10))
        bottom.pack(side=tk.BOTTOM, fill=tk.X)

        body = ttk.Frame(win, padding=(14, 12))
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        ttk.Label(body, text="1. Tryb próbek", font=("Segoe UI", 10, "bold")).pack(
            anchor=tk.W
        )
        ttk.Radiobutton(
            body, text="Jedna klatka (single)", value="single", variable=mode_var
        ).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(
            body,
            text="Triplet (prev + current + next)",
            value="triplet",
            variable=mode_var,
        ).pack(anchor=tk.W, pady=1)
        ttk.Checkbutton(
            body,
            text="Uwzględnij klatki puste (negatywy)",
            variable=empty_var,
        ).pack(anchor=tk.W, pady=(6, 2))
        ttk.Checkbutton(
            body,
            text="Format YOLO / Ultralytics (images + labels + data.yaml)",
            variable=yolo_var,
        ).pack(anchor=tk.W, pady=(2, 2))
        ttk.Label(
            body,
            text="YOLO zapisuje tylko current (nawet przy wyborze triplet).",
            foreground="#666",
        ).pack(anchor=tk.W, pady=(0, 4))

        ttk.Separator(body).pack(fill=tk.X, pady=8)
        ttk.Label(body, text="2. Podział procentowy", font=("Segoe UI", 10, "bold")).pack(
            anchor=tk.W
        )

        # update_preview musi istnieć ZANIM suwaki wywołają sync()
        pct_labels: dict[str, ttk.Label] = {}

        def update_preview(*_a) -> None:
            for key, var in (
                ("train", train_var),
                ("val", val_var),
                ("test", test_var),
            ):
                lab = pct_labels.get(key)
                if lab is not None:
                    lab.configure(text=f"{int(round(var.get()))}%")
            mode = mode_var.get()
            samples = self.logic.collect_export_samples(
                mode,  # type: ignore[arg-type]
                include_empty=bool(empty_var.get()),
            )
            n = len(samples)
            try:
                nt, nv, nte = self.logic.split_counts(
                    n, train_var.get(), val_var.get(), test_var.get()
                )
            except ValueError:
                preview_var.set("Ustaw procenty > 0")
                return
            s = int(round(train_var.get() + val_var.get() + test_var.get()))
            hint = ""
            if n == 0:
                hint = (
                    "\nBrak próbek — oznacz klatki (box lub Puste). "
                    "Przy triplet potrzebne też sąsiedzi."
                )
            preview_var.set(
                f"Kandydujące próbki: {n}  →  train {nt} | val {nv} | test {nte}\n"
                f"Suma suwaków: {s}% (przy tworzeniu normalizowana)"
                f"{hint}"
            )

        def make_row(parent: ttk.Frame, key: str, label: str, var: tk.DoubleVar) -> None:
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=label, width=8).pack(side=tk.LEFT)
            scale = ttk.Scale(
                row,
                from_=0,
                to=100,
                variable=var,
                orient=tk.HORIZONTAL,
                command=lambda _v: update_preview(),
            )
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
            val_lbl = ttk.Label(row, width=5, text=f"{int(round(var.get()))}%")
            val_lbl.pack(side=tk.LEFT)
            pct_labels[key] = val_lbl

        make_row(body, "train", "train", train_var)
        make_row(body, "val", "val", val_var)
        make_row(body, "test", "test", test_var)

        seed_row = ttk.Frame(body)
        seed_row.pack(fill=tk.X, pady=(6, 2))
        ttk.Label(seed_row, text="Seed losowania").pack(side=tk.LEFT)
        ttk.Spinbox(seed_row, from_=0, to=999999, textvariable=seed_var, width=8).pack(
            side=tk.LEFT, padx=8
        )

        ttk.Label(body, textvariable=preview_var, justify=tk.LEFT).pack(
            anchor=tk.W, pady=8
        )

        ttk.Separator(body).pack(fill=tk.X, pady=4)
        ttk.Label(
            body,
            text="3. Folder docelowy (powstaną train/val/test)",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W, pady=(4, 2))
        dest_row = ttk.Frame(body)
        dest_row.pack(fill=tk.X, pady=2)
        ttk.Entry(dest_row, textvariable=dest_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        def browse_dest() -> None:
            chosen = filedialog.askdirectory(
                parent=win,
                title="Folder docelowy zbioru",
            )
            if chosen:
                dest_var.set(chosen)

        ttk.Button(dest_row, text="Przeglądaj…", command=browse_dest).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        mode_var.trace_add("write", lambda *_: update_preview())
        empty_var.trace_add("write", lambda *_: update_preview())
        update_preview()

        def create_dataset() -> None:
            dest = dest_var.get().strip()
            if not dest:
                messagebox.showwarning(
                    "Folder",
                    "Wskaż folder docelowy (Przeglądaj…), potem kliknij Utwórz zbiór.",
                    parent=win,
                )
                return
            samples = self.logic.collect_export_samples(
                mode_var.get(),  # type: ignore[arg-type]
                include_empty=bool(empty_var.get()),
            )
            if not samples:
                messagebox.showerror(
                    "Brak próbek",
                    "Nie ma czego eksportować. Oznacz klatki boxem lub jako puste.",
                    parent=win,
                )
                return
            try:
                manifest = self.logic.build_dataset(
                    Path(dest),
                    mode=mode_var.get(),  # type: ignore[arg-type]
                    train_pct=float(train_var.get()),
                    val_pct=float(val_var.get()),
                    test_pct=float(test_var.get()),
                    include_empty=bool(empty_var.get()),
                    seed=int(seed_var.get()),
                    yolo_format=bool(yolo_var.get()),
                )
            except ValueError as exc:
                messagebox.showerror("Błąd", str(exc), parent=win)
                return
            counts = manifest["counts"]
            win.destroy()
            extra = ""
            if manifest.get("yolo_format"):
                extra = f"\ndata.yaml → {manifest.get('data_yaml', dest)}"
            messagebox.showinfo(
                "Zbiór gotowy",
                (
                    f"Tryb: {manifest['export_mode']}"
                    f"{' + YOLO' if manifest.get('yolo_format') else ''}\n"
                    f"train: {counts['train']}  |  val: {counts['val']}  |  test: {counts['test']}\n"
                    f"→ {dest}"
                    f"{extra}\n"
                    f"(manifest.json w folderze)"
                ),
            )

        ttk.Button(bottom, text="Anuluj", command=win.destroy).pack(side=tk.RIGHT)
        ttk.Button(bottom, text="Utwórz zbiór", command=create_dataset).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        ttk.Label(
            bottom, text="Najpierw folder (krok 3), potem „Utwórz zbiór”."
        ).pack(side=tk.LEFT)

        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.wait_window()

    def on_class_change(self) -> None:
        self.logic.set_active_class(self.class_var.get())  # type: ignore[arg-type]

    def _set_class(self, class_id: LabelClass) -> None:
        self.class_var.set(class_id)
        self.logic.set_active_class(class_id)

    def nav(self, delta: int) -> None:
        self.logic.go(delta)
        self._zoom = 1.0
        self.refresh()

    def on_list_select(self, _event=None) -> None:
        sel = self.file_list.curselection()
        if not sel:
            return
        self.logic.go_to(int(sel[0]))
        self._zoom = 1.0
        self._reload_pils()
        self.refresh_images()
        self.refresh_side_thumbs()
        self._update_status()
        if self.logic.files:
            self.file_list.selection_clear(0, tk.END)
            self.file_list.selection_set(self.logic.index)
            self.file_list.see(self.logic.index)

    def on_empty(self) -> None:
        self.logic.mark_empty()
        self.logic.go(1)
        self._zoom = 1.0
        self.refresh()

    def on_reviewed_next(self) -> None:
        self.logic.mark_reviewed_and_next()
        self._zoom = 1.0
        self.refresh()

    def on_undo_box(self) -> None:
        self.logic.delete_last_box()
        self.refresh_images()
        self._update_status()

    # --- rysowanie boxa -----------------------------------------------------

    def on_drag_start(self, event: tk.Event) -> None:
        if self.logic.current_path() is None or self._fit_cur is None or self._blink_on:
            return
        self._drag_start = (event.x, event.y)
        if self._drag_rect is not None:
            self.canvas_cur.delete(self._drag_rect)
        self._drag_rect = self.canvas_cur.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline=CLASS_COLORS[self.logic.active_class],
            width=2,
        )

    def on_drag_move(self, event: tk.Event) -> None:
        if self._drag_start is None or self._drag_rect is None:
            return
        x0, y0 = self._drag_start
        self.canvas_cur.coords(self._drag_rect, x0, y0, event.x, event.y)

    def on_drag_end(self, event: tk.Event) -> None:
        if self._drag_start is None or self._fit_cur is None:
            return
        x0, y0 = self._drag_start
        x1, y1 = event.x, event.y
        self._drag_start = None
        if self._drag_rect is not None:
            self.canvas_cur.delete(self._drag_rect)
            self._drag_rect = None

        ox, oy, dw, dh = self._fit_cur
        if dw <= 0 or dh <= 0:
            return

        def to_norm(px: float, py: float) -> tuple[float, float]:
            return ((px - ox) / dw, (py - oy) / dh)

        nx0, ny0 = to_norm(x0, y0)
        nx1, ny1 = to_norm(x1, y1)
        x = min(nx0, nx1)
        y = min(ny0, ny1)
        w = abs(nx1 - nx0)
        h = abs(ny1 - ny0)
        if (nx0 < 0 and nx1 < 0) or (ny0 < 0 and ny1 < 0):
            return
        self.logic.add_box(x, y, w, h)
        self.refresh_images()
        self._update_status()

    # --- odświeżanie --------------------------------------------------------

    def refresh(self) -> None:
        self.file_list.delete(0, tk.END)
        for p in self.logic.files:
            mark = " "
            lab = self.logic.labels.get(p.name)
            if lab:
                if lab.status == "empty":
                    mark = "·"
                elif lab.boxes:
                    mark = "●"
                elif lab.status == "reviewed":
                    mark = "○"
            self.file_list.insert(tk.END, f"{mark} {p.name}")
        if self.logic.files:
            self.file_list.selection_clear(0, tk.END)
            self.file_list.selection_set(self.logic.index)
            self.file_list.see(self.logic.index)
        self._reload_pils()
        self.refresh_images()
        self.refresh_side_thumbs()
        self._update_status()

    def _update_status(self) -> None:
        if not self.logic.files:
            self.status_var.set("Wybierz folder ze stackami (PNG/JPG).")
            return
        st = self.logic.stats()
        prev_n, cur_n, next_n = self.logic.triplet_names()
        lab = self.logic.current_label()
        status = lab.status if lab else "unreviewed"
        self.status_var.set(
            f"{self.logic.index + 1}/{st['total']}  |  "
            f"status: {status}  |  boxy: {len(lab.boxes) if lab else 0}  |  "
            f"zoom ×{self._zoom:.2f}  |  "
            f"triplet: {prev_n or '—'} | {cur_n} | {next_n or '—'}"
        )

    def _enhance(self, img: Image.Image) -> Image.Image:
        if abs(self._contrast - 1.0) < 0.05:
            return img
        return ImageEnhance.Contrast(img).enhance(self._contrast)

    def _load_pil(self, path: Path | None) -> Image.Image | None:
        if path is None:
            return None
        try:
            return self._enhance(Image.open(path).convert("RGB"))
        except OSError:
            return None

    def _reload_pils(self) -> None:
        self._pil_prev = self._load_pil(self.logic.prev_path())
        self._pil_cur = self._load_pil(self.logic.current_path())
        self._pil_next = self._load_pil(self.logic.next_path())

    def refresh_images(self) -> None:
        # blink: pokaż sąsiada zamiast current
        show = self._pil_cur
        label_extra = ""
        if self._blink_on:
            if self._blink_peer.get() == "prev" and self._pil_prev is not None:
                show = self._pil_prev
                label_extra = " [BLINK PREV]"
            elif self._blink_peer.get() == "next" and self._pil_next is not None:
                show = self._pil_next
                label_extra = " [BLINK NEXT]"

        self._photo_cur, self._fit_cur = self._paint_main(
            self.canvas_cur, show, draw_boxes=not self._blink_on, zoom=self._zoom
        )
        if label_extra:
            self.canvas_cur.create_text(
                8, 8, anchor=tk.NW, text=label_extra, fill="#38bdf8", font=("Segoe UI", 11, "bold")
            )

    def refresh_side_thumbs(self) -> None:
        self._photo_prev = self._paint_thumb(self.canvas_prev, self._pil_prev, "brak prev")
        self._photo_next = self._paint_thumb(self.canvas_next, self._pil_next, "brak next")

    def _paint_thumb(
        self, canvas: tk.Canvas, img: Image.Image | None, empty: str
    ) -> ImageTk.PhotoImage | None:
        canvas.delete("all")
        cw = max(canvas.winfo_width(), 40)
        ch = max(canvas.winfo_height(), 40)
        if img is None:
            canvas.create_text(cw // 2, ch // 2, text=empty, fill="#666")
            return None
        scale = min(cw / img.width, ch / img.height)
        dw = max(int(img.width * scale), 1)
        dh = max(int(img.height * scale), 1)
        ox = (cw - dw) // 2
        oy = (ch - dh) // 2
        photo = ImageTk.PhotoImage(img.resize((dw, dh), Image.Resampling.BILINEAR))
        canvas.create_image(ox, oy, anchor=tk.NW, image=photo)
        canvas.image = photo  # type: ignore[attr-defined]
        return photo

    def _paint_main(
        self,
        canvas: tk.Canvas,
        img: Image.Image | None,
        draw_boxes: bool,
        zoom: float,
    ) -> tuple[ImageTk.PhotoImage | None, tuple[float, float, float, float] | None]:
        canvas.delete("all")
        cw = max(canvas.winfo_width(), 40)
        ch = max(canvas.winfo_height(), 40)
        if img is None:
            canvas.create_text(cw // 2, ch // 2, text="brak", fill="#666")
            return None, None

        base = min(cw / img.width, ch / img.height)
        scale = base * zoom
        dw = max(int(img.width * scale), 1)
        dh = max(int(img.height * scale), 1)
        # przy zoom > 1: wyśrodkuj (prosty pan = środek)
        ox = (cw - dw) // 2
        oy = (ch - dh) // 2
        photo = ImageTk.PhotoImage(img.resize((dw, dh), Image.Resampling.BILINEAR))
        canvas.create_image(ox, oy, anchor=tk.NW, image=photo)
        canvas.image = photo  # type: ignore[attr-defined]

        if draw_boxes:
            lab = self.logic.current_label()
            if lab:
                for box in lab.boxes:
                    color = CLASS_COLORS.get(box.class_id, "#fff")
                    x0 = ox + box.x * dw
                    y0 = oy + box.y * dh
                    x1 = ox + (box.x + box.w) * dw
                    y1 = oy + (box.y + box.h) * dh
                    canvas.create_rectangle(x0, y0, x1, y1, outline=color, width=2)
                    canvas.create_text(
                        x0 + 4,
                        y0 + 4,
                        anchor=tk.NW,
                        text=box.class_id,
                        fill=color,
                        font=("Segoe UI", 9),
                    )

        return photo, (float(ox), float(oy), float(dw), float(dh))
