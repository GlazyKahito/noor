"""Scenario Lab: change the inputs, rerun the real risk and allocation code, compare.

The calculation is Scenario.run() in noor/scenario.py. It runs on a background thread so the
window stays responsive. The result is a what-if with NOOR's own method, not a prediction.
"""
from tkinter import filedialog, ttk

from .. import charts, reports, settings
from ..scenario import LIMITS
from .resource_allocation import TYPE_LABELS
from .widgets import (split_panes, Card, ChartPanel, DataTable, Form, Page, ScrollableFrame, bullet_list, caps, fmt, pct,
                      tile_row)

# label, step for the spinbox
PARAMS = {
    "temperature_increase": ("Temperature increase (°C)", 0.5),
    "extra_hot_days": ("Extra hot days in the spell", 1),
    "new_cooling_centres": ("New cooling centres requested", 1),
    "water_capacity_pct": ("Water-point capacity (% of today)", 5),
    "medical_capacity_pct": ("Medical capacity (% of today)", 5),
    "budget_per_day": ("Budget for new centres (₹ per day)", 15000),
    "staff_available": ("Staff available for new centres", 1),
}


class ScenarioPage(Page):
    title = "Scenario Lab"
    subtitle = "What-if analysis: the same risk and allocation code rerun on changed inputs. Not a prediction."

    def build(self):
        self.result = None
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)
        split_panes(panes, 0.31)
        left = Card(panes, "Scenario settings",
                    f"Each new centre: {settings.NEW_CENTRE['places']} places/day, "
                    f"₹{settings.NEW_CENTRE['daily_cost']:,}/day, {settings.NEW_CENTRE['staff']} staff, "
                    f"{settings.NEW_CENTRE['radius_km']:g} km radius. Centres go where risk-weighted unmet "
                    f"cooling demand is largest.")
        panes.add(left, weight=1)
        form = Form(left.body)
        for name, (label, step) in PARAMS.items():
            low, high, default = LIMITS[name]
            form.add(name, label, "spin", values=(low, high, step), default=default, width=12,
                     hint=f"{low:g} to {high:,g}")
        form.pack(fill="x")
        self.form = form
        buttons = ttk.Frame(left.body, style="Card.TFrame")
        buttons.pack(fill="x", pady=(14, 0))
        self.run_button = ttk.Button(buttons, text="Run scenario", style="Accent.TButton", command=self.run)
        self.run_button.pack(side="left")
        ttk.Button(buttons, text="Reset", command=self.reset).pack(side="left", padx=8)
        ttk.Button(buttons, text="Export…", command=self.export).pack(side="left")

        scroll = ScrollableFrame(panes)
        panes.add(scroll, weight=3)
        body = scroll.inner
        body.configure(padding=(12, 0, 0, 0))
        self.tiles = tile_row(body, [
            ("mean", "Mean risk score", True), ("high", "High risk or above", True),
            ("unmet", "Unmet demand / day", False), ("centres", "New centres placed", False),
        ])
        explain = Card(body, "What changed")
        explain.pack(fill="x", pady=(0, 12))
        self.explain = ttk.Frame(explain.body, style="Card.TFrame")
        self.explain.pack(fill="x")
        chart_card = Card(body)
        chart_card.pack(fill="x", pady=(0, 12))
        self.chart = ChartPanel(chart_card.body, height=270)
        self.chart.pack(fill="x")
        tables = Card(body, "Details")
        tables.pack(fill="both", expand=True)
        caps(tables.body, "Resources by type: before → after")
        self.type_table = DataTable(tables.body, [
            ("label", "Type", 170, "w"), ("unmet_before", "Unmet before", 95, "e"), ("unmet_after", "Unmet after", 90, "e"),
            ("coverage_before", "Coverage before", 105, "e"), ("coverage_after", "Coverage after", 100, "e"),
            ("utilisation_after", "Use after", 80, "e"),
        ], height=5, formatters={"unmet_before": fmt, "unmet_after": fmt, "coverage_before": pct,
                                 "coverage_after": pct, "utilisation_after": pct})
        self.type_table.pack(fill="x")
        caps(tables.body, "Locations: score before → after (largest change first)")
        self.loc_table = DataTable(tables.body, [
            ("code", "Code", 70, "w"), ("name", "Location", 140, "w"), ("score_before", "Before", 65, "e"),
            ("score_after", "After", 65, "e"), ("change", "Change", 65, "e"), ("category_before", "Category before", 115, "w"),
            ("category_after", "Category after", 110, "w"),
        ], height=10, formatters={"score_before": lambda v: fmt(v, 1), "score_after": lambda v: fmt(v, 1),
                                  "change": lambda v: "—" if v is None else f"{v:+.1f}"})
        self.loc_table.pack(fill="x")

    def refresh(self):
        if self.result is None:
            self.run()

    def params(self):
        """The spinbox values (Scenario() checks every limit and rejects bad input)."""
        return self.form.values()

    def run(self):
        params = self.params()  # read on the main thread; only the calculation runs in the background
        self.app.run_task("Running the scenario", lambda svc: svc.scenario(params), self.show)

    def show(self, result):
        self.result = result
        c = result["comparison"]
        self.tiles["mean"].set(f"{fmt(c['mean_score_before'], 1)} → {fmt(c['mean_score_after'], 1)}", "average of all scored locations")
        self.tiles["high"].set(f"{c['high_before']} → {c['high_after']}", "locations High, Severe or Extreme")
        self.tiles["unmet"].set(f"{fmt(c['unmet_before'])} → {fmt(c['unmet_after'])}", "people or visits per day")
        limited = " (limited by " + " and ".join(result["limited_by"]) + ")" if result["limited_by"] else ""
        self.tiles["centres"].set(str(len(result["placed_centres"])),
                                  f"₹{result['extra_cost_per_day']:,}/day extra{limited}")
        bullet_list(self.explain, self._explanation(result), wraplength=760)
        self.chart.show(charts.scenario_chart(c))
        self.type_table.set_rows([{"id": r["type"], "label": TYPE_LABELS[r["type"]], **r} for r in c["by_type"]])
        rows = sorted(c["locations"], key=lambda r: (r["change"] is None, -abs(r["change"] or 0)))
        self.loc_table.set_rows(rows, tag_fn=lambda r: r["category_after"])
        self.app.set_status("Scenario calculated (what-if only; nothing saved).", "ok")

    @staticmethod
    def _explanation(result):
        """Plain sentences built only from the calculated numbers."""
        p, c = result["params"], result["comparison"]
        lines = [f"Settings: +{p['temperature_increase']:g} °C, {p['extra_hot_days']} extra hot day(s), "
                 f"{p['new_cooling_centres']} new centre(s) requested, water {p['water_capacity_pct']}%, "
                 f"medical {p['medical_capacity_pct']}%, budget ₹{p['budget_per_day']:,}/day, "
                 f"{p['staff_available']} staff."]
        if c["mean_score_before"] is not None and c["mean_score_after"] is not None:
            diff = c["mean_score_after"] - c["mean_score_before"]
            lines.append(f"The mean risk score moves from {c['mean_score_before']:.1f} to {c['mean_score_after']:.1f} "
                         f"({diff:+.1f}); {c['high_after']} location(s) are High or above, against {c['high_before']} "
                         f"today.")
        moved = [r for r in c["locations"] if r["category_before"] != r["category_after"]]
        if moved:
            lines.append("Category changes: " + "; ".join(f"{r['name']} {r['category_before']} → {r['category_after']}"
                                                          for r in moved[:6]) + ("…" if len(moved) > 6 else "."))
        else:
            lines.append("No location changes category.")
        if result["placed_centres"]:
            lines.append("New cooling centres placed at: " + ", ".join(result["placed_centres"]) + ".")
        if result["limited_by"]:
            lines.append("Fewer centres than requested could be placed: limited by "
                         + " and ".join(result["limited_by"]) + ".")
        lines.append(f"Unmet demand changes from {fmt(c['unmet_before'])} to {fmt(c['unmet_after'])} per day.")
        if c["still_needing_help"]:
            lines.append("Still needing intervention: " + ", ".join(f"{r['name']} ({r['category']})"
                                                                     for r in c["still_needing_help"]) + ".")
        return lines

    def reset(self):
        for name in PARAMS:
            self.form.set(name, LIMITS[name][2])
        self.run()

    def export(self, path=None):
        if self.result is None:
            return None
        path = path or filedialog.asksaveasfilename(parent=self, title="Export scenario", defaultextension=".csv",
                                                    initialfile="noor_scenario.csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return None
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(reports.scenario_report(self.result, reports.data_note(self.svc.status())))
        self.app.set_status(f"Scenario comparison saved to {path}", "ok")
        return path
