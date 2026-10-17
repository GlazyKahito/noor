"""Reports and Analytics: summary statistics, charts, the SQL examples and CSV / PNG exports.

Every figure and table here is generated from the database when the screen loads.
"""
import os
import tkinter as tk
from datetime import date
from tkinter import filedialog, ttk

from .. import charts, reports
from ..climate import location_comparison, monthly_means, summary_stats
from ..exceptions import ValidationError
from ..queries import QUERIES, run_query
from . import styles
from .widgets import Card, ChartPanel, DataTable, Form, Page, fmt, tile_row

CHARTS = [
    ("Risk score by location", lambda page: charts.risk_bars(page.db.latest_assessments())),
    ("Locations per risk category", lambda page: charts.risk_distribution(page.db.latest_assessments())),
    ("How risk scores are spread", lambda page: charts.score_histogram(page.db.latest_assessments())),
    ("Schematic ward grid: risk score", lambda page: charts.risk_map(page.db.latest_assessments(), "score")),
    ("Schematic ward grid: hazard", lambda page: charts.risk_map(page.svc.assess(), "hazard")),
    ("Schematic ward grid: vulnerability", lambda page: charts.risk_map(page.svc.assess(), "vulnerability")),
    ("Daily max temperature heatmap (30 days)", lambda page: charts.temperature_heatmap(page.db.observations_frame())),
    ("Monthly climate means", lambda page: charts.monthly_chart(monthly_means(page.db.observations_frame()))),
    ("Allocation: demand vs capacity (risk-first)", lambda page: charts.allocation_chart(page.svc.plan("risk_first"))),
]


