"""Tests for the Tkinter desktop app: every screen opens and the buttons do real, saved work.

The window is created withdrawn (never shown). Message boxes are replaced by a recorder so
nothing waits for a click. Skipped automatically when Tk cannot start (no display).
"""
import os
import shutil
import tempfile
import time
import tkinter as tk
import unittest
from tkinter import messagebox

from noor.exceptions import ConflictError, ValidationError

try:
    _probe = tk.Tk()
    _probe.destroy()
    TK_OK = True
except tk.TclError:
    TK_OK = False


@unittest.skipUnless(TK_OK, "Tk cannot open a window here")
class GuiTests(unittest.TestCase):
    """One app window shared by all tests (building it takes a few seconds)."""

    @classmethod
    def setUpClass(cls):
        from noor.gui.main_window import NoorApp
        cls.tmp = tempfile.mkdtemp()
        cls.boxes = []
        cls._saved = {name: getattr(messagebox, name) for name in ("showwarning", "showerror", "showinfo",
                                                                    "askyesno")}
        messagebox.showwarning = lambda title, msg, **k: cls.boxes.append(("warning", msg))
        messagebox.showerror = lambda title, msg, **k: cls.boxes.append(("error", msg))
        messagebox.showinfo = lambda title, msg, **k: cls.boxes.append(("info", msg))
        messagebox.askyesno = lambda *a, **k: True
        cls.app = NoorApp(db_path=os.path.join(cls.tmp, "gui.db"), splash=False)
        cls.app.withdraw()
        cls.wait()

    @classmethod
    def tearDownClass(cls):
        cls.app.close()
        for name, func in cls._saved.items():
            setattr(messagebox, name, func)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def wait(cls, timeout=60):
        """Process events until start-up and any background task have finished."""
        end = time.time() + timeout
        while (cls.app.busy or not cls.app.ready) and time.time() < end:
            cls.app.update()
            time.sleep(0.02)
        cls.app.update()

    def setUp(self):
        self.boxes.clear()

    def tearDown(self):
        self.assertEqual(self.app.errors, [], "unexpected errors were shown")

    # ------------------------------------------------------------------ start-up and navigation
    def test_database_created_and_seeded(self):
        self.assertTrue(os.path.exists(self.app.db_path))
        demo = [l for l in self.app.db.list_locations() if l["code"].startswith("SPR-")]
        self.assertEqual(len(demo), 16)  # other tests may add their own locations

    def test_every_screen_opens(self):
        from noor.gui.main_window import PAGES
        for key, label, _cls in PAGES:
            with self.subTest(screen=key):
                page = self.app.page(key)
                self.wait()
                self.assertEqual(self.app.current, key)
                self.assertEqual(page.title, label.replace("Overview", page.title))
        self.assertEqual(self.boxes, [])

    def test_dashboard_numbers_come_from_the_database(self):
        page = self.app.page("overview")
        page.refresh()
        db = self.app.db
        self.assertEqual(page.tiles["locations"].value.cget("text"), str(len(db.list_locations())))
        high = sum(1 for a in db.latest_assessments() if a["category"] in ("High", "Severe", "Extreme"))
        self.assertEqual(page.tiles["high"].value.cget("text"), str(high))
        self.assertEqual(page.tiles["alerts"].value.cget("text"), str(len(db.list_alerts(status="active"))))
        self.assertEqual(page.table.count(), len(db.latest_assessments()))

    # ------------------------------------------------------------------ monitoring
    def test_observation_filters(self):
        page = self.app.page("monitoring")
        page.f_location.set("SPR-01 — Old Market")
        page.f_start.set("2026-05-01")
        page.f_end.set("2026-05-31")
        page.load_observations()
        rows = list(page.obs_table.rows.values())
        self.assertTrue(rows)
        self.assertTrue(all(r["location"] == "SPR-01" and "2026-05-01" <= r["date"] <= "2026-05-31" for r in rows))
        page.f_start.set("01/05/2026")
        with self.assertRaises(ValidationError):
            page.load_observations()
        page.reset_filters()

    def test_csv_check_and_import(self):
        page = self.app.page("monitoring")
        path = os.path.join(self.tmp, "upload.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("location_code,date,t_max,t_min,humidity\n"
                    "SPR-01,2026-06-05,41.5,29.0,35\n"
                    "NOPE,2026-06-05,41.5,29.0,35\n")
        page.i_path.set(path)
        page.check_file()
        self.assertEqual(page.error_table.count(), 1)
        before = self.app.db.table_counts()["observations"]
        page.i_source.set("Test upload")
        page.i_kind.set("Measured")
        page.i_licence.set("unknown")
        page.import_file()
        self.wait()
        self.assertEqual(self.app.db.table_counts()["observations"], before + 1)
        self.assertIn("1 valid", page.import_result.cget("text"))

    def test_observation_export(self):
        page = self.app.page("monitoring")
        page.reset_filters()
        path = page.export_observations(os.path.join(self.tmp, "obs.csv"))
        with open(path, encoding="utf-8") as f:
            self.assertTrue(f.readline().startswith("# NOOR report: Climate observations"))

    # ------------------------------------------------------------------ risk
    def test_risk_detail_and_weights_preview(self):
        page = self.app.page("risk")
        page.show_location("SPR-04")
        self.assertIn("SPR-04", page.d_name.cget("text"))
        self.assertTrue(page.d_reasons.winfo_children())
        page.weight_form.set("hazard", "0.9")
        with self.assertRaises(ValidationError):  # weights now add up to 1.5
            page.preview()
        for key, value in {"hazard": "0.7", "exposure": "0.1", "vulnerability": "0.1", "lack_of_capacity": "0.1"}.items():
            page.weight_form.set(key, value)
        page.preview()
        self.assertIn("PREVIEW", page.mode.cget("text"))
        page.back_to_saved()
        self.assertIn("Saved assessment", page.mode.cget("text"))

    # ------------------------------------------------------------------ alerts
    def test_acknowledge_and_resolve_are_saved(self):
        page = self.app.page("alerts")
        page.f_status.set("Active")
        page.refresh()
        alert = next(iter(page.table.rows.values()))
        page.table.select_where(lambda a: a["id"] == alert["id"])
        page.change_status("acknowledged")
        status = self.app.db.fetch_one("SELECT status FROM alerts WHERE id = ?", (alert["id"],))["status"]
        self.assertEqual(status, "acknowledged")
        page.f_status.set("All")
        page.refresh()
        page.table.select_where(lambda a: a["id"] == alert["id"])
        page.change_status("resolved")
        self.assertTrue(page.ack.instate(["disabled"]))
        with self.assertRaises(ConflictError):  # never backwards
            page.change_status("acknowledged")

    # ------------------------------------------------------------------ resources
    def test_resource_edit_move_add_delete(self):
        page = self.app.page("resources")
        page.f_type.set("All types")
        page.f_status.set("All")
        page.load_inventory()
        page.inventory.select_where(lambda r: r["code"] == "CC-01")
        page.e_status.set("limited")
        page.e_amount.set("280")
        page.save_resource()
        row = next(r for r in self.app.db.list_resources() if r["code"] == "CC-01")
        self.assertEqual((row["status"], row["amount"]), ("limited", 280))

        page.inventory.select_where(lambda r: r["code"] == "CC-01")
        page.e_location.set("SPR-02 — Fort Ward")
        page.move_resource()
        row = next(r for r in self.app.db.list_resources() if r["code"] == "CC-01")
        self.assertEqual(row["location_code"], "SPR-02")

        form = page.add_form
        form.set("code", "CC-TEST")
        form.set("name", "Test hall")
        form.set("amount", "150")
        page.add_resource()
        self.assertIn("CC-TEST", {r["code"] for r in self.app.db.list_resources()})
        form.set("code", "X")  # too short
        form.set("name", "Bad")
        form.set("amount", "10")
        with self.assertRaises(ValidationError):
            page.add_resource()

        page.load_inventory()
        page.inventory.select_where(lambda r: r["code"] == "CC-TEST")
        page.delete_resource(confirm=False)
        self.assertNotIn("CC-TEST", {r["code"] for r in self.app.db.list_resources()})

    def test_plan_save_and_export(self):
        page = self.app.page("resources")
        page.p_name.set("GUI test plan")
        page.save_plan()
        self.assertIn("GUI test plan", {p["plan_name"] for p in self.app.db.list_plans()})
        path = page.export_plan(os.path.join(self.tmp, "plan.csv"))
        with open(path, encoding="utf-8") as f:
            self.assertIn("Allocation plan", f.readline())

    # ------------------------------------------------------------------ scenario
    def test_scenario_runs_real_calculation(self):
        page = self.app.page("scenario")
        self.wait()
        page.form.set("temperature_increase", "3")
        page.form.set("new_cooling_centres", "4")
        page.run()
        self.wait()
        comparison = page.result["comparison"]
        self.assertEqual(page.result["params"]["temperature_increase"], 3.0)
        self.assertGreaterEqual(comparison["mean_score_after"], comparison["mean_score_before"])
        self.assertEqual(page.loc_table.count(), len(self.app.db.list_locations()))
        page.form.set("temperature_increase", "99")
        page.run()
        self.wait()
        self.assertTrue(self.boxes and "temperature_increase" in self.boxes[-1][1])  # shown, not crashed
        page.form.set("temperature_increase", "0")

    # ------------------------------------------------------------------ reports and data
    def test_reports_exports_and_queries(self):
        page = self.app.page("reports")
        for key in ("risk", "vulnerability", "alerts", "plan_risk", "plan_population", "observations"):
            path = page.export(key, os.path.join(self.tmp, key + ".csv"))
            with open(path, encoding="utf-8") as f:
                self.assertTrue(f.readline().startswith("# NOOR report"), key)
        saved = page.export_charts(os.path.join(self.tmp, "charts_out") if os.makedirs(
            os.path.join(self.tmp, "charts_out"), exist_ok=True) is None else None)
        self.assertEqual(len(saved), 9)
        page.q_choice.set("Locations with more than ? days at or above 40 °C")
        page.q_param.set("abc")
        with self.assertRaises(ValidationError):
            page.run_query()
        page.q_param.set("5")
        page.run_query()
        self.assertGreater(page.q_table.count(), 0)

    def test_add_location(self):
        page = self.app.page("data")
        form = page.form
        form.set("code", "TST-01")
        form.set("name", "Test Ward")
        form.set("population", "50000")
        form.set("area_km2", "4")
        form.set("source", "Typed in for a test")
        page.add_location()
        self.assertIn("TST-01", {l["code"] for l in self.app.db.list_locations()})
        form.set("code", "TST-02")
        form.set("name", "Bad share")
        form.set("elderly_share", "1.5")
        with self.assertRaises(ValidationError):
            page.add_location()


if __name__ == "__main__":
    unittest.main()
