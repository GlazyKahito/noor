"""Colours, fonts and ttk styles: the whole look of the app is defined in this one file."""
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ---------------------------------------------------------------------------- colours
SAND = "#F5EBD0"         # window background
SAND_DARK = "#EADFC2"    # table headings, inactive tabs
CARD = "#FFFBF2"         # cards, tables, charts
LINE = "#E1D2AE"         # borders
WINE = "#7F011F"         # primary accent
WINE_DARK = "#5E0017"    # pressed accent
WINE_TINT = "#F4DADD"    # light wine wash
CHARCOAL = "#171719"     # sidebar
CHARCOAL_2 = "#26262B"   # sidebar hover
SIDEBAR_TEXT = "#D8CDB4"
SIDEBAR_MUTED = "#8F8573"
INK = "#1F1A17"          # main text
MUTED = "#6B5E4B"        # secondary text
OK = "#3F6B2E"           # success messages
WARN = "#9A5B00"         # caution messages

# Row tints for risk categories and alert severities (text stays dark and readable)
CATEGORY_TINTS = {
    "Extreme": "#E9C3C8",
    "Severe": "#F3D9DB",
    "High": "#F7E3D2",
    "Moderate": "#FBF0D6",
    "Low": CARD,
    "Insufficient data": "#ECE7DA",
}
SEVERITY_TINTS = {
    "emergency": "#E9C3C8",
    "warning": "#F3D9DB",
    "advisory": "#F7E3D2",
    "info": CARD,
}
SEVERITY_COLOURS = {"emergency": "#3E0010", "warning": WINE, "advisory": "#A9481F", "info": MUTED}

# ---------------------------------------------------------------------------- fonts
# Filled in by apply_styles() once Tk is running (font families can only be read then).
FONTS = {}


def _pick(families, wanted):
    """First installed family from the wanted list."""
    for name in wanted:
        if name in families:
            return name
    return wanted[-1]


