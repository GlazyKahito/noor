"""Tests for the SQLite layer: constraints, relationships, seed reproducibility and provenance."""
import threading
import unittest

from noor.database import Database
from noor.exceptions import ConflictError, NotFoundError
from noor.queries import QUERIES, run_query
from noor.seed import build_weather
from noor.service import NoorService


class DatabaseTests(unittest.TestCase):
    """Each test gets a fresh in-memory database with the demo data."""

    def setUp(self):
        self.db = Database(":memory:")
        self.svc = NoorService(self.db)
        self.svc.setup()

    def tearDown(self):
        self.db.close()

    def test_eight_tables(self):
        names = {r["name"] for r in self.db.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table' "
                                                      "AND name NOT LIKE 'sqlite_%'")}
        self.assertEqual(len(names), 8)

    def test_foreign_keys_enforced(self):
        with self.assertRaises(ConflictError):
            self.db.add_observations([(9999, "2026-06-01", 0, 40.0, 28.0, 30.0, 1)])

    def test_check_constraints(self):
        loc_id = self.db.list_locations()[0]["id"]
        with self.assertRaises(ConflictError):
            self.db.add_observations([(loc_id, "2026-01-01", 0, 40.0, 28.0, 150.0, 1)])  # humidity 150 %
        with self.assertRaises(ConflictError):
            self.db.execute("UPDATE resources SET status = 'broken' WHERE code = 'CC-01'")

    def test_unique_codes(self):
        with self.assertRaises(ConflictError):
            self.db.execute("INSERT INTO resources (code, name, type, location_id, amount, radius_km, source_id) "
                            "VALUES ('CC-01', 'dup', 'cooling_centre', 1, 10, 1, 1)")

    def test_parameters_store_text_literally(self):
        evil = "x'); DROP TABLE locations; --"
        self.db.add_source(evil, "estimated", "test", "test")
        self.assertIsNotNone(self.db.fetch_one("SELECT id FROM data_sources WHERE name = ?", (evil,)))
        self.assertEqual(self.db.table_counts()["locations"], 16)

    def test_alert_status_moves_forward_only(self):
        alert = self.db.list_alerts(status="active")[0]
        self.db.set_alert_status(alert["id"], "acknowledged")
        with self.assertRaises(ConflictError):
            self.db.set_alert_status(alert["id"], "acknowledged")
        self.db.set_alert_status(alert["id"], "resolved")
        with self.assertRaises(ConflictError):
            self.db.set_alert_status(alert["id"], "acknowledged")
        with self.assertRaises(NotFoundError):
            self.db.set_alert_status(999999, "resolved")

    def test_alerts_not_duplicated(self):
        before = self.db.table_counts()["alerts"]
        new, _found = self.svc.run_alerts()
        self.assertEqual(new, 0)
        self.assertEqual(self.db.table_counts()["alerts"], before)

    def test_delete_resource_cascades_to_allocations(self):
        rows = self.db.fetch_one("SELECT COUNT(*) AS n FROM allocations a JOIN resources r ON r.id = a.resource_id "
                                 "WHERE r.code = 'CC-01'")["n"]
        self.assertGreater(rows, 0)
        self.db.delete_resource("CC-01")
        left = self.db.fetch_one("SELECT COUNT(*) AS n FROM allocations WHERE resource_id NOT IN (SELECT id FROM resources)")
        self.assertEqual(left["n"], 0)

    def test_update_resource_changes_risk(self):
        before = {a["code"]: a["score"] for a in self.db.latest_assessments()}
        self.svc.update_resource("CC-02", "offline", 500)
        after = {a["code"]: a["score"] for a in self.db.latest_assessments()}
        self.assertGreater(after["SPR-06"], before["SPR-06"])  # its own cooling centre went offline

    def test_unknown_location(self):
        with self.assertRaises(NotFoundError):
            self.db.get_location("NOPE")

    def test_every_named_query_runs(self):
        for name in QUERIES:
            title, rows = run_query(self.db, name)
            self.assertTrue(title)
            self.assertIsInstance(rows, list)

    def test_having_query(self):
        _title, rows = run_query(self.db, "hot_locations", (10,))
        self.assertTrue(all(r["hot_days"] > 10 for r in rows))

    def test_everything_is_labelled_synthetic(self):
        kinds = {r["source_kind"] for r in self.db.list_locations()} | {r["source_kind"] for r in self.db.list_resources()}
        self.assertEqual(kinds, {"synthetic"})
        self.assertTrue(self.svc.status()["synthetic_only"])

    def test_import_is_labelled_with_its_kind(self):
        csv = b"location_code,date,t_max,t_min,humidity\nSPR-01,2026-06-04,43.2,30.1,22\n"
        report = self.svc.import_csv(csv, "Ward logger", "measured", "CC BY 4.0")
        self.assertEqual(report["accepted"], 1)
        row = self.db.observations_frame(["SPR-01"], "2026-06-04", "2026-06-04").iloc[0]
        self.assertEqual(row["source_kind"], "measured")
        self.assertFalse(self.svc.status()["synthetic_only"])

    def test_seed_is_reproducible(self):
        self.assertTrue(build_weather().equals(build_weather()))

    def test_demo_gaps_exist(self):
        _title, rows = run_query(self.db, "missing_days")
        self.assertIn("SPR-04", {r["code"] for r in rows})
        self.assertIsNone(self.db.get_location("SPR-15")["population"])

    def test_close_and_destructor(self):
        db = Database(":memory:")
        db.close()
        db.close()  # second close is harmless
        del db

    def test_write_lock_is_shared(self):
        self.assertIsInstance(Database.write_lock, type(threading.Lock()))
        self.assertIs(Database(":memory:").write_lock, Database.write_lock)


if __name__ == "__main__":
    unittest.main()
