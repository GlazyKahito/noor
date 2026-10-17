"""Alerts: warnings raised by the rule engine (noor/alerts.py), with acknowledge / resolve.

Status changes are saved in SQLite through Database.set_alert_status(), which only allows
active -> acknowledged -> resolved. Nothing is sent anywhere: these are on-screen records.
"""
from tkinter import filedialog, ttk

from .. import reports
from ..alerts import DISCLAIMER
from .widgets import (split_panes, RULE_LABELS, Card, DataTable, Form, Page, bullet_list, caps, fmt, tile_row, when,
                      wrap_on_resize)

STATUSES = ["Active", "Acknowledged", "Resolved", "All"]
SEVERITIES = ["All", "emergency", "warning", "advisory", "info"]


class AlertsPage(Page):
    title = "Alerts"
    subtitle = "Early warnings from fixed, documented threshold rules. " + DISCLAIMER

    def build(self):
        self.tiles = tile_row(self, [
            ("emergency", "Emergency (active)", True),
            ("warning", "Warning (active)", True),
            ("advisory", "Advisory (active)", False),
            ("acknowledged", "Acknowledged", False),
            ("resolved", "Resolved", False),
        ])
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)
        split_panes(panes, 0.66)
        left = Card(panes)
        right = Card(panes, "Alert details")
        panes.add(left, weight=3)
        panes.add(right, weight=2)

        bar = ttk.Frame(left.body, style="Card.TFrame")
        bar.pack(fill="x", pady=(0, 8))
        form = Form(bar, columns=2)
        self.f_status = form.add("status", "Status", "combo", values=STATUSES, default="Active", width=14)
        self.f_severity = form.add("severity", "Severity", "combo", values=SEVERITIES, default="All", width=12)
        form.pack(side="left")
        for key in ("status", "severity"):
            form.widget(key).bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Button(bar, text="Export CSV…", command=self.export).pack(side="right", anchor="s")
        ttk.Button(bar, text="Run warning rules", style="Accent.TButton",
                   command=self.run_rules).pack(side="right", anchor="s", padx=8)
        self.count = ttk.Label(left.body, text="", style="CardMuted.TLabel")
        self.count.pack(fill="x", pady=(0, 4))
        self.table = DataTable(left.body, [
            ("id", "ID", 45, "e"), ("severity", "Severity", 85, "w"), ("name", "Location", 130, "w"),
            ("rule_label", "Rule", 100, "w"), ("issued_at", "Created", 135, "w"), ("status", "Status", 95, "w"),
            ("message", "Reason", 320, "w"),
        ], height=14, formatters={"issued_at": when}, on_select=self.show_alert,
            empty_text="No alerts match these filters.")
        self.table.pack(fill="both", expand=True)

        body = right.body
        self.d_title = ttk.Label(body, text="Select an alert", style="CardBold.TLabel", justify="left")
        self.d_title.pack(fill="x")
        wrap_on_resize(self.d_title)
        self.d_meta = ttk.Label(body, text="", style="CardMuted.TLabel", justify="left")
        self.d_meta.pack(fill="x", pady=(4, 0))
        wrap_on_resize(self.d_meta)
        caps(body, "Trigger")
        self.d_trigger = ttk.Label(body, text="", style="Card.TLabel", justify="left")
        self.d_trigger.pack(fill="x")
        wrap_on_resize(self.d_trigger)
        caps(body, "Recommended action")
        self.d_actions = ttk.Frame(body, style="Card.TFrame")
        self.d_actions.pack(fill="x")
        caps(body, "Confidence")
        self.d_confidence = ttk.Label(body, text="", style="CardMuted.TLabel", justify="left")
        self.d_confidence.pack(fill="x")
        wrap_on_resize(self.d_confidence)
        buttons = ttk.Frame(body, style="Card.TFrame")
        buttons.pack(fill="x", pady=(14, 0))
        self.ack = ttk.Button(buttons, text="Acknowledge", command=lambda: self.change_status("acknowledged"))
        self.ack.pack(side="left")
        self.resolve = ttk.Button(buttons, text="Mark resolved", style="Accent.TButton",
                                  command=lambda: self.change_status("resolved"))
        self.resolve.pack(side="left", padx=8)
        self.ack.state(["disabled"])
        self.resolve.state(["disabled"])

    # ------------------------------------------------------------------ data
    def refresh(self):
        counts = {r["k"]: r["n"] for r in self.db.fetch_all(
            "SELECT CASE WHEN status = 'active' THEN severity ELSE status END AS k, COUNT(*) AS n "
            "FROM alerts GROUP BY k")}
        for key, tile in self.tiles.items():
            tile.set(str(counts.get(key, 0)))
        status = self.f_status.get().lower()
        severity = self.f_severity.get()
        alerts = self.db.list_alerts(None if status == "all" else status, None if severity == "All" else severity)
        for a in alerts:
            a["rule_label"] = RULE_LABELS.get(a["rule"], a["rule"])
        self.table.set_rows(alerts, tag_fn=lambda a: a["severity"] if a["status"] == "active" else "muted")
        self.count.configure(text=f"{len(alerts)} alert(s) shown. Most severe first.")
        self.show_alert(self.table.selected())

    def show_alert(self, alert):
        if not alert:
            self.d_title.configure(text="Select an alert to see its details.")
            for label in (self.d_meta, self.d_trigger, self.d_confidence):
                label.configure(text="")
            bullet_list(self.d_actions, [])
            self.ack.state(["disabled"])
            self.resolve.state(["disabled"])
            return
        self.d_title.configure(text=alert["message"])
        self.d_meta.configure(text=f"#{alert['id']} · {alert['severity'].upper()} · {alert['name']} ({alert['code']}) · "
                                   f"{alert['status']} · created {when(alert['issued_at'])}")
        self.d_trigger.configure(text=f"{RULE_LABELS.get(alert['rule'], alert['rule'])}: value "
                                      f"{fmt(alert['trigger_value'], 1)} against threshold {fmt(alert['threshold'], 1)}; "
                                      f"period {alert['period']}.")
        bullet_list(self.d_actions, [a for a in alert["actions"].split(" | ") if a], wraplength=380)
        self.d_confidence.configure(text=alert["confidence"])
        self.ack.state(["!disabled"] if alert["status"] == "active" else ["disabled"])
        self.resolve.state(["!disabled"] if alert["status"] != "resolved" else ["disabled"])

    # ------------------------------------------------------------------ actions
    def change_status(self, new_status):
        alert = self.table.selected()
        if not alert:
            return
        self.db.set_alert_status(alert["id"], new_status)  # ConflictError for a backwards move
        self.app.data_changed()
        self.table.select_where(lambda a: a["id"] == alert["id"])
        self.app.set_status(f"Alert #{alert['id']} marked {new_status}.", "ok")

    def run_rules(self):
        self.app.run_task("Running the warning rules", lambda svc: svc.run_alerts(), self._ran)

    def _ran(self, result):
        new, found = result
        self.app.data_changed()
        self.app.set_status(f"Rules fired {found} time(s); {new} new alert(s). Alerts already on record "
                            f"for the same rule, location and period are not repeated.", "ok")

    def export(self, path=None):
        path = path or filedialog.asksaveasfilename(parent=self, title="Export alerts", defaultextension=".csv",
                                                    initialfile="noor_alerts.csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return None
        text = reports.alerts_report(self.db.list_alerts(), reports.data_note(self.svc.status()))
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        self.app.set_status(f"Alert report saved to {path}", "ok")
        return path
