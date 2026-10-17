"""The dark navigation column on the left: wordmark, one button per screen, data notice."""
import tkinter as tk

from .styles import CHARCOAL, CHARCOAL_2, FONTS, SAND, SIDEBAR_MUTED, SIDEBAR_TEXT, WINE


class Sidebar(tk.Frame):
    """Navigation. Calls on_select(key) when a screen is chosen (mouse, Tab + Enter, or Ctrl+number)."""

    def __init__(self, parent, pages, on_select):
        """pages: list of (key, label)."""
        super().__init__(parent, bg=CHARCOAL, width=232)
        self.pack_propagate(False)
        self.on_select = on_select
        self.items = {}
        self.badges = {}
        self.active = None

        brand = tk.Frame(self, bg=CHARCOAL)
        brand.pack(fill="x", padx=22, pady=(24, 18))
        tk.Label(brand, text="N O O R", bg=CHARCOAL, fg=SAND, font=FONTS["wordmark"]).pack(anchor="w")
        tk.Label(brand, text="Climate Intelligence", bg=CHARCOAL, fg=SIDEBAR_TEXT,
                 font=FONTS["body"]).pack(anchor="w")
        tk.Label(brand, text="See the risk. Save lives.", bg=CHARCOAL, fg=SIDEBAR_MUTED,
                 font=(FONTS["small"][0], 9, "italic")).pack(anchor="w", pady=(2, 0))
        tk.Frame(self, bg="#34343A", height=1).pack(fill="x", padx=22, pady=(0, 10))

        for number, (key, label) in enumerate(pages, start=1):
            row = tk.Frame(self, bg=CHARCOAL)
            row.pack(fill="x")
            bar = tk.Frame(row, bg=CHARCOAL, width=4)
            bar.pack(side="left", fill="y")
            button = tk.Button(row, text=label, anchor="w", relief="flat", bd=0, padx=18, pady=8,
                               bg=CHARCOAL, fg=SIDEBAR_TEXT, activebackground=CHARCOAL_2, activeforeground=SAND,
                               font=FONTS["nav"], cursor="hand2", highlightthickness=1,
                               highlightbackground=CHARCOAL, highlightcolor=WINE, takefocus=1,
                               command=lambda k=key: self.on_select(k))
            button.pack(side="left", fill="x", expand=True)
            badge = tk.Label(row, text="", bg=CHARCOAL, fg=SAND, font=FONTS["caps"], padx=6)
            badge.pack(side="right", padx=(0, 14))
            button.bind("<Enter>", lambda e, k=key: self._hover(k, True))
            button.bind("<Leave>", lambda e, k=key: self._hover(k, False))
            button.bind("<Return>", lambda e, k=key: self.on_select(k))
            self.items[key] = (row, bar, button)
            self.badges[key] = badge
            parent.winfo_toplevel().bind(f"<Control-Key-{number}>", lambda e, k=key: self.on_select(k))

        foot = tk.Frame(self, bg=CHARCOAL)
        foot.pack(side="bottom", fill="x", padx=22, pady=18)
        self.notice = tk.Label(foot, text="", bg=CHARCOAL, fg="#E7B9C1", font=FONTS["small"], justify="left",
                               wraplength=188, anchor="w")
        self.notice.pack(fill="x")
        tk.Label(foot, text="Offline desktop app · SQLite", bg=CHARCOAL, fg=SIDEBAR_MUTED,
                 font=FONTS["small"], anchor="w").pack(fill="x", pady=(6, 0))
        tk.Label(foot, text="Ctrl+1…8 switch screens · F5 reload", bg=CHARCOAL, fg=SIDEBAR_MUTED,
                 font=FONTS["small"], anchor="w").pack(fill="x")

    def _paint(self, key, background, foreground, bar_colour):
        row, bar, button = self.items[key]
        for widget in (row, button):
            widget.configure(bg=background)
        badge = self.badges[key]
        badge.configure(bg=WINE if badge.cget("text") else background)
        button.configure(fg=foreground)
        bar.configure(bg=bar_colour)

    def _hover(self, key, inside):
        if key != self.active:
            self._paint(key, CHARCOAL_2 if inside else CHARCOAL, SAND if inside else SIDEBAR_TEXT, CHARCOAL)

    def set_active(self, key):
        """Highlight the current screen."""
        if self.active and self.active in self.items:
            self._paint(self.active, CHARCOAL, SIDEBAR_TEXT, CHARCOAL)
        self.active = key
        self._paint(key, CHARCOAL_2, SAND, WINE)

    def set_badge(self, key, count):
        """Show a small count next to a screen name (hidden when zero)."""
        badge = self.badges[key]
        if count:
            badge.configure(text=str(count), bg=WINE)
        else:
            badge.configure(text="", bg=self.items[key][2].cget("bg"))

    def set_notice(self, text):
        """Data notice at the bottom (e.g. synthetic demonstration data)."""
        self.notice.configure(text=text)

