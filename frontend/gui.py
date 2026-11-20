"""Desktop GUI for the NFC antenna generator.

Run:      py frontend/gui.py
Build:    py -m PyInstaller --onefile --windowed --name NFC-Antenna-Generator \
              --paths backend frontend/gui.py

All calculations live in backend/generator.py; this file only collects the
inputs, previews the layout and saves the SVG + report.
"""
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Make backend/ importable when run from source. In the built exe the module is
# bundled (PyInstaller --paths backend), so this path is simply unused.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import generator  # noqa: E402

COPPER = "#b87333"

# (key, label, default, cast, unit). Empty spacing means "same as trace width".
NUMERIC_FIELDS = [
    ("turns", "Number of turns", "5", int, ""),
    ("length", "Outer length", "50", float, "mm"),
    ("width", "Outer width", "50", float, "mm"),
    ("trace_mil", "Trace width", "15", float, "mil"),
    ("spacing_mil", "Trace spacing", "", float, "mil (blank = trace width)"),
    ("copper_oz", "Copper weight", "0.5", float, "oz"),
    ("freq", "Target frequency", "13.56", float, "MHz"),
    ("opening_gap", "Opening gap", "1", float, "mm"),
    ("corner_diameter", "Inner corner diameter", "2", float, "mm"),
    ("chip_cap_pf", "Chip capacitance", "0", float, "pF"),
]

# (key, label, {shown text: value passed to generator.design}, default text)
DROPDOWNS = [
    ("opening", "Opening side", {"length": "length", "width": "width"}, "length"),
    ("chip_inside", "Chip inside", {"True": 1, "False": 0}, "True"),
]


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=10)
        self.root = root
        self.result = None
        self.vars = {}
        root.title("NFC Antenna Generator")
        root.minsize(900, 560)
        self.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self._build_form()
        self._build_output()
        self.preview()

    # ---- layout -------------------------------------------------------
    def _build_form(self):
        form = ttk.LabelFrame(self, text="Inputs", padding=10)
        form.grid(row=0, column=0, sticky="nsw", padx=(0, 10))

        row = 0
        for key, label, default, _cast, unit in NUMERIC_FIELDS:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(form, textvariable=var, width=10)
            entry.grid(row=row, column=1, sticky="w", padx=6, pady=2)
            entry.bind("<Return>", lambda _e: self.preview())
            ttk.Label(form, text=unit, foreground="#666").grid(row=row, column=2, sticky="w")
            self.vars[key] = var
            row += 1

        for key, label, options, default in DROPDOWNS:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=default)
            box = ttk.Combobox(form, textvariable=var, values=list(options), state="readonly", width=8)
            box.grid(row=row, column=1, sticky="w", padx=6, pady=2)
            box.bind("<<ComboboxSelected>>", lambda _e: self.preview())
            self.vars[key] = var
            row += 1

        ttk.Label(form, text="Chip inside = True: outer end bends out\n"
                             "Chip inside = False: inner end bends in",
                  foreground="#666", justify="left").grid(row=row, column=0, columnspan=3,
                                                          sticky="w", pady=(4, 8))
        row += 1

        buttons = ttk.Frame(form)
        buttons.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="Preview", command=self.preview).pack(side="left", expand=True, fill="x")
        ttk.Button(buttons, text="Save SVG + report...", command=self.save).pack(
            side="left", expand=True, fill="x", padx=(6, 0))

        self.status = tk.StringVar()
        ttk.Label(form, textvariable=self.status, foreground="#a00", wraplength=300,
                  justify="left").grid(row=row + 1, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def _build_output(self):
        out = ttk.Frame(self)
        out.grid(row=0, column=1, sticky="nsew")
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        out.rowconfigure(0, weight=3)
        out.rowconfigure(1, weight=2)
        out.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(out, background="white", highlightthickness=1,
                                highlightbackground="#ccc")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _e: self._draw())

        report_frame = ttk.Frame(out)
        report_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        report_frame.rowconfigure(0, weight=1)
        report_frame.columnconfigure(0, weight=1)
        self.report = tk.Text(report_frame, font=("Consolas", 9), wrap="none", height=12)
        self.report.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(report_frame, command=self.report.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.report.configure(yscrollcommand=scroll.set, state="disabled")

    # ---- actions ------------------------------------------------------
    def _read_inputs(self):
        params = {}
        for key, label, _default, cast, _unit in NUMERIC_FIELDS:
            text = self.vars[key].get().strip()
            if key == "spacing_mil" and not text:
                params[key] = None
                continue
            try:
                params[key] = cast(text)
            except ValueError:
                kind = "a whole number" if cast is int else "a number"
                raise ValueError(f"{label} must be {kind}.") from None
        for key, _label, options, _default in DROPDOWNS:
            params[key] = options[self.vars[key].get()]
        return params

    def preview(self):
        try:
            self.result = generator.design(**self._read_inputs())
        except ValueError as e:
            self.result = None
            self.status.set(str(e))
            self._set_report("")
        else:
            self.status.set("")
            self._set_report(self.result["report"])
        self._draw()

    def save(self):
        self.preview()
        if self.result is None:
            messagebox.showerror("Cannot save", self.status.get())
            return
        path = filedialog.asksaveasfilename(
            title="Save antenna", defaultextension=".svg", initialfile="antenna.svg",
            filetypes=[("SVG drawing", "*.svg")])
        if not path:
            return
        try:
            svg_path, txt_path = generator.save(self.result, Path(path).with_suffix(""))
        except OSError as e:
            messagebox.showerror("Cannot save", str(e))
            return
        messagebox.showinfo("Saved", f"Wrote:\n{svg_path}\n{txt_path}")

    # ---- drawing ------------------------------------------------------
    def _set_report(self, text):
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", text)
        self.report.configure(state="disabled")

    def _draw(self):
        c = self.canvas
        c.delete("all")
        if self.result is None:
            c.create_text(c.winfo_width() / 2, c.winfo_height() / 2,
                          text="Fix the inputs to see a preview", fill="#999")
            return
        pts, length, width = self.result["pts"], self.result["length"], self.result["width"]
        xs = [0, length] + [x for x, _ in pts]
        ys = [0, width] + [y for _, y in pts]
        x0, y0 = min(xs), min(ys)
        span_x, span_y = max(xs) - x0, max(ys) - y0
        margin = 20
        cw, ch = max(c.winfo_width() - 2 * margin, 1), max(c.winfo_height() - 2 * margin, 1)
        scale = min(cw / span_x, ch / span_y)
        ox = margin + (cw - span_x * scale) / 2 - x0 * scale
        oy = margin + (ch - span_y * scale) / 2 - y0 * scale

        c.create_rectangle(ox, oy, ox + length * scale, oy + width * scale,
                           outline="#aaa", dash=(3, 3))
        flat = [v for x, y in pts for v in (ox + x * scale, oy + y * scale)]
        c.create_line(*flat, fill=COPPER, width=max(self.result["trace_w"] * scale, 1),
                      capstyle="projecting", joinstyle="miter")
        c.create_text(ox + length * scale / 2, oy + width * scale + 4, anchor="n",
                      text=f"{length:g} x {width:g} mm", fill="#888")


def main():
    if sys.platform == "win32":      # crisp text on high-DPI screens
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