def apply_styles(root):
    """Create the fonts and configure every ttk style used by the screens."""
    families = set(tkfont.families(root))
    body = _pick(families, ["Segoe UI", "Helvetica Neue", "DejaVu Sans", "Arial"])
    serif = _pick(families, ["Georgia", "Cambria", "DejaVu Serif", "Times New Roman"])
    mono = _pick(families, ["Consolas", "Menlo", "DejaVu Sans Mono", "Courier New"])
    FONTS.update({
        "body": (body, 10),
        "body_bold": (body, 10, "bold"),
        "small": (body, 9),
        "caps": (body, 8, "bold"),
        "title": (serif, 21, "bold"),
        "h2": (serif, 13, "bold"),
        "number": (body, 18, "bold"),
        "wordmark": (serif, 26, "bold"),
        "nav": (body, 10),
        "mono": (mono, 9),
    })
    root.configure(bg=SAND)
    root.option_add("*TCombobox*Listbox.font", FONTS["body"])
    root.option_add("*TCombobox*Listbox.selectBackground", WINE)

    style = ttk.Style(root)
    style.theme_use("clam")  # "clam" lets us set colours; the native Windows theme ignores most of them

    style.configure(".", background=SAND, foreground=INK, font=FONTS["body"], bordercolor=LINE,
                    lightcolor=CARD, darkcolor=LINE, troughcolor=SAND_DARK, focuscolor=WINE)
    style.configure("TFrame", background=SAND)
    style.configure("Card.TFrame", background=CARD)
    style.configure("TLabel", background=SAND, foreground=INK)
    style.configure("Muted.TLabel", background=SAND, foreground=MUTED, font=FONTS["small"])
    style.configure("Title.TLabel", background=SAND, foreground=WINE, font=FONTS["title"])
    style.configure("Card.TLabel", background=CARD, foreground=INK)
    style.configure("CardBold.TLabel", background=CARD, foreground=INK, font=FONTS["body_bold"])
    style.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=FONTS["small"])
    style.configure("CardCaps.TLabel", background=CARD, foreground=MUTED, font=FONTS["caps"])
    style.configure("CardH2.TLabel", background=CARD, foreground=INK, font=FONTS["h2"])
    style.configure("Number.TLabel", background=CARD, foreground=INK, font=FONTS["number"])
    style.configure("AccentNumber.TLabel", background=CARD, foreground=WINE, font=FONTS["number"])

    style.configure("TButton", background=CARD, foreground=INK, bordercolor=LINE, lightcolor=CARD,
                    darkcolor=CARD, padding=(12, 5), focusthickness=1, focuscolor=WINE)
    style.map("TButton", background=[("disabled", SAND), ("pressed", SAND_DARK), ("active", "#F3E8CD")],
              foreground=[("disabled", "#A99C83")])
    style.configure("Accent.TButton", background=WINE, foreground="white", bordercolor=WINE_DARK,
                    lightcolor=WINE, darkcolor=WINE_DARK)
    style.map("Accent.TButton", background=[("disabled", "#B58A93"), ("pressed", WINE_DARK), ("active", "#951232")],
              foreground=[("disabled", "#F5EBD0")])

    for widget in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(widget, fieldbackground="white", foreground=INK, bordercolor=LINE, lightcolor="white",
                        darkcolor=LINE, padding=4, arrowcolor=WINE, insertcolor=INK)
        style.map(widget, bordercolor=[("focus", WINE)], fieldbackground=[("readonly", "white")],
                  lightcolor=[("focus", WINE_TINT)])
    style.configure("TCheckbutton", background=CARD, foreground=INK, indicatorbackground="white",
                    indicatorforeground=WINE)
    style.map("TCheckbutton", background=[("active", CARD)])
    style.configure("Sand.TCheckbutton", background=SAND)
    style.map("Sand.TCheckbutton", background=[("active", SAND)])

    style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=25,
                    bordercolor=LINE, lightcolor=CARD, darkcolor=LINE, font=FONTS["body"])
    style.map("Treeview", background=[("selected", WINE)], foreground=[("selected", "white")])
    style.configure("Treeview.Heading", background=SAND_DARK, foreground=INK, font=FONTS["body_bold"],
                    bordercolor=LINE, lightcolor=SAND_DARK, darkcolor=LINE, relief="flat", padding=(6, 4))
    style.map("Treeview.Heading", background=[("active", "#E2D4B2")])

    style.configure("TNotebook", background=SAND, bordercolor=LINE, tabmargins=(0, 4, 0, 0))
    style.configure("TNotebook.Tab", background=SAND_DARK, foreground=MUTED, padding=(14, 6), bordercolor=LINE,
                    lightcolor=SAND_DARK, font=FONTS["body"])
    style.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", WINE)],
              lightcolor=[("selected", CARD)], font=[("selected", FONTS["body_bold"])])

    style.configure("TPanedwindow", background=SAND)
    style.configure("Vertical.TScrollbar", background=SAND_DARK, troughcolor=CARD, bordercolor=LINE,
                    arrowcolor=MUTED, lightcolor=SAND_DARK, darkcolor=LINE)
    style.configure("Horizontal.TScrollbar", background=SAND_DARK, troughcolor=CARD, bordercolor=LINE,
                    arrowcolor=MUTED, lightcolor=SAND_DARK, darkcolor=LINE)
    style.configure("Wine.Horizontal.TProgressbar", background=WINE, troughcolor=SAND_DARK, bordercolor=LINE,
                    lightcolor=WINE, darkcolor=WINE_DARK)
    style.configure("TSeparator", background=LINE)
    return style


def text_widget(parent, height=6, mono=False):
    """A read-only looking tk.Text that matches the cards."""
    return tk.Text(parent, height=height, wrap="word", bg=CARD, fg=INK, relief="flat", bd=0,
                   highlightthickness=1, highlightbackground=LINE, highlightcolor=WINE,
                   font=FONTS["mono"] if mono else FONTS["body"], padx=8, pady=6)
