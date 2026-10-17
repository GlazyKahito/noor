"""Reusable building blocks for the screens: cards, number tiles, tables, charts, forms."""
import gc
import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ..summaries import RULE_LABELS, fmt, pct, when  # noqa: F401 (re-exported for the screens)
from . import styles
from .styles import CARD, FONTS, LINE

# ---------------------------------------------------------------------------- page
class Page(ttk.Frame):
    """Base class for a screen. Subclasses fill build() and refresh()."""

    title = "Page"
    subtitle = ""

    def __init__(self, parent, app):
        """Keep a reference to the app (and its service and database), then build the widgets."""
        super().__init__(parent, padding=(22, 6, 22, 14))
        self.app = app
        self.svc = app.svc
        self.db = app.db
        self.build()

    def build(self):
        """Create the widgets once."""

    def refresh(self):
        """Reload data from the database into the widgets."""

    def toolbar(self, parent=None):
        """A row for buttons and filters at the top of the page."""
        bar = ttk.Frame(parent or self)
        bar.pack(fill="x", pady=(0, 10))
        return bar


# ---------------------------------------------------------------------------- containers
class Card(tk.Frame):
    """White panel with a thin border, an optional title and a body frame."""

    def __init__(self, parent, title=None, subtitle=None, padding=12):
        super().__init__(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1, bd=0)
        if title:
            head = ttk.Frame(self, style="Card.TFrame")
            head.pack(fill="x", padx=padding, pady=(padding - 2, 0))
            ttk.Label(head, text=title, style="CardH2.TLabel").pack(side="left")
            self.head = head
            if subtitle:
                ttk.Label(self, text=subtitle, style="CardMuted.TLabel", wraplength=900,
                          justify="left").pack(fill="x", padx=padding, pady=(2, 0))
        self.body = ttk.Frame(self, style="Card.TFrame")
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)


class StatTile(tk.Frame):
    """One headline number with a label above and a note below."""

    def __init__(self, parent, label, accent=False):
        super().__init__(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1, bd=0)
        bar = tk.Frame(self, bg=styles.WINE if accent else LINE, height=3)
        bar.pack(fill="x")
        inner = ttk.Frame(self, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=14, pady=(8, 10))
        ttk.Label(inner, text=label.upper(), style="CardCaps.TLabel").pack(anchor="w")
        self.value = ttk.Label(inner, text="—", style="AccentNumber.TLabel" if accent else "Number.TLabel")
        self.value.pack(anchor="w", pady=(2, 0))
        self.note = ttk.Label(inner, text="", style="CardMuted.TLabel", wraplength=220, justify="left")
        self.note.pack(anchor="w")

    def set(self, value, note=""):
        """Show a new value and note."""
        self.value.configure(text=value)
        self.note.configure(text=note)


def tile_row(parent, specs):
    """A row of StatTiles that share the width equally. specs: [(key, label, accent)]."""
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=(0, 12))
    tiles = {}
    for i, (key, label, accent) in enumerate(specs):
        tile = StatTile(row, label, accent)
        tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
        row.columnconfigure(i, weight=1, uniform="tiles")
        tiles[key] = tile
    return tiles