class ReportsPage(Page):
    title = "Reports & Analytics"
    subtitle = "Summary statistics, charts, the project's SQL queries and downloadable reports."

    def build(self):
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        self._summary_tab()
        self._charts_tab()
        self._sql_tab()
        self._export_tab()

    def _tab(self, title):
        frame = ttk.Frame(self.tabs, padding=(0, 12, 0, 0))
        self.tabs.add(frame, text=title)
        return frame

    # ------------------------------------------------------------------ summary
    def _summary_tab(self):
        tab = self._tab("Summary")
        self.tiles = tile_row(tab, [
            ("obs", "Observed days stored", False), ("mean", "Mean max temperature", False),
            ("hottest", "Hottest reading", True), ("alerts", "Alerts on record", False),
            ("resources", "Resource capacity / day", False),
        ])
        grid = ttk.Frame(tab)
        grid.pack(fill="both", expand=True)
        for c in (0, 1):
            grid.columnconfigure(c, weight=1, uniform="sum")
        for r in (0, 1):
            grid.rowconfigure(r, weight=1, uniform="sumr")
        self.summary_tables = {}
        specs = [
            ("region_summary", 0, 0, [("region", "Region", 160, "w"), ("locations", "Locations", 80, "e"),
                                      ("mean_score", "Mean score", 85, "e"), ("max_score", "Max score", 80, "e"),
                                      ("high_or_above", "High or above", 100, "e")]),
            ("alerts_by_severity", 0, 1, [("severity", "Severity", 120, "w"), ("status", "Status", 120, "w"),
                                          ("alerts", "Alerts", 80, "e")]),
            ("resources_by_type", 1, 0, [("type", "Type", 130, "w"), ("status", "Status", 80, "w"),
                                         ("resources", "Count", 60, "e"), ("total_amount", "Total amount", 100, "e"),
                                         ("staff", "Staff", 60, "e")]),
        ]
        for key, row, col, columns in specs:
            card = Card(grid, QUERIES[key]["title"])
            card.grid(row=row, column=col, sticky="nsew", padx=(0, 12) if col == 0 else 0, pady=(0, 12))
            table = DataTable(card.body, columns, height=5, formatters={"total_amount": fmt})
            table.pack(fill="both", expand=True)
            self.summary_tables[key] = table
        card = Card(grid, "Location-wise climate comparison")
        card.grid(row=1, column=1, sticky="nsew", pady=(0, 12))
        self.comparison = DataTable(card.body, [
            ("location", "Code", 70, "w"), ("name", "Location", 130, "w"), ("mean_tmax", "Mean max °C", 90, "e"),
            ("max_tmax", "Highest °C", 80, "e"), ("mean_humidity", "Humidity %", 85, "e"),
            ("days_missing", "Missing days", 90, "e"),
        ], height=5, formatters={k: (lambda v: fmt(v, 1)) for k in ("mean_tmax", "max_tmax", "mean_humidity")})
        self.comparison.pack(fill="both", expand=True)

    def load_summary(self):
        frame = self.db.observations_frame()
        observed = frame[frame["is_forecast"] == 0]
        stats = summary_stats(observed["t_max"])
        self.tiles["obs"].set(fmt(len(observed)), f"{observed['location'].nunique()} locations")
        self.tiles["mean"].set(fmt(stats["mean"], 1, "°C"), f"standard deviation {fmt(stats['std'], 1)} °C")
        if stats["count"]:
            hottest = observed.loc[observed["t_max"].idxmax()]
            self.tiles["hottest"].set(fmt(stats["max"], 1, "°C"), f"{hottest['name']}, {hottest['date']}")
        else:
            self.tiles["hottest"].set("—", "no readings")
        counts = self.db.table_counts()
        open_alerts = self.db.fetch_one("SELECT COUNT(*) AS n FROM alerts WHERE status <> 'resolved'")["n"]
        self.tiles["alerts"].set(str(counts["alerts"]), f"{open_alerts} not yet resolved")
        capacity = sum(r["capacity"] for r in self.svc.plan("risk_first")["resources"])
        self.tiles["resources"].set(fmt(capacity), f"{counts['resources']} resources, after status")
        for key, table in self.summary_tables.items():
            _title, rows = run_query(self.db, key)
            table.set_rows([{**r, "id": i} for i, r in enumerate(rows)], keep_selection=False)
        rows = location_comparison(frame).to_dict("records")
        self.comparison.set_rows([{**r, "code": r["location"]} for r in rows])

    # ------------------------------------------------------------------ charts
    def _charts_tab(self):
        tab = self._tab("Charts")
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        menu = Card(tab, "Choose a chart")
        menu.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        self.chart_list = tk.Listbox(menu.body, height=len(CHARTS), activestyle="none", exportselection=False,
                                     bg=styles.CARD, fg=styles.INK, selectbackground=styles.WINE,
                                     selectforeground="white", relief="flat", highlightthickness=0, bd=0,
                                     font=styles.FONTS["body"], width=40)
        for title, _make in CHARTS:
            self.chart_list.insert("end", "  " + title)
        self.chart_list.pack(fill="y", expand=True)
        self.chart_list.bind("<<ListboxSelect>>", lambda e: self.draw_chart())
        ttk.Button(menu.body, text="Save chart as PNG…", command=self.save_chart).pack(fill="x", pady=(10, 0))
        holder = Card(tab)
        holder.grid(row=0, column=1, sticky="nsew")
        self.chart = ChartPanel(holder.body, height=420)
        self.chart.pack(fill="both", expand=True)

    def draw_chart(self, index=None):
        if index is None:
            chosen = self.chart_list.curselection()
            index = chosen[0] if chosen else 0
        self.chart_list.selection_clear(0, "end")
        self.chart_list.selection_set(index)
        self.chart.show(CHARTS[index][1](self))

    def save_chart(self, path=None):
        if self.chart.figure is None:
            return None
        title = CHARTS[(self.chart_list.curselection() or (0,))[0]][0]
        name = "noor_" + "".join(ch if ch.isalnum() else "_" for ch in title.lower()).strip("_") + ".png"
        path = path or filedialog.asksaveasfilename(parent=self, title="Save chart", defaultextension=".png",
                                                    initialfile=name, filetypes=[("PNG image", "*.png")])
        if path:
            charts.save_png(self.chart.figure, path)
            self.app.set_status(f"Chart saved to {path}", "ok")
        return path

    # ------------------------------------------------------------------ SQL
    def _sql_tab(self):
        tab = self._tab("SQL queries")
        top = Card(tab, "SQL examples from noor/queries.py",
                   "Each query runs on the live database with ? parameters (JOIN, GROUP BY, HAVING, sub-queries).")
        top.pack(fill="x")
        row = ttk.Frame(top.body, style="Card.TFrame")
        row.pack(fill="x")
        form = Form(row, columns=2)
        self.q_choice = form.add("query", "Query", "combo", values=[q["title"] for q in QUERIES.values()],
                                 default=QUERIES["region_summary"]["title"], width=56)
        self.q_param = form.add("param", "Parameter (?)", width=8)
        form.pack(side="left")
        form.widget("query").bind("<<ComboboxSelected>>", lambda e: self.show_query(run=True))
        ttk.Button(row, text="Run query", style="Accent.TButton", command=self.run_query).pack(side="right", anchor="s")
        self.q_sql = styles.text_widget(top.body, height=9, mono=True)
        self.q_sql.pack(fill="x", pady=(10, 0))
        result = Card(tab, "Result")
        result.pack(fill="both", expand=True, pady=(12, 0))
        self.q_count = ttk.Label(result.body, text="", style="CardMuted.TLabel")
        self.q_count.pack(fill="x")
        self.q_holder = ttk.Frame(result.body, style="Card.TFrame")
        self.q_holder.pack(fill="both", expand=True)
        self.q_table = None

    def _query_key(self):
        return next(k for k, q in QUERIES.items() if q["title"] == self.q_choice.get())

    def show_query(self, run=False):
        query = QUERIES[self._query_key()]
        self.q_sql.configure(state="normal")
        self.q_sql.delete("1.0", "end")
        self.q_sql.insert("1.0", query["sql"].strip())
        self.q_sql.configure(state="disabled")
        self.q_param.set(", ".join(str(p) for p in query["params"]))
        if run:
            self.run_query()

    def run_query(self):
        key = self._query_key()
        params = None
        if QUERIES[key]["params"]:
            try:
                params = (int(self.q_param.get()),)
            except ValueError:
                raise ValidationError("The parameter must be a whole number") from None
        _title, rows = run_query(self.db, key, params)
        if self.q_table is not None:
            self.q_table.destroy()
        columns = [(c, c, 110, "w") for c in (rows[0].keys() if rows else ["result"])]
        self.q_table = DataTable(self.q_holder, columns, height=12, empty_text="The query returned no rows.")
        self.q_table.pack(fill="both", expand=True)
        self.q_table.set_rows([{**r, "id": i} for i, r in enumerate(rows)])
        self.q_count.configure(text=f"{len(rows)} row(s).")

    # ------------------------------------------------------------------ export
    def _export_tab(self):
        tab = self._tab("Export")
        card = Card(tab, "Download reports",
                    "Each CSV starts with lines beginning with # that say when it was made, from which data, "
                    "by which method, and its limitations.")
        card.pack(fill="x")
        exports = [
            ("risk", "Regional heat-risk summary", "Latest score, category, dimensions and reasons per location."),
            ("vulnerability", "Vulnerability assessment", "Indicator shares next to the vulnerability dimension."),
            ("alerts", "Alert report", "Every alert with severity, trigger, period, status and actions."),
            ("plan_risk", "Allocation plan (risk-first)", "Demand and served per location and resource type."),
            ("plan_population", "Allocation plan (population-first)", "The baseline plan for comparison."),
            ("observations", "Climate observations", "Every stored daily row."),
        ]
        for i, (key, title, note) in enumerate(exports):
            ttk.Label(card.body, text=title, style="CardBold.TLabel").grid(row=i, column=0, sticky="w", pady=5)
            ttk.Label(card.body, text=note, style="CardMuted.TLabel").grid(row=i, column=1, sticky="w", padx=16)
            ttk.Button(card.body, text="Save CSV…", command=lambda k=key: self.export(k)).grid(row=i, column=2,
                                                                                             sticky="e")
        card.body.columnconfigure(1, weight=1)
        charts_card = Card(tab, "Charts", "Saves every chart on the Charts tab as a PNG file into one folder.")
        charts_card.pack(fill="x", pady=(12, 0))
        ttk.Button(charts_card.body, text="Save all charts…", command=self.export_charts).pack(anchor="w")

    def report_text(self, key):
        """CSV text for one report (all generated from the live database)."""
        note = reports.data_note(self.svc.status())
        if key == "risk":
            return reports.risk_report(self.db.latest_assessments(), note)
        if key == "vulnerability":
            return reports.vulnerability_report(self.db.list_locations(), self.db.latest_assessments(), note)
        if key == "alerts":
            return reports.alerts_report(self.db.list_alerts(), note)
        if key == "plan_risk":
            return reports.allocation_report(self.svc.plan("risk_first"), note)
        if key == "plan_population":
            return reports.allocation_report(self.svc.plan("population_first"), note)
        if key == "observations":
            return reports.observations_report(self.db.observations_frame(), note)
        raise KeyError(key)

    def export(self, key, path=None):
        path = path or filedialog.asksaveasfilename(parent=self, title="Save report", defaultextension=".csv",
                                                    initialfile=f"noor_{key}_{date.today():%Y%m%d}.csv",
                                                    filetypes=[("CSV files", "*.csv")])
        if not path:
            return None
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(self.report_text(key))
        self.app.set_status(f"Report saved to {path}", "ok")
        return path

    def export_charts(self, folder=None):
        folder = folder or filedialog.askdirectory(parent=self, title="Choose a folder for the charts")
        if not folder:
            return []
        saved = []
        for title, make in CHARTS:
            name = "".join(ch if ch.isalnum() else "_" for ch in title.lower()).strip("_") + ".png"
            path = os.path.join(folder, name)
            charts.save_png(make(self), path)
            saved.append(path)
        self.app.set_status(f"Saved {len(saved)} charts to {folder}", "ok")
        return saved

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        self.load_summary()
        self.draw_chart((self.chart_list.curselection() or (0,))[0])
        self.show_query(run=True)
