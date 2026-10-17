"""Website tests: start the real HTTP server on a background thread and use it like a browser."""
import http.client
import os
import shutil
import tempfile
import threading
import unittest
from urllib.parse import urlencode


class WebTests(unittest.TestCase):
    """Every screen, tab, chart, export and form action over real HTTP."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.old_path = os.environ.get("NOOR_DB_PATH")
        os.environ["NOOR_DB_PATH"] = os.path.join(cls.tmp, "web.db")
        from http.server import ThreadingHTTPServer

        from noor.web import server
        server._setup_done = False
        server.NoorHandler.log_message = lambda *args: None  # keep test output readable
        server.prepare()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.NoorHandler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        if cls.old_path is None:
            os.environ.pop("NOOR_DB_PATH", None)
        else:
            os.environ["NOOR_DB_PATH"] = cls.old_path
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def get(self, path):
        resp, data = self.request("GET", path)
        return resp.status, data, resp

    def post(self, path, fields):
        resp, _ = self.request("POST", path, urlencode(fields),
                               {"Content-Type": "application/x-www-form-urlencoded"})
        return resp.status, resp.getheader("Location", "")

    # ------------------------------------------------------------------ pages
    def test_every_screen_and_tab(self):
        paths = ["/", "/monitoring", "/monitoring?tab=trend", "/monitoring?tab=heatmap&days=14",
                 "/monitoring?tab=comparison", "/monitoring?tab=import", "/risk", "/risk?code=SPR-04",
                 "/alerts", "/alerts?status=all", "/resources", "/resources?tab=add", "/resources?tab=plan",
                 "/resources?tab=plan&strategy=population_first", "/resources?tab=compare", "/resources?tab=saved",
                 "/scenario", "/scenario?temperature_increase=2&new_cooling_centres=5", "/reports",
                 "/reports?tab=charts&chart=3", "/reports?tab=sql&query=hot_locations&param=5", "/reports?tab=export",
                 "/data", "/data?tab=locations"]
        for path in paths:
            with self.subTest(path=path):
                status, body, _ = self.get(path)
                self.assertEqual(status, 200)
                self.assertIn(b"N O O R", body)
                self.assertEqual(body.count(b"<h1>"), 1)
                self.assertIn(b"SYNTHETIC", body)  # header chip names the data kinds in use

    def test_overview_numbers_match_database(self):
        from noor.database import Database
        db = Database()
        try:
            locations = len(db.list_locations())
            active = len(db.list_alerts(status="active"))
        finally:
            db.close()
        _, body, _ = self.get("/")
        text = body.decode("utf-8")
        self.assertIn(f'<div class="number">{locations}</div>', text)
        self.assertIn(f'<span class="badge">{active}</span>', text)

    def test_bad_input_gives_a_message_not_a_crash(self):
        for path in ["/monitoring?start=01/05/2026", "/risk?preview=1&hazard=0.9&exposure=0.2&vulnerability=0.25"
                     "&lack_of_capacity=0.15", "/scenario?temperature_increase=99",
                     "/reports?tab=sql&query=hot_locations&param=abc"]:
            with self.subTest(path=path):
                status, body, _ = self.get(path)
                self.assertEqual(status, 400)
                self.assertIn(b"Please check", body)
        status, _, _ = self.get("/no-such-page")
        self.assertEqual(status, 404)

    # ------------------------------------------------------------------ charts and exports
    def test_charts_are_png(self):
        for path in ["/chart/distribution.png", "/chart/heatmap.png?days=30", "/chart/monthly.png",
                     "/chart/trend.png?code=SPR-01&start=2026-05-01&end=2026-06-04", "/chart/allocation.png",
                     "/chart/scenario.png?temperature_increase=2", "/chart/dimensions.png?code=SPR-01",
                     "/chart/report.png?i=8"]:
            with self.subTest(path=path):
                status, body, resp = self.get(path)
                self.assertEqual(status, 200)
                self.assertEqual(resp.getheader("Content-Type"), "image/png")
                self.assertEqual(body[:8], b"\x89PNG\r\n\x1a\n")

    def test_exports(self):
        for name in ["risk", "vulnerability", "alerts", "plan_risk", "plan_population", "observations", "scenario"]:
            with self.subTest(name=name):
                status, body, _ = self.get(f"/export/{name}.csv")
                self.assertEqual(status, 200)
                self.assertTrue(body.startswith(b"# NOOR report"))
        status, body, _ = self.get("/export/charts.zip")
        self.assertEqual((status, body[:2]), (200, b"PK"))

    # ------------------------------------------------------------------ actions
    def test_alert_status_is_saved(self):
        from noor.database import Database
        db = Database()
        alert_id = db.list_alerts(status="active")[0]["id"]
        db.close()
        status, location = self.post(f"/alerts/{alert_id}/status", {"status": "acknowledged", "back": "/alerts"})
        self.assertEqual(status, 303)
        self.assertIn("msg=", location)
        status, location = self.post(f"/alerts/{alert_id}/status", {"status": "active", "back": "/alerts"})
        self.assertIn("err=", location)  # never backwards

    def test_resource_update_add_and_plan(self):
        status, location = self.post("/resources/CC-01/update", {"status": "limited", "amount": "250",
                                                                 "back": "/resources"})
        self.assertIn("msg=", location)
        status, location = self.post("/resources/add", {"type": "water_point", "location_code": "SPR-02",
                                                        "code": "WP-WEB", "name": "Web kiosk", "amount": "5000",
                                                        "radius_km": "2", "status": "available", "kind": "estimated",
                                                        "back": "/resources?tab=add"})
        self.assertIn("msg=", location)
        status, location = self.post("/resources/add", {"type": "water_point", "location_code": "SPR-02",
                                                        "code": "X", "name": "Bad", "amount": "1", "back": "/"})
        self.assertIn("err=", location)
        status, location = self.post("/plans/save", {"name": "Web plan", "strategy": "risk_first", "back": "/"})
        self.assertIn("msg=", location)
        _, body, _ = self.get("/resources?tab=saved")
        self.assertIn(b"Web plan", body)

    def test_cross_site_post_refused(self):
        resp, _ = self.request("POST", "/actions/recalculate", "back=/",
                               {"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://evil.example"})
        self.assertEqual(resp.status, 403)

    def test_csv_import(self):
        boundary = "noorboundary"
        csv = b"location_code,date,t_max,t_min,humidity\nSPR-03,2026-06-05,42,30,40\nNOPE,2026-06-05,42,30,40\n"
        parts = []
        for name, value in [("source", "Web test upload"), ("kind", "measured"), ("licence", "unknown"),
                            ("action", "import")]:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="t.csv"\r\n'
                     f'Content-Type: text/csv\r\n\r\n'.encode() + csv + b"\r\n")
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        resp, data = self.request("POST", "/monitoring/import", body,
                                  {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        self.assertEqual(resp.status, 200)
        self.assertIn(b"1 valid, 1 rejected", data)
        self.assertIn(b"unknown location code", data)


if __name__ == "__main__":
    unittest.main()