class ScrollableFrame(ttk.Frame):
    """A frame whose content scrolls vertically (Canvas + inner frame + scrollbar)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=styles.SAND, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        # the inner frame always takes the full width of the visible area
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, event):
        """Scroll with the mouse wheel, except over widgets that scroll themselves."""
        if isinstance(event.widget, (ttk.Treeview, tk.Text, tk.Listbox)):
            return
        if self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def to_top(self):
        """Scroll back to the top."""
        self.canvas.yview_moveto(0)


def split_panes(panes, fraction):
    """Keep the divider of a two-pane ttk.PanedWindow at `fraction` of its width.

    Without this the panes are sized from what their widgets ask for, which can push the
    right-hand pane past the edge of the window."""
    last = {"width": 0}

    def place(event):
        if event.width != last["width"] and event.width > 1:
            last["width"] = event.width
            panes.sashpos(0, int(event.width * fraction))

    panes.bind("<Configure>", place, add="+")


# ---------------------------------------------------------------------------- table
class DataTable(ttk.Frame):
    """ttk.Treeview with scrollbars, click-to-sort headings and an empty-state message.

    columns: list of (key, heading, width, anchor). Rows are dicts; display values come from
    formatters[key](value) when given, otherwise str(value).
    """

    def __init__(self, parent, columns, height=10, formatters=None, on_select=None, on_open=None,
                 empty_text="No records to show."):
        super().__init__(parent, style="Card.TFrame")
        self.columns = columns
        self.formatters = formatters or {}
        self.on_select = on_select
        self.empty_text = empty_text
        self.rows = {}           # Treeview item id -> row dict
        self.sort_key = None
        self.sort_reverse = False
        self.tag_fn = None
        keys = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=keys, show="headings", height=height, selectmode="browse")
        for key, heading, width, anchor in columns:
            self.tree.heading(key, text=heading, anchor=anchor, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, minwidth=40, anchor=anchor, stretch=True)
        ys = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.empty = ttk.Label(self, text=empty_text, style="CardMuted.TLabel")
        for name, colour in {**styles.CATEGORY_TINTS, **styles.SEVERITY_TINTS}.items():
            self.tree.tag_configure(name, background=colour)
        self.tree.tag_configure("muted", foreground=styles.MUTED)
        if on_select:
            self.tree.bind("<<TreeviewSelect>>", lambda e: on_select(self.selected()))
        if on_open:
            self.tree.bind("<Double-1>", lambda e: self.selected() and on_open(self.selected()))
            self.tree.bind("<Return>", lambda e: self.selected() and on_open(self.selected()))

    def set_rows(self, rows, tag_fn=None, keep_selection=True):
        """Replace all rows. tag_fn(row) may return a tag name used to tint the row."""
        before = self.selected_key() if keep_selection else None
        self.tag_fn = tag_fn
        self._all = list(rows)
        if self.sort_key:
            self._all = self._sorted(self._all)
        self._fill(self._all)
        if before is not None:
            self.select_where(lambda r: self._identity(r) == before)

    def _fill(self, rows):
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for row in rows:
            values = [self.formatters[k](row.get(k)) if k in self.formatters else
                      ("—" if row.get(k) is None else row.get(k)) for k, *_ in self.columns]
            tag = self.tag_fn(row) if self.tag_fn else None
            iid = self.tree.insert("", "end", values=values, tags=(tag,) if tag else ())
            self.rows[iid] = row
        if rows:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

    def _sorted(self, rows):
        key = self.sort_key
        present = [r for r in rows if r.get(key) is not None]
        missing = [r for r in rows if r.get(key) is None]  # missing values always go last
        try:
            present.sort(key=lambda r: r[key], reverse=self.sort_reverse)
        except TypeError:
            present.sort(key=lambda r: str(r[key]), reverse=self.sort_reverse)
        return present + missing

    def sort_by(self, key):
        """Click a heading: sort by it; click again to reverse."""
        self.sort_reverse = not self.sort_reverse if self.sort_key == key else False
        self.sort_key = key
        before = self.selected_key()
        self._all = self._sorted(getattr(self, "_all", []))
        self._fill(self._all)
        if before is not None:
            self.select_where(lambda r: self._identity(r) == before)
        for k, heading, *_ in self.columns:
            arrow = (" ▼" if self.sort_reverse else " ▲") if k == key else ""
            self.tree.heading(k, text=heading + arrow)

    @staticmethod
    def _identity(row):
        """What identifies a row across reloads (id, code, or the whole row)."""
        return row.get("id", row.get("code", tuple(sorted(map(str, row.items())))))

    def selected(self):
        """The selected row dict, or None."""
        chosen = self.tree.selection()
        return self.rows.get(chosen[0]) if chosen else None

    def selected_key(self):
        row = self.selected()
        return None if row is None else self._identity(row)

    def select_where(self, test):
        """Select (and scroll to) the first row for which test(row) is true."""
        for iid, row in self.rows.items():
            if test(row):
                self.tree.selection_set(iid)
                self.tree.focus(iid)
                self.tree.see(iid)
                return True
        return False

    def count(self):
        """Number of rows shown."""
        return len(self.rows)


# ---------------------------------------------------------------------------- chart
class ChartPanel(ttk.Frame):
    """Holds one Matplotlib Figure drawn with FigureCanvasTkAgg; show() swaps in a new figure."""

    def __init__(self, parent, height=260, style="Card.TFrame"):
        super().__init__(parent, style=style)
        self.height = height
        self.canvas = None
        self.figure = None

    def show(self, figure):
        """Replace the current chart with `figure`."""
        if self.canvas is not None:
            self.canvas.get_tk_widget().destroy()
            self.canvas = None
            # free the old chart now, on the main thread; Tk images must not be deleted from another thread
            gc.collect()
        self.figure = figure
        self.canvas = FigureCanvasTkAgg(figure, master=self)
        widget = self.canvas.get_tk_widget()
        # ask for a modest size; pack(fill/expand) then stretches the chart to the space available
        widget.configure(width=200, height=self.height, bg=CARD, highlightthickness=0)
        widget.pack(fill="both", expand=True)
        self.canvas.draw()


# ---------------------------------------------------------------------------- forms
class Form(ttk.Frame):
    """Two-column grid of labelled inputs. add() returns the variable holding the value."""

    def __init__(self, parent, style="Card.TFrame", label_style="Card.TLabel", columns=1):
        super().__init__(parent, style=style)
        self.label_style = label_style
        self.columns = columns
        self.fields = {}
        self._next = 0
        for c in range(columns):
            self.columnconfigure(c * 2 + 1, weight=1)

    def add(self, key, label, kind="entry", values=None, default="", width=24, hint=None):
        """Add an input. kind: entry, combo (pick from values), editcombo (pick or type), spin."""
        var = tk.StringVar(value=str(default))
        row, col = divmod(self._next, self.columns)
        self._next += 1
        ttk.Label(self, text=label, style=self.label_style).grid(row=row * 2, column=col * 2, sticky="w",
                                                                 padx=(0 if col == 0 else 16, 8), pady=(4, 0))
        if kind == "combo":
            widget = ttk.Combobox(self, textvariable=var, values=values or [], state="readonly", width=width)
        elif kind == "editcombo":
            widget = ttk.Combobox(self, textvariable=var, values=values or [], width=width)
        elif kind == "spin":
            low, high, step = values
            widget = ttk.Spinbox(self, textvariable=var, from_=low, to=high, increment=step, width=width)
        else:
            widget = ttk.Entry(self, textvariable=var, width=width)
        widget.grid(row=row * 2, column=col * 2 + 1, sticky="ew", pady=(4, 0))
        if hint:
            ttk.Label(self, text=hint, style="CardMuted.TLabel").grid(row=row * 2 + 1, column=col * 2 + 1,
                                                                      sticky="w")
        self.fields[key] = (var, widget)
        return var

    def values(self):
        """{key: text typed or chosen}."""
        return {key: var.get().strip() for key, (var, _w) in self.fields.items()}

    def widget(self, key):
        return self.fields[key][1]

    def set(self, key, value):
        self.fields[key][0].set("" if value is None else str(value))

    def clear(self, keep=()):
        for key, (var, _w) in self.fields.items():
            if key not in keep:
                var.set("")


def bullet_list(parent, lines, style="Card.TLabel", wraplength=420):
    """Labels with a bullet in front of each line (clears the parent first)."""
    for child in parent.winfo_children():
        child.destroy()
    for line in lines:
        ttk.Label(parent, text="•  " + line, style=style, wraplength=wraplength, justify="left").pack(
            anchor="w", pady=1)


def choice_label(code, name):
    """'SPR-01 — Old Market' for comboboxes."""
    return f"{code} — {name}"


def code_from_choice(text):
    """'SPR-01 — Old Market' -> 'SPR-01'."""
    return text.split(" — ")[0].strip()


def wrap_on_resize(label, padding=24):
    """Keep a label's wraplength equal to its current width."""
    label.bind("<Configure>", lambda e: label.configure(wraplength=max(200, e.width - padding)))


def caps(parent, text, style="CardCaps.TLabel"):
    """Small capitals heading inside a card."""
    lab = ttk.Label(parent, text=text.upper(), style=style)
    lab.pack(anchor="w", pady=(8, 2))
    return lab
