"""Overview dashboard: headline numbers, risk distribution, situation summary, locations, activity.

Every number is read from the database or computed by the engines when the screen loads.
"""
from tkinter import ttk

from .. import charts
from ..summaries import overview_numbers, recent_activity, situation_summary
from .widgets import (Card, ChartPanel, DataTable, Page, ScrollableFrame, bullet_list, fmt,
                      tile_row, when)


class DashboardPage(Page):
    title = "Overview"
    subtitle = "Current heat-risk situation across all monitored locations, from the latest saved assessment."

    def build(self):
        bar = self.toolbar()
        ttk.Button(bar, text="Run warning rules", command=self.run_alerts).pack(side="right")
        ttk.Button(bar, text="Recalculate risk", style="Accent.TButton",
                   command=self.recalculate).pack(side="right", padx=(0, 8))
        self.assessed = ttk.Label(bar, text="", style="Muted.TLabel")
        self.assessed.pack(side="left")

        scroll = ScrollableFrame(self)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner

        self.tiles = tile_row(body, [
            ("locations", "Monitored locations", False),
            ("high", "High risk or above", True),
            ("alerts", "Active heatwave alerts", True),
            ("resources", "Resources available", False),
            ("latest", "Latest observation", False),
        ])

        middle = ttk.Frame(body)
        middle.pack(fill="x", pady=(0, 12))
        middle.columnconfigure(0, weight=5, uniform="mid")
        middle.columnconfigure(1, weight=6, uniform="mid")
        chart_card = Card(middle, "Risk distribution", "Number of locations in each category of the risk engine.")
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.chart = ChartPanel(chart_card.body, height=250)
        self.chart.pack(fill="both", expand=True)
        summary_card = Card(middle, "Situation summary", "Written from the computed numbers on this screen.")
        summary_card.grid(row=0, column=1, sticky="nsew")
        self.summary = ttk.Frame(summary_card.body, style="Card.TFrame")
        self.summary.pack(fill="both", expand=True)

        bottom = ttk.Frame(body)
        bottom.pack(fill="both", expand=True)
        bottom.columnconfigure(0, weight=6, uniform="bottom")
        bottom.columnconfigure(1, weight=5, uniform="bottom")
        table_card = Card(bottom, "Locations by current risk", "Double-click a location to see why it got its score.")
        table_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.table = DataTable(table_card.body, [
            ("code", "Code", 70, "w"), ("name", "Location", 150, "w"), ("score", "Score", 60, "e"),
            ("category", "Category", 110, "w"), ("confidence", "Confidence", 90, "w"),
            ("as_of_date", "As of", 90, "w"),
        ], height=9, formatters={"score": lambda v: fmt(v, 1)}, on_open=self.open_location)
        self.table.pack(fill="both", expand=True)
        activity_card = Card(bottom, "Recent monitoring activity", "Latest recalculations, alerts and saved plans.")
        activity_card.grid(row=0, column=1, sticky="nsew")
        self.activity = DataTable(activity_card.body, [("time", "When", 140, "w"), ("event", "Activity", 320, "w")],
                                  height=9, formatters={"time": when})
        self.activity.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ data
    def refresh(self):
        n = overview_numbers(self.svc)
        latest, status, severity, by_status = n["latest"], n["status"], n["severity"], n["by_status"]
        self.tiles["locations"].set(str(len(n["locations"])), f"{n['regions']} region(s)")
        self.tiles["high"].set(str(len(n["high"])), f"of {len(latest)} assessed locations")
        self.tiles["alerts"].set(str(len(n["active"])), f"{severity['emergency']} emergency · "
                                                        f"{severity['warning']} warning · {severity['advisory']} advisory")
        self.tiles["resources"].set(f"{by_status['available']} / {len(n['resources'])}",
                                    f"{by_status['limited']} limited · {by_status['offline']} offline")
        self.tiles["latest"].set(status["latest_observation"] or "—", "Synthetic demo data" if status["synthetic_only"]
                                 else ", ".join(status["data_kinds"]))
        self.assessed.configure(text=f"Last risk calculation: {when(n['assessed_at'])}")
        self.chart.show(charts.risk_distribution(latest))
        self.table.set_rows(latest, tag_fn=lambda r: r["category"])
        bullet_list(self.summary, situation_summary(self.svc, n), wraplength=520)
        self.activity.set_rows(recent_activity(self.db), keep_selection=False)

    # ------------------------------------------------------------------ actions
    def recalculate(self):
        self.app.run_task("Recalculating risk", lambda svc: svc.recalculate(), self._recalculated)

    def _recalculated(self, results):
        self.app.data_changed()
        self.app.set_status(f"Risk recalculated for {len(results)} locations.", "ok")

    def run_alerts(self):
        self.app.run_task("Running the warning rules", lambda svc: svc.run_alerts(), self._alerts_done)

    def _alerts_done(self, result):
        new, found = result
        self.app.data_changed()
        self.app.set_status(f"Warning rules fired {found} time(s); {new} new alert(s) saved "
                            f"(alerts already on record are not repeated).", "ok")

    def open_location(self, row):
        self.app.page("risk").show_location(row["code"])
