"""Heatwave Risk Assessment: the risk engine's results, explained location by location.

Scores, categories and reasons all come from noor/risk.py (RiskEngine). The weights box lets
an examiner try other weights: that is a preview only and is not saved.
"""
from tkinter import ttk

from .. import charts, settings
from ..summaries import (WEIGHT_LABELS, data_note_for, indicator_rows, method_text,
                         recommended_actions)
from .widgets import (split_panes, Card, ChartPanel, DataTable, Form, Page, ScrollableFrame, bullet_list, caps, fmt,
                      when)

ALL = "All categories"
CATEGORY_NAMES = [name for _t, name in settings.CATEGORIES] + ["Insufficient data"]


class RiskPage(Page):
    title = "Risk Assessment"
    subtitle = "Heat-risk score, category and the reasons behind it for every location."

    def build(self):
        self.weights = None  # None = saved assessment; a dict = what-if preview
        self.rows = []
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)
        split_panes(panes, 0.62)
        left = ttk.Frame(panes)
        right = ttk.Frame(panes)
        panes.add(left, weight=3)
        panes.add(right, weight=2)

        table_card = Card(left)
        table_card.pack(fill="both", expand=True)
        bar = ttk.Frame(table_card.body, style="Card.TFrame")
        bar.pack(fill="x", pady=(0, 8))
        form = Form(bar, columns=2)
        self.f_category = form.add("category", "Category", "combo", values=[ALL] + CATEGORY_NAMES, default=ALL,
                                   width=16)
        self.f_search = form.add("search", "Search", width=16)
        form.pack(side="left")
        form.widget("category").bind("<<ComboboxSelected>>", lambda e: self.fill_table())
        form.widget("search").bind("<KeyRelease>", lambda e: self.fill_table())
        ttk.Button(bar, text="Recalculate and save", style="Accent.TButton",
                   command=self.recalculate).pack(side="right", anchor="s")
        self.mode = ttk.Label(table_card.body, text="", style="CardMuted.TLabel")
        self.mode.pack(fill="x", pady=(0, 4))
        self.table = DataTable(table_card.body, [
            ("code", "Code", 62, "w"), ("name", "Location", 118, "w"), ("score", "Score", 52, "e"),
            ("category", "Category", 82, "w"), ("confidence", "Confidence", 78, "w"),
            ("hazard", "Hazard", 58, "e"), ("exposure", "Exposure", 64, "e"),
            ("vulnerability", "Vulner.", 58, "e"), ("capacity", "Capacity", 64, "e"),
        ], height=12, formatters={"score": lambda v: fmt(v, 1), **{k: (lambda v: fmt(v, 2)) for k in
                                  ("hazard", "exposure", "vulnerability", "capacity")}},
            on_select=lambda row: row and self.show_location(row["code"], select=False))
        self.table.pack(fill="both", expand=True)

        weights_card = Card(left, "Method and what-if weights", method_text())
        weights_card.pack(fill="x", pady=(10, 0))
        wform = Form(weights_card.body, columns=4)
        for key, label in WEIGHT_LABELS.items():
            wform.add(key, label, width=6, default=settings.RISK_WEIGHTS[key])
        wform.pack(fill="x")
        self.weight_form = wform
        wbar = ttk.Frame(weights_card.body, style="Card.TFrame")
        wbar.pack(fill="x", pady=(8, 0))
        ttk.Button(wbar, text="Preview with these weights", command=self.preview).pack(side="left")
        ttk.Button(wbar, text="Back to saved results", command=self.back_to_saved).pack(side="left", padx=8)
        ttk.Label(wbar, text="Weights must add up to 1.0. A preview is not saved.",
                  style="CardMuted.TLabel").pack(side="left", padx=8)

        scroll = ScrollableFrame(right)
        scroll.pack(fill="both", expand=True, padx=(12, 0))
        self.detail_scroll = scroll
        detail = Card(scroll.inner)
        detail.pack(fill="both", expand=True)
        body = detail.body
        self.d_name = ttk.Label(body, text="Select a location", style="CardH2.TLabel")
        self.d_name.pack(anchor="w")
        self.d_meta = ttk.Label(body, text="", style="CardMuted.TLabel")
        self.d_meta.pack(anchor="w")
        self.d_score = ttk.Label(body, text="", style="AccentNumber.TLabel")
        self.d_score.pack(anchor="w", pady=(6, 0))
        self.d_confidence = ttk.Label(body, text="", style="CardMuted.TLabel")
        self.d_confidence.pack(anchor="w")
        caps(body, "Why this score")
        self.d_reasons = ttk.Frame(body, style="Card.TFrame")
        self.d_reasons.pack(fill="x")
        caps(body, "Recommended response")
        self.d_actions = ttk.Frame(body, style="Card.TFrame")
        self.d_actions.pack(fill="x")
        caps(body, "Dimensions")
        self.d_chart = ChartPanel(body, height=210)
        self.d_chart.pack(fill="x")
        caps(body, "Indicators used")
        self.d_table = DataTable(body, [("dimension", "Dimension", 95, "w"), ("indicator", "Indicator", 140, "w"),
                                        ("value", "Value", 80, "e"), ("normalised", "0-1", 45, "e"),
                                        ("weight", "Weight", 50, "e")], height=10,
                                 formatters={"normalised": lambda v: fmt(v, 2), "weight": lambda v: fmt(v, 2)})
        self.d_table.pack(fill="x")
        self.d_data = ttk.Label(body, text="", style="CardMuted.TLabel", justify="left")
        self.d_data.pack(anchor="w", pady=(8, 0))
        self.current_code = None

    # ------------------------------------------------------------------ table
    def refresh(self):
        if self.weights is None:
            saved = self.db.latest_assessments()
            for r in saved:
                r["as_of"] = r["as_of_date"]
            self.rows = saved
            stamp = saved[0]["assessed_at"] if saved else None
            self.mode.configure(text=f"Saved assessment from {when(stamp)} (standard weights from settings.py).")
        self.fill_table()
        code = self.current_code or (self.rows[0]["code"] if self.rows else None)
        if code:
            self.show_location(code)

    def fill_table(self):
        category = self.f_category.get()
        text = self.f_search.get().strip().lower()
        rows = [r for r in self.rows
                if (category in ("", ALL) or r["category"] == category)
                and (not text or text in r["code"].lower() or text in r["name"].lower())]
        self.table.set_rows(rows, tag_fn=lambda r: r["category"])

    def recalculate(self):
        self.weights = None
        self.app.run_task("Recalculating risk", lambda svc: svc.recalculate(), self._recalculated)

    def _recalculated(self, results):
        self.app.data_changed()
        self.app.set_status(f"Risk recalculated and saved for {len(results)} locations.", "ok")

    def preview(self):
        weights = {k: v for k, v in self.weight_form.values().items()}
        results = self.svc.assess(weights)  # RiskEngine.check_weights validates them
        self.weights = {k: float(v) for k, v in weights.items()}
        self.rows = sorted(results, key=lambda r: (r["score"] is None, -(r["score"] or 0)))
        text = ", ".join(f"{WEIGHT_LABELS[k]} {v:.2f}" for k, v in self.weights.items())
        self.mode.configure(text=f"PREVIEW with weights {text}. Not saved.")
        self.fill_table()
        if self.current_code:
            self.show_location(self.current_code)
        self.app.set_status("Preview calculated with your weights (not saved).", "ok")

    def back_to_saved(self):
        self.weights = None
        for key in WEIGHT_LABELS:
            self.weight_form.set(key, settings.RISK_WEIGHTS[key])
        self.refresh()

    # ------------------------------------------------------------------ detail
    def show_location(self, code, select=True):
        """Explain one location (opened from the table or from another screen)."""
        result = self.svc.assessment(code, self.weights)
        self.current_code = code
        if select:
            self.table.select_where(lambda r: r["code"] == code)
        loc = self.db.get_location(code)
        self.d_name.configure(text=f"{result['name']} ({code})")
        self.d_meta.configure(text=f"{loc['region']} · population {fmt(loc['population'])} · data: "
                                   f"{settings.DATA_KINDS.get(loc['source_kind'], loc['source_kind'])}",
                              wraplength=self.detail_width())
        score = "No score" if result["score"] is None else f"{result['score']:.1f}"
        self.d_score.configure(text=f"{score}  {result['category']}")
        self.d_confidence.configure(text=f"Confidence: {result['confidence']} · as of {result['as_of']}")
        wrap = self.detail_width()
        bullet_list(self.d_reasons, result["reasons"], wraplength=wrap)

        bullet_list(self.d_actions, recommended_actions(self.db, code), wraplength=wrap)
        self.d_chart.show(charts.dimension_chart(result))
        self.d_table.set_rows(indicator_rows(result), keep_selection=False)
        self.d_data.configure(text=data_note_for(result) + (" Preview weights in use." if self.weights else ""),
                              wraplength=wrap)

    def detail_width(self):
        """Text width that fits the detail panel."""
        self.update_idletasks()
        return max(260, self.detail_scroll.winfo_width() - 70)
