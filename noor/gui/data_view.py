"""Data Management: the SQLite file, its tables, data sources (provenance) and locations."""
import os
from tkinter import ttk

from .. import settings
from .widgets import Card, DataTable, Form, Page, fmt, wrap_on_resize

KIND_BY_LABEL = {label: key for key, label in settings.DATA_KINDS.items()}
SHARES = [
    ("elderly_share", "Elderly (65+) share"),
    ("children_share", "Children (under 5) share"),
    ("outdoor_worker_share", "Outdoor worker share"),
    ("poor_housing_share", "Poor housing share"),
    ("low_income_share", "Low income share"),
    ("piped_water_share", "Piped water share"),
]


class DataPage(Page):
    title = "Data Management"
    subtitle = "The SQLite database, where every number comes from, and the monitored locations."

    def build(self):
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        self._database_tab()
        self._locations_tab()

    def _tab(self, title):
        frame = ttk.Frame(self.tabs, padding=(0, 12, 0, 0))
        self.tabs.add(frame, text=title)
        return frame

    # ------------------------------------------------------------------ database
    def _database_tab(self):
        tab = self._tab("Database and sources")
        tab.columnconfigure(0, weight=2, uniform="db")
        tab.columnconfigure(1, weight=5, uniform="db")
        tab.rowconfigure(0, weight=1)
        left = Card(tab, "SQLite database")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.db_info = ttk.Label(left.body, text="", style="Card.TLabel", justify="left")
        self.db_info.pack(fill="x", pady=(0, 10))
        wrap_on_resize(self.db_info)
        self.counts = DataTable(left.body, [("table", "Table", 150, "w"), ("rows", "Rows", 80, "e")], height=8,
                                formatters={"rows": fmt})
        self.counts.pack(fill="both", expand=True)
        ttk.Label(left.body, text="Reset to the demo data: close the app and run  python app.py --reset",
                  style="CardMuted.TLabel", wraplength=300, justify="left").pack(fill="x", pady=(10, 0))

        right = Card(tab, "Data sources",
                     "Every location, observation and resource row points to a source. Kind says how far to trust "
                     "it: measured, model-derived, estimated, or synthetic (made up for the demonstration).")
        right.grid(row=0, column=1, sticky="nsew")
        self.sources = DataTable(right.body, [
            ("id", "ID", 40, "e"), ("name", "Name", 230, "w"), ("kind_label", "Kind", 120, "w"),
            ("provider", "Provider", 150, "w"), ("licence", "Licence", 140, "w"),
            ("observations", "Observations", 95, "e"), ("locations", "Locations", 75, "e"),
            ("resources", "Resources", 75, "e"), ("notes", "Notes", 300, "w"),
        ], height=12, formatters={"observations": fmt})
        self.sources.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ locations
    def _locations_tab(self):
        tab = self._tab("Locations")
        tab.columnconfigure(0, weight=3, uniform="loc")
        tab.columnconfigure(1, weight=2, uniform="loc")
        tab.rowconfigure(0, weight=1)
        left = Card(tab, "Monitored locations")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.locations = DataTable(left.body, [
            ("code", "Code", 70, "w"), ("name", "Name", 140, "w"), ("region", "Region", 140, "w"),
            ("population", "Population", 90, "e"), ("area_km2", "Area km²", 75, "e"), ("density", "People/km²", 90, "e"),
            ("kind_label", "Data kind", 110, "w"),
        ], height=16, formatters={"population": fmt, "area_km2": lambda v: fmt(v, 1), "density": fmt})
        self.locations.pack(fill="both", expand=True)

        right = Card(tab, "Add a location",
                     "Shares are fractions from 0 to 1 (0.12 = 12%). Leave a field empty when it is unknown: "
                     "NOOR then treats it as missing, never as zero.")
        right.grid(row=0, column=1, sticky="nsew")
        form = Form(right.body, columns=2)
        form.add("region", "Region", "editcombo", width=16)
        form.add("code", "Code", width=16)
        form.add("name", "Name", width=16)
        form.add("population", "Population", width=16)
        form.add("area_km2", "Area (km²)", width=16)
        form.add("grid_x", "Grid x (km)", width=16)
        form.add("grid_y", "Grid y (km)", width=16)
        for key, label in SHARES:
            form.add(key, label, width=16)
        form.add("kind", "Kind of data", "combo", values=list(settings.DATA_KINDS.values()),
                 default=settings.DATA_KINDS["estimated"], width=16)
        form.add("source", "Source of the numbers", width=16)
        form.pack(fill="x")
        self.form = form
        ttk.Button(right.body, text="Add location", style="Accent.TButton", command=self.add_location).pack(
            anchor="w", pady=(12, 0))

    def add_location(self):
        values = self.form.values()
        values["kind"] = KIND_BY_LABEL.get(values["kind"], values["kind"])
        location = self.svc.add_location(values)  # every field is validated by Location and the service
        self.form.clear(keep=("region", "kind", "source"))
        self.app.data_changed()
        self.app.set_status(f"Added location {location.code} ({location.name}). Risk recalculated; it will be "
                            f"'Insufficient data' until observations are imported for it.", "ok")

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        status = self.svc.status()
        size = os.path.getsize(self.app.db_path) if os.path.exists(self.app.db_path) else 0
        kinds = ", ".join(settings.DATA_KINDS[k] for k in status["data_kinds"]) or "none"
        self.db_info.configure(text=f"File: {self.app.db_path}\nSize: {size / 1024:,.0f} KB\n"
                                    f"Latest observation: {status['latest_observation'] or '—'}\n"
                                    f"Data kinds in use: {kinds}"
                                    + ("\nAll data is synthetic demonstration data." if status["synthetic_only"]
                                       else ""))
        self.counts.set_rows([{"id": t, "table": t, "rows": n} for t, n in status["counts"].items()])
        self.sources.set_rows([{**s, "kind_label": settings.DATA_KINDS[s["kind"]]} for s in status["sources"]])
        rows = []
        for loc in self.db.list_locations():
            density = loc["population"] / loc["area_km2"] if loc["population"] and loc["area_km2"] else None
            rows.append({**loc, "density": density, "kind_label": settings.DATA_KINDS[loc["source_kind"]]})
        self.locations.set_rows(rows)
        regions = sorted({loc["region"] for loc in rows})
        self.form.widget("region").configure(values=regions)
        if not self.form.values()["region"] and regions:
            self.form.set("region", regions[0])
