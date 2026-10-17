"""Climate Monitoring: browse and filter observations, trends, comparisons and CSV import."""
import os
from datetime import date, timedelta
from tkinter import filedialog, ttk

from .. import charts, reports, settings
from ..climate import explorer_table, heat_index, location_comparison, monthly_means, summary_stats
from ..exceptions import ValidationError
from ..importer import REQUIRED, read_upload, validate
from .widgets import (Card, ChartPanel, DataTable, Form, Page, choice_label, code_from_choice, fmt,
                      wrap_on_resize)

ALL = "All locations"
MAX_ROWS_SHOWN = 3000
KIND_CHOICES = list(settings.DATA_KINDS.values())


def check_date(text, label):
    """'' or a YYYY-MM-DD date; anything else is an input error."""
    text = text.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValidationError(f"{label} must be a date written as YYYY-MM-DD") from None


class MonitoringPage(Page):
    title = "Climate Monitoring"
    subtitle = "Daily observations per location: browse, filter, chart, compare and import new readings."

    def build(self):
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        self._observations_tab()
        self._trend_tab()
        self._heatmap_tab()
        self._comparison_tab()
        self._import_tab()

    def _tab(self, title):
        frame = ttk.Frame(self.tabs, padding=(0, 12, 0, 0))
        self.tabs.add(frame, text=title)
        return frame

    def _location_choices(self):
        return [choice_label(l["code"], l["name"]) for l in self.db.list_locations()]

    # ------------------------------------------------------------------ observations
    def _observations_tab(self):
        tab = self._tab("Observations")
        card = Card(tab)
        card.pack(fill="both", expand=True)
        filters = Form(card.body, columns=4)
        self.f_location = filters.add("location", "Location", "combo", width=24)
        self.f_start = filters.add("start", "From (YYYY-MM-DD)", width=13)
        self.f_end = filters.add("end", "To", width=13)
        self.f_search = filters.add("search", "Search name or code", width=16)
        filters.pack(fill="x")
        self.obs_form = filters
        actions = ttk.Frame(card.body, style="Card.TFrame")
        actions.pack(fill="x", pady=(8, 8))
        self.f_forecast = ttk.Checkbutton(actions, text="Include forecast days")
        self.f_forecast.state(["!alternate"])
        self.f_forecast.pack(side="left")
        ttk.Button(actions, text="Export shown rows (CSV)…", command=self.export_observations).pack(side="right")
        ttk.Button(actions, text="Reset", command=self.reset_filters).pack(side="right", padx=8)
        ttk.Button(actions, text="Apply filters", style="Accent.TButton", command=self.load_observations).pack(side="right")
        filters.widget("search").bind("<Return>", lambda e: self.load_observations())
        self.obs_summary = ttk.Label(card.body, text="", style="CardMuted.TLabel")
        self.obs_summary.pack(fill="x", pady=(0, 6))
        self.obs_table = DataTable(card.body, [
            ("location", "Code", 70, "w"), ("name", "Location", 140, "w"), ("date", "Date", 95, "w"),
            ("type", "Type", 80, "w"), ("t_max", "Max °C", 70, "e"), ("t_min", "Min °C", 70, "e"),
            ("humidity", "Humidity %", 85, "e"), ("heat_index", "Heat index °C", 95, "e"),
            ("source_kind", "Data kind", 110, "w"),
        ], height=14, formatters={k: (lambda v: fmt(v, 1)) for k in ("t_max", "t_min", "humidity", "heat_index")},
            empty_text="No observations match these filters.")
        self.obs_table.pack(fill="both", expand=True)

    def reset_filters(self):
        frame = self.db.observations_frame()
        self.f_location.set(ALL)
        self.f_start.set(frame["date"].min() if not frame.empty else "")
        self.f_end.set(frame["date"].max() if not frame.empty else "")
        self.f_search.set("")
        self.f_forecast.state(["!selected"])
        self.load_observations()

    def filtered_observations(self):
        """Observations matching the filter fields (a pandas DataFrame)."""
        start = check_date(self.f_start.get(), "From")
        end = check_date(self.f_end.get(), "To")
        if start and end and start > end:
            raise ValidationError("'From' must be on or before 'To'")
        choice = self.f_location.get()
        codes = None if choice in ("", ALL) else [code_from_choice(choice)]
        frame = self.db.observations_frame(codes, start, end)
        if not self.f_forecast.instate(["selected"]):
            frame = frame[frame["is_forecast"] == 0]
        text = self.f_search.get().strip().lower()
        if text:
            frame = frame[frame["name"].str.lower().str.contains(text, regex=False)
                          | frame["location"].str.lower().str.contains(text, regex=False)]
        return frame

    def load_observations(self):
        frame = self.filtered_observations()
        frame = frame.assign(heat_index=[heat_index(t, h) for t, h in zip(frame["t_max"], frame["humidity"])],
                             type=["Forecast" if f else "Observed" for f in frame["is_forecast"]])
        stats = summary_stats(frame["t_max"])
        note = (f"{len(frame):,} rows. Max temperature: mean {fmt(stats['mean'], 1)} °C, "
                f"lowest {fmt(stats['min'], 1)} °C, highest {fmt(stats['max'], 1)} °C, "
                f"standard deviation {fmt(stats['std'], 2)} °C (NumPy, missing values ignored).")
        if len(frame) > MAX_ROWS_SHOWN:
            note += f" Showing the first {MAX_ROWS_SHOWN:,}; narrow the filters or export to see all."
        self.obs_summary.configure(text=note)
        records = frame.head(MAX_ROWS_SHOWN).to_dict("records")
        for r in records:  # pandas uses NaN for empty cells; the table shows a dash for None
            for key in ("t_max", "t_min", "humidity"):
                if r[key] != r[key]:
                    r[key] = None
            r["id"] = (r["location"], r["date"], r["is_forecast"])
        self.obs_table.set_rows(records, tag_fn=lambda r: "muted" if r["is_forecast"] else None)
        self.shown_frame = frame

    def export_observations(self, path=None):
        frame = self.filtered_observations()
        path = path or filedialog.asksaveasfilename(parent=self, title="Export observations", defaultextension=".csv",
                                                    initialfile="noor_observations.csv",
                                                    filetypes=[("CSV files", "*.csv")])
        if not path:
            return None
        text = reports.observations_report(frame, reports.data_note(self.svc.status()))
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        self.app.set_status(f"Saved {len(frame):,} observation rows to {path}", "ok")
        return path

    # ------------------------------------------------------------------ trend
    def _trend_tab(self):
        tab = self._tab("Daily trend")
        card = Card(tab, "Daily temperatures for one location",
                    "Max and min temperature and the heat index (from temperature and humidity). "
                    "Ticks along the bottom mark days with no reading.")
        card.pack(fill="both", expand=True)
        form = Form(card.body, columns=3)
        self.t_location = form.add("location", "Location", "combo", width=26)
        self.t_start = form.add("start", "From (YYYY-MM-DD)", width=13)
        self.t_end = form.add("end", "To", width=13)
        form.pack(fill="x")
        self.trend_form = form
        row = ttk.Frame(card.body, style="Card.TFrame")
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Show trend", style="Accent.TButton", command=self.show_trend).pack(side="left")
        self.trend_stats = ttk.Label(row, text="", style="CardMuted.TLabel")
        self.trend_stats.pack(side="left", padx=12)
        form.widget("location").bind("<<ComboboxSelected>>", lambda e: self._new_trend_location())
        self.trend_chart = ChartPanel(card.body, height=320)
        self.trend_chart.pack(fill="both", expand=True)

    def _new_trend_location(self):
        """A different location was picked: show its latest 45 days."""
        self.t_start.set("")
        self.t_end.set("")
        self.show_trend()

    def show_trend(self):
        code = code_from_choice(self.t_location.get())
        if not code:
            raise ValidationError("Choose a location")
        frame = self.db.observations_frame([code])
        observed = frame[frame["is_forecast"] == 0]
        if observed.empty:
            self.trend_chart.show(charts.empty_chart("No observations for this location"))
            self.trend_stats.configure(text="")
            return
        end = check_date(self.t_end.get(), "To") or observed["date"].max()
        start = check_date(self.t_start.get(), "From") or (date.fromisoformat(end) - timedelta(days=44)).isoformat()
        if start > end:
            raise ValidationError("'From' must be on or before 'To'")
        if (date.fromisoformat(end) - date.fromisoformat(start)).days > 400:
            raise ValidationError("Choose a period of at most 400 days")
        self.t_start.set(start)
        self.t_end.set(end)
        table = explorer_table(observed, start, end)
        stats = summary_stats(table["t_max"])
        self.trend_stats.configure(text=f"{stats['count']} days with a reading, {int(table['missing'].sum())} missing; "
                                        f"mean max {fmt(stats['mean'], 1)} °C, highest {fmt(stats['max'], 1)} °C")
        self.trend_chart.show(charts.trend_chart(table, f"{code}: daily temperatures"))

    # ------------------------------------------------------------------ heatmap
    def _heatmap_tab(self):
        tab = self._tab("All-location heatmap")
        card = Card(tab, "Daily maximum temperature, every location",
                    "Each row is a location and each column a day. Grey cells are days with no reading.")
        card.pack(fill="both", expand=True)
        row = ttk.Frame(card.body, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 8))
        form = Form(row)
        self.h_days = form.add("days", "Days to show", "spin", values=(7, 90, 1), default=30, width=6)
        form.pack(side="left")
        ttk.Button(row, text="Draw heatmap", style="Accent.TButton", command=self.show_heatmap).pack(side="left",
                                                                                                    padx=12)
        self.heatmap = ChartPanel(card.body, height=360)
        self.heatmap.pack(fill="both", expand=True)

    def show_heatmap(self):
        try:
            days = int(self.h_days.get())
        except ValueError:
            raise ValidationError("Days to show must be a whole number") from None
        if not 7 <= days <= 90:
            raise ValidationError("Days to show must be between 7 and 90")
        self.heatmap.show(charts.temperature_heatmap(self.db.observations_frame(), days))

    # ------------------------------------------------------------------ comparison
    def _comparison_tab(self):
        tab = self._tab("Location comparison")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        card = Card(tab, "Per-location summary of observed days", "Pandas groupby over all observed rows.")
        card.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.compare_table = DataTable(card.body, [
            ("location", "Code", 70, "w"), ("name", "Location", 140, "w"), ("mean_tmax", "Mean max °C", 90, "e"),
            ("max_tmax", "Highest °C", 85, "e"), ("mean_tmin", "Mean min °C", 90, "e"),
            ("mean_humidity", "Mean humidity %", 110, "e"), ("days_observed", "Days observed", 100, "e"),
            ("days_missing", "Days missing", 95, "e"), ("first_day", "First day", 95, "w"),
            ("last_day", "Last day", 95, "w"),
        ], height=7, formatters={k: (lambda v: fmt(v, 1)) for k in ("mean_tmax", "max_tmax", "mean_tmin",
                                                                       "mean_humidity")})
        self.compare_table.pack(fill="both", expand=True)
        chart_card = Card(tab, "Monthly means")
        chart_card.grid(row=1, column=0, sticky="nsew")
        self.monthly = ChartPanel(chart_card.body, height=220)
        self.monthly.pack(fill="both", expand=True)

    def load_comparison(self):
        frame = self.db.observations_frame()
        table = location_comparison(frame)
        rows = table.to_dict("records")
        for r in rows:
            r["first_day"] = str(r["first_day"])[:10]
            r["last_day"] = str(r["last_day"])[:10]
            r["code"] = r["location"]
        self.compare_table.set_rows(rows)
        self.monthly.show(charts.monthly_chart(monthly_means(frame)))

    # ------------------------------------------------------------------ import
    def _import_tab(self):
        tab = self._tab("Import CSV")
        tab.columnconfigure(0, weight=4, uniform="imp")
        tab.columnconfigure(1, weight=5, uniform="imp")
        tab.rowconfigure(0, weight=1)
        left = Card(tab, "Import climate observations",
                    "Required columns: " + ", ".join(REQUIRED) + " (optional: is_forecast 0/1). Dates as "
                    "YYYY-MM-DD, temperatures in °C, humidity in %. Bad rows are listed and skipped; good rows "
                    "are saved. A row for a location and day that already exists replaces it.")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        form = Form(left.body)
        self.i_path = form.add("path", "CSV file", width=30)
        form.pack(fill="x")
        ttk.Button(left.body, text="Browse…", command=self.browse).pack(anchor="e", pady=(4, 8))
        form2 = Form(left.body)
        self.i_source = form2.add("source", "Data source name", width=30,
                                  hint="Where the numbers come from, e.g. 'Ward weather station log'")
        self.i_kind = form2.add("kind", "Kind of data", "combo", values=KIND_CHOICES, default="Measured", width=28)
        self.i_licence = form2.add("licence", "Licence or terms", width=30, hint="Write 'unknown' if you do not know")
        form2.pack(fill="x")
        buttons = ttk.Frame(left.body, style="Card.TFrame")
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Import valid rows", style="Accent.TButton", command=self.import_file).pack(side="left")
        ttk.Button(buttons, text="Check file only", command=self.check_file).pack(side="left", padx=8)
        ttk.Button(buttons, text="Save empty template…", command=self.save_template).pack(side="right")

        right = Card(tab, "Validation result")
        right.grid(row=0, column=1, sticky="nsew")
        self.import_result = ttk.Label(right.body, text="Choose a file and press Check file only or Import.",
                                       style="Card.TLabel", justify="left")
        self.import_result.pack(fill="x", pady=(0, 8))
        wrap_on_resize(self.import_result)
        self.error_table = DataTable(right.body, [("line", "Line", 60, "e"), ("column", "Column", 110, "w"),
                                                  ("message", "Problem", 300, "w")], height=12,
                                     empty_text="No problems found.")
        self.error_table.pack(fill="both", expand=True)

    def browse(self):
        path = filedialog.askopenfilename(parent=self, title="Choose a CSV file",
                                          filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.i_path.set(path)
            if not self.i_source.get():
                self.i_source.set(os.path.splitext(os.path.basename(path))[0][:80])

    def _read_file(self):
        path = self.i_path.get().strip()
        if not path:
            raise ValidationError("Choose a CSV file first")
        if not os.path.isfile(path):
            raise ValidationError(f"File not found: {path}")
        with open(path, "rb") as f:
            return f.read()

    def _show_report(self, rows, accepted, errors, extra=""):
        rejected = rows - accepted
        text = f"{rows:,} row(s) read: {accepted:,} valid, {rejected:,} rejected."
        if extra:
            text += " " + extra
        self.import_result.configure(text=text)
        for i, e in enumerate(errors):
            e["id"] = i
        self.error_table.set_rows(errors, keep_selection=False)

    def check_file(self):
        """Validate without saving anything (same checks as the import)."""
        df = read_upload(self._read_file())
        known = {l["code"] for l in self.db.list_locations()}
        clean, errors = validate(df, known)
        self._show_report(len(df), len(clean), errors[:500], "Nothing was saved (check only).")
        self.app.set_status("File checked; nothing saved.", "ok")

    def import_file(self):
        data = self._read_file()
        kind = {label: key for key, label in settings.DATA_KINDS.items()}.get(self.i_kind.get())
        source, licence = self.i_source.get(), self.i_licence.get()
        self.app.run_task("Importing observations",
                          lambda svc: svc.import_csv(data, source, kind, licence), self._imported)

    def _imported(self, report):
        extra = (f"Saved under the data source '{report['source']}' and risk recalculated."
                 if report.get("source") else "Nothing was saved because no row was valid.")
        errors = report["errors"]
        if report["more_errors"]:
            extra += f" ({report['more_errors']} more problems not listed.)"
        self._show_report(report["rows"], report["accepted"], errors, extra)
        if report.get("source"):
            self.app.data_changed()
            self.app.set_status(f"Imported {report['accepted']:,} rows.", "ok")
        else:
            self.app.set_status("No valid rows: nothing imported.", "warn")

    def save_template(self, path=None):
        path = path or filedialog.asksaveasfilename(parent=self, title="Save CSV template", defaultextension=".csv",
                                                    initialfile="noor_import_template.csv",
                                                    filetypes=[("CSV files", "*.csv")])
        if path:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(",".join(REQUIRED + ["is_forecast"]) + "\n")
            self.app.set_status(f"Template saved to {path}", "ok")

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        choices = self._location_choices()
        self.obs_form.widget("location").configure(values=[ALL] + choices)
        self.trend_form.widget("location").configure(values=choices)
        if not self.f_location.get():
            self.reset_filters()  # first visit: whole date range, all locations
        else:
            self.load_observations()
        if not self.t_location.get() and choices:
            latest = self.db.latest_assessments()  # start the trend on the highest-risk location
            code = latest[0]["code"] if latest else code_from_choice(choices[0])
            self.t_location.set(next(c for c in choices if code_from_choice(c) == code))
        if self.t_location.get():
            self.show_trend()
        self.show_heatmap()
        self.load_comparison()
