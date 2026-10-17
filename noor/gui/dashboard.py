"""Overview dashboard: headline numbers, risk distribution, situation summary, locations, activity.

Every number is read from the database or computed by the engines when the screen loads.
"""
from tkinter import ttk

from .. import charts
from ..allocation import HIGH_CATEGORIES
from .widgets import (RULE_LABELS, Card, ChartPanel, DataTable, Page, ScrollableFrame, bullet_list, fmt, pct,
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
        latest = self.db.latest_assessments()
        locations = self.db.list_locations()
        active = self.db.list_alerts(status="active")
        resources = self.db.list_resources()
        status = self.svc.status()

        high = [a for a in latest if a["category"] in HIGH_CATEGORIES]
        severity = {s: sum(1 for a in active if a["severity"] == s) for s in ("emergency", "warning", "advisory")}
        by_status = {s: sum(1 for r in resources if r["status"] == s) for s in ("available", "limited", "offline")}
        self.tiles["locations"].set(str(len(locations)), f"{len({l['region'] for l in locations})} region(s)")
        self.tiles["high"].set(str(len(high)), f"of {len(latest)} assessed locations")
        self.tiles["alerts"].set(str(len(active)), f"{severity['emergency']} emergency · {severity['warning']} warning · "
                                                   f"{severity['advisory']} advisory")
        self.tiles["resources"].set(f"{by_status['available']} / {len(resources)}",
                                    f"{by_status['limited']} limited · {by_status['offline']} offline")
        latest_day = status["latest_observation"]
        self.tiles["latest"].set(latest_day or "—", "Synthetic demo data" if status["synthetic_only"]
                                 else ", ".join(status["data_kinds"]))
        stamp = latest[0]["assessed_at"] if latest else None
        self.assessed.configure(text=f"Last risk calculation: {when(stamp)}")

        self.chart.show(charts.risk_distribution(latest))
        self.table.set_rows(latest, tag_fn=lambda r: r["category"])
        self._summary(latest, high, active, severity, status)
        self._activity()

    def _summary(self, latest, high, active, severity, status):
        lines = []
        scored = [a for a in latest if a["score"] is not None]
        if not latest:
            lines.append("No assessments yet. Press Recalculate risk.")
        else:
            as_of = max(a["as_of_date"] for a in latest)
            names = ", ".join(f"{a['name']} ({a['category']})" for a in high[:4])
            lines.append(f"As of {as_of}, {len(high)} of {len(latest)} locations are at High risk or above"
                         + (f": {names}" + (" and others." if len(high) > 4 else ".") if high else "."))
            if scored:
                top = scored[0]  # latest_assessments() is ordered by score, highest first
                reasons = top["reasons"].split(" | ")
                lines.append(f"Highest score: {top['name']} ({top['code']}) at {top['score']:.1f}, {top['category']}. "
                             + (reasons[1] if len(reasons) > 1 else ""))
        lines.append(f"{len(active)} active alerts: {severity['emergency']} emergency, {severity['warning']} warning, "
                     f"{severity['advisory']} advisory.")
        plan = self.svc.plan("risk_first")
        coverage = plan["total_served"] / plan["total_demand"] if plan["total_demand"] else None
        lines.append(f"The risk-first resource plan can serve {pct(coverage)} of estimated daily demand "
                     f"(risk-weighted coverage {pct(plan['risk_weighted_coverage'])}); "
                     f"{len(plan['high_risk_with_gaps'])} high-risk location(s) still have unmet needs.")
        if status["synthetic_only"]:
            lines.append("All data is synthetic demonstration data for a fictional district, not IMD observations.")
        lines.append("NOOR supports preparedness. It does not replace IMD or SDMA warnings.")
        bullet_list(self.summary, lines, wraplength=520)

    def _activity(self):
        events = []
        batch = self.db.fetch_one("SELECT MAX(assessed_at) AS t, COUNT(*) AS n FROM risk_assessments "
                                  "WHERE assessed_at = (SELECT MAX(assessed_at) FROM risk_assessments)")
        if batch["t"]:
            events.append({"time": batch["t"], "event": f"Risk recalculated for {batch['n']} locations"})
        for a in self.db.fetch_all("""SELECT a.id, a.issued_at, a.severity, a.rule, l.name
                                      FROM alerts a JOIN locations l ON l.id = a.location_id
                                      ORDER BY a.issued_at DESC, a.id DESC LIMIT 8"""):
            events.append({"time": a["issued_at"], "event": f"{a['severity'].title()} alert: {a['name']} "
                                                            f"({RULE_LABELS.get(a['rule'], a['rule'])})"})
        for p in self.db.list_plans()[:4]:
            events.append({"time": p["created_at"], "event": f"Plan saved: {p['plan_name']}"})
        events.sort(key=lambda e: e["time"], reverse=True)
        self.activity.set_rows(events[:12], keep_selection=False)

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
