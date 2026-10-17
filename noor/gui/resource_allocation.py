"""Emergency Resource Allocation: inventory (edit, reassign, add, delete) and allocation plans.

The plan comes from AllocationPlanner in noor/allocation.py: a greedy rule (highest-priority
locations first, nearest resources first). It is a transparent baseline, not an optimiser.
"""
from tkinter import filedialog, messagebox, ttk

from .. import charts, reports, settings
from ..allocation import STRATEGIES
from ..models import RESOURCE_CLASSES, make_resource
from ..summaries import STRATEGY_LABELS, TYPE_LABELS, plan_location_rows
from .widgets import (split_panes, Card, ChartPanel, DataTable, Form, Page, choice_label, code_from_choice, fmt, pct,
                      tile_row, wrap_on_resize)

TYPE_BY_LABEL = {label: name for name, label in TYPE_LABELS.items()}
STRATEGY_BY_LABEL = {label: key for key, label in STRATEGY_LABELS.items()}
KIND_BY_LABEL = {label: key for key, label in settings.DATA_KINDS.items()}
STATUSES = list(settings.STATUS_FACTOR)


class ResourcesPage(Page):
    title = "Resource Allocation"
    subtitle = ("Cooling centres, water points, medical units and teams: what exists, where, and how the greedy "
                "planner shares them out.")

    def build(self):
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        self._inventory_tab()
        self._add_tab()
        self._plan_tab()
        self._compare_tab()
        self._saved_tab()
        self.plan_result = None

    def _tab(self, title):
        frame = ttk.Frame(self.tabs, padding=(0, 12, 0, 0))
        self.tabs.add(frame, text=title)
        return frame

    # ------------------------------------------------------------------ inventory
    def _inventory_tab(self):
        tab = self._tab("Inventory")
        panes = ttk.PanedWindow(tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        split_panes(panes, 0.74)
        left = Card(panes)
        right = Card(panes, "Selected resource")
        panes.add(left, weight=3)
        panes.add(right, weight=1)

        bar = ttk.Frame(left.body, style="Card.TFrame")
        bar.pack(fill="x", pady=(0, 8))
        form = Form(bar, columns=2)
        self.f_type = form.add("type", "Type", "combo", values=["All types"] + list(TYPE_LABELS.values()),
                               default="All types", width=24)
        self.f_status = form.add("status", "Status", "combo", values=["All"] + STATUSES, default="All", width=12)
        form.pack(side="left")
        for key in ("type", "status"):
            form.widget(key).bind("<<ComboboxSelected>>", lambda e: self.load_inventory())
        self.inv_count = ttk.Label(left.body, text="", style="CardMuted.TLabel")
        self.inv_count.pack(fill="x", pady=(0, 4))
        self.inventory = DataTable(left.body, [
            ("code", "Code", 75, "w"), ("name", "Name", 170, "w"), ("type_label", "Type", 150, "w"),
            ("location", "Location", 150, "w"), ("amount_text", "Amount", 120, "e"),
            ("capacity", "Serves / day", 90, "e"), ("status", "Status", 75, "w"), ("radius_km", "Radius km", 75, "e"),
            ("staff", "Staff", 55, "e"), ("daily_cost", "Cost ₹/day", 85, "e"),
        ], height=15, formatters={"capacity": fmt, "daily_cost": fmt, "radius_km": lambda v: fmt(v, 1)},
            on_select=self.show_resource)
        self.inventory.pack(fill="both", expand=True)

        body = right.body
        self.r_desc = ttk.Label(body, text="Select a resource in the table.", style="Card.TLabel", justify="left")
        self.r_desc.pack(fill="x", pady=(0, 8))
        wrap_on_resize(self.r_desc)
        edit = Form(body)
        self.e_status = edit.add("status", "Status", "combo", values=STATUSES, width=16)
        self.e_amount = edit.add("amount", "Amount", width=16)
        edit.pack(fill="x")
        self.e_unit = ttk.Label(body, text="", style="CardMuted.TLabel")
        self.e_unit.pack(anchor="w")
        ttk.Button(body, text="Save status and amount", style="Accent.TButton",
                   command=self.save_resource).pack(fill="x", pady=(8, 14))
        move = Form(body)
        self.e_location = move.add("location", "Reassign to location", "combo", width=22)
        move.pack(fill="x")
        self.move_form = move
        ttk.Button(body, text="Move resource here", command=self.move_resource).pack(fill="x", pady=(8, 14))
        ttk.Button(body, text="Delete resource…", command=self.delete_resource).pack(fill="x")
        ttk.Label(body, text="Every change is saved in SQLite and the risk scores are recalculated, because "
                             "response capacity is part of the score.", style="CardMuted.TLabel",
                  wraplength=230, justify="left").pack(fill="x", pady=(14, 0))

    def load_inventory(self):
        rtype = TYPE_BY_LABEL.get(self.f_type.get())
        status = self.f_status.get()
        rows = []
        for r in self.db.list_resources():
            if rtype and r["type"] != rtype or status not in ("", "All") and r["status"] != status:
                continue
            obj = make_resource(r["type"], code=r["code"], name=r["name"], location_code=r["location_code"],
                                amount=r["amount"], status=r["status"], radius_km=r["radius_km"])
            rows.append({**r, "type_label": TYPE_LABELS[r["type"]], "location": f"{r['location_code']} {r['location_name']}",
                         "amount_text": f"{fmt(r['amount'])} {obj.unit}", "capacity": obj.capacity(),
                         "describe": obj.describe(), "unit": obj.unit})
        self.inventory.set_rows(rows, tag_fn=lambda r: {"offline": "Extreme", "limited": "High"}.get(r["status"]))
        total = len(self.db.list_resources())
        self.inv_count.configure(text=f"{len(rows)} of {total} resources shown. 'Serves / day' is the capacity "
                                      f"after status (limited = half, offline = none).")
        self.show_resource(self.inventory.selected())

    def show_resource(self, row):
        if not row:
            self.r_desc.configure(text="Select a resource in the table.")
            return
        self.r_desc.configure(text=f"{row['code']}: {row['describe']}. Based at {row['location']}, "
                                   f"serves locations within {row['radius_km']:.1f} km.")
        self.e_status.set(row["status"])
        self.e_amount.set(f"{row['amount']:g}")
        self.e_unit.configure(text=f"Amount is in {row['unit']}.")
        self.e_location.set(next((c for c in self.move_form.widget("location").cget("values")
                                  if code_from_choice(c) == row["location_code"]), ""))

    def _selected(self):
        row = self.inventory.selected()
        if not row:
            messagebox.showinfo("No resource selected", "Select a resource in the table first.", parent=self)
        return row

    def save_resource(self):
        row = self._selected()
        if row:
            self.svc.update_resource(row["code"], self.e_status.get(), self.e_amount.get())
            self._changed(f"Saved {row['code']}: {self.e_status.get()}, amount {self.e_amount.get()}. "
                          f"Risk recalculated.")

    def move_resource(self):
        row = self._selected()
        if row:
            code = code_from_choice(self.e_location.get())
            self.svc.move_resource(row["code"], code)
            self._changed(f"Moved {row['code']} to {code}. Risk recalculated.")

    def delete_resource(self, confirm=True):
        row = self._selected()
        if row and (not confirm or messagebox.askyesno(
                "Delete resource", f"Delete {row['code']} ({row['name']})?\nSaved plan rows that use it are "
                                   f"deleted too. This cannot be undone.", parent=self)):
            self.svc.delete_resource(row["code"])
            self._changed(f"Deleted {row['code']}. Risk recalculated.")

    def _changed(self, message):
        self.plan_result = None
        self.app.data_changed()
        self.app.set_status(message, "ok")

    # ------------------------------------------------------------------ add
    def _add_tab(self):
        tab = self._tab("Add resource")
        card = Card(tab, "Add a resource to the inventory",
                    "Units: " + "; ".join(f"{cls.label}: {cls.unit}" for cls in RESOURCE_CLASSES.values()) + ".")
        card.pack(fill="x", anchor="n")
        form = Form(card.body, columns=2)
        form.add("type", "Type", "combo", values=list(TYPE_LABELS.values()), default=TYPE_LABELS["cooling_centre"],
                 width=26)
        form.add("location_code", "Located at", "combo", width=26)
        form.add("code", "Code (2-20 characters)", width=26)
        form.add("name", "Name", width=26)
        form.add("amount", "Amount (in the unit above)", width=26)
        form.add("radius_km", "Service radius (km)", default="3", width=26)
        form.add("staff", "Staff", default="0", width=26)
        form.add("daily_cost", "Daily cost (₹)", default="0", width=26)
        form.add("status", "Status", "combo", values=STATUSES, default="available", width=26)
        form.add("kind", "Kind of data", "combo", values=list(settings.DATA_KINDS.values()),
                 default=settings.DATA_KINDS["estimated"], width=26)
        form.pack(fill="x")
        self.add_form = form
        ttk.Button(card.body, text="Add resource", style="Accent.TButton", command=self.add_resource).pack(
            anchor="w", pady=(12, 0))

    def add_resource(self):
        values = self.add_form.values()
        values["type"] = TYPE_BY_LABEL.get(values["type"], values["type"])
        values["location_code"] = code_from_choice(values["location_code"])
        values["kind"] = KIND_BY_LABEL.get(values["kind"], values["kind"])
        resource = self.svc.add_resource(values)  # validates every field
        self.add_form.clear(keep=("type", "location_code", "radius_km", "status", "kind"))
        self.add_form.set("staff", "0")
        self.add_form.set("daily_cost", "0")
        self._changed(f"Added {resource.code}: {resource.describe()}. Risk recalculated.")

    # ------------------------------------------------------------------ plan
    def _plan_tab(self):
        tab = self._tab("Allocation plan")
        top = Card(tab, "Run the allocation planner", reports.METHODS["allocation"]
                   + " Demand rates are planning assumptions in settings.py, not measured needs.")
        top.pack(fill="x")
        bar = ttk.Frame(top.body, style="Card.TFrame")
        bar.pack(fill="x")
        form = Form(bar, columns=2)
        self.p_strategy = form.add("strategy", "Strategy", "combo", values=list(STRATEGY_LABELS.values()),
                                   default=STRATEGY_LABELS["risk_first"], width=34)
        self.p_name = form.add("name", "Save as (plan name)", width=26)
        form.pack(side="left")
        ttk.Button(bar, text="Export CSV…", command=self.export_plan).pack(side="right", anchor="s")
        ttk.Button(bar, text="Save plan", command=self.save_plan).pack(side="right", anchor="s", padx=8)
        ttk.Button(bar, text="Run plan", style="Accent.TButton", command=self.run_plan).pack(side="right", anchor="s")

        self.plan_tiles = tile_row(tab, [("demand", "Estimated demand / day", False),
                                         ("served", "Can be served / day", True),
                                         ("unmet", "Unmet / day", True),
                                         ("weighted", "Risk-weighted coverage", False),
                                         ("gaps", "High-risk locations with gaps", False)])
        self.plan_tiles["demand"].master.pack_configure(pady=(12, 12))
        lower = ttk.Frame(tab)
        lower.pack(fill="both", expand=True)
        lower.columnconfigure(0, weight=1, uniform="plan")
        lower.columnconfigure(1, weight=1, uniform="plan")
        lower.rowconfigure(0, weight=1)
        types_card = Card(lower, "By resource type")
        types_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.type_table = DataTable(types_card.body, [
            ("label", "Type", 160, "w"), ("demand", "Demand", 75, "e"), ("served", "Served", 75, "e"),
            ("unmet", "Unmet", 75, "e"), ("coverage", "Coverage", 75, "e"), ("utilisation", "Use of capacity", 105, "e"),
        ], height=5, formatters={"demand": fmt, "served": fmt, "unmet": fmt, "coverage": pct, "utilisation": pct})
        self.type_table.pack(fill="x")
        self.plan_chart = ChartPanel(types_card.body, height=200)
        self.plan_chart.pack(fill="both", expand=True, pady=(8, 0))
        loc_card = Card(lower, "By location (served / demand per day)")
        loc_card.grid(row=0, column=1, sticky="nsew")
        cols = [("code", "Code", 65, "w"), ("name", "Location", 120, "w"), ("category", "Category", 85, "w")]
        cols += [(t, TYPE_LABELS[t].split()[0], 85, "e") for t in settings.DEMAND_RATES]
        self.loc_table = DataTable(loc_card.body, cols, height=12)
        self.loc_table.pack(fill="both", expand=True)

    def run_plan(self):
        strategy = STRATEGY_BY_LABEL.get(self.p_strategy.get(), "risk_first")
        self.plan_result = self.svc.plan(strategy)
        self.show_plan()

    def show_plan(self):
        plan = self.plan_result
        self.plan_tiles["demand"].set(fmt(plan["total_demand"]), "people (or visits) per day")
        coverage = plan["total_served"] / plan["total_demand"] if plan["total_demand"] else None
        self.plan_tiles["served"].set(fmt(plan["total_served"]), f"{pct(coverage)} of demand")
        self.plan_tiles["unmet"].set(fmt(plan["total_unmet"]), "not reached by any resource")
        self.plan_tiles["weighted"].set(pct(plan["risk_weighted_coverage"]), "coverage weighted by risk score")
        gaps = plan["high_risk_with_gaps"]
        self.plan_tiles["gaps"].set(str(len(gaps)), ", ".join(gaps) if gaps else "none")
        self.type_table.set_rows([{"id": t, "label": TYPE_LABELS[t], **v} for t, v in plan["by_type"].items()])
        self.plan_chart.show(charts.allocation_chart(plan))
        self.loc_table.set_rows(plan_location_rows(plan), tag_fn=lambda r: r["category"])

    def save_plan(self):
        strategy = STRATEGY_BY_LABEL.get(self.p_strategy.get(), "risk_first")
        name = self.p_name.get()
        self.plan_result = self.svc.save_plan(name, strategy)  # validates the name
        self.show_plan()
        self.p_name.set("")
        self.app.data_changed()
        self.app.set_status(f"Plan '{name.strip()}' saved ({STRATEGY_LABELS[strategy]}).", "ok")

    def export_plan(self, path=None):
        if self.plan_result is None:
            self.run_plan()
        plan = self.plan_result
        path = path or filedialog.asksaveasfilename(parent=self, title="Export allocation plan", defaultextension=".csv",
                                                    initialfile=f"noor_plan_{plan['strategy']}.csv",
                                                    filetypes=[("CSV files", "*.csv")])
        if not path:
            return None
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(reports.allocation_report(plan, reports.data_note(self.svc.status())))
        self.app.set_status(f"Plan saved to {path}", "ok")
        return path

    # ------------------------------------------------------------------ compare
    def _compare_tab(self):
        tab = self._tab("Compare strategies")
        card = Card(tab, "Population-first (A) vs risk-first (B) on today's data",
                    "Same resources, same greedy loop; only the order in which locations are served changes.")
        card.pack(fill="both", expand=True)
        self.cmp_summary = ttk.Label(card.body, text="", style="Card.TLabel", justify="left")
        self.cmp_summary.pack(fill="x", pady=(0, 10))
        wrap_on_resize(self.cmp_summary)
        self.cmp_table = DataTable(card.body, [
            ("label", "Type", 180, "w"), ("served_a", "Served (A)", 100, "e"), ("served_b", "Served (B)", 100, "e"),
            ("difference", "B − A", 90, "e"), ("unmet_a", "Unmet (A)", 100, "e"), ("unmet_b", "Unmet (B)", 100, "e"),
        ], height=6, formatters={k: fmt for k in ("served_a", "served_b", "difference", "unmet_a", "unmet_b")})
        self.cmp_table.pack(fill="x")

    def load_compare(self):
        result = self.svc.compare()
        self.cmp_table.set_rows([{"id": r["type"], "label": TYPE_LABELS[r["type"]], **r} for r in result["rows"]])
        self.cmp_summary.configure(
            text=f"Risk-weighted coverage: A {pct(result['risk_weighted_a'])}, B {pct(result['risk_weighted_b'])}. "
                 f"High-risk locations still with gaps: A {', '.join(result['high_gaps_a']) or 'none'}; "
                 f"B {', '.join(result['high_gaps_b']) or 'none'}.")

    # ------------------------------------------------------------------ saved
    def _saved_tab(self):
        tab = self._tab("Saved plans")
        card = Card(tab, "Plans saved in the allocations table")
        card.pack(fill="both", expand=True)
        self.saved_table = DataTable(card.body, [
            ("plan_name", "Plan", 220, "w"), ("strategy", "Strategy", 140, "w"), ("created_at", "Saved (UTC)", 170, "w"),
            ("rows", "Assignments", 100, "e"), ("people_per_day", "People / day", 110, "e"),
        ], height=12, formatters={"people_per_day": fmt}, empty_text="No plans saved yet.")
        self.saved_table.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        choices = [choice_label(l["code"], l["name"]) for l in self.db.list_locations()]
        self.move_form.widget("location").configure(values=choices)
        self.add_form.widget("location_code").configure(values=choices)
        if not self.add_form.values()["location_code"] and choices:
            self.add_form.set("location_code", choices[0])
        self.load_inventory()
        self.run_plan()
        self.load_compare()
        self.saved_table.set_rows([{**p, "id": (p["plan_name"], p["strategy"])} for p in self.db.list_plans()])
