"""End-to-end tests: start the real HTTP server on a background thread and call it with http.client."""
import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from urllib.parse import urlencode


class ServerTests(unittest.TestCase):
    """Pages, API, forms, uploads, charts and exports over real HTTP."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ["NOOR_DB_PATH"] = os.path.join(cls.tmp, "test.db")
        from noor.web import server
        server._setup_done = False
        server.NoorHandler.log_message = lambda *args: None  # keep test output readable
        server.prepare()
        cls.httpd = server.NoorHTTPServer(("127.0.0.1", 0), server.NoorHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    def setUp(self):
        self.conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)

    def tearDown(self):
        self.conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        os.environ.pop("NOOR_DB_PATH", None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ helpers
    def request(self, path, data=None, headers=None, method=None):
        """Return (status, headers, body bytes) using one keep-alive connection, like a browser."""
        method = method or ("POST" if data is not None else "GET")
        for attempt in range(2):  # reconnect once if the server closed the connection
            try:
                self.conn.request(method, path, body=data, headers=headers or {})
                resp = self.conn.getresponse()
                body = resp.read()
                return resp.status, resp.headers, body
            except (ConnectionError, http.client.HTTPException):
                self.conn.close()
                self.conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
                if attempt == 1:
                    raise

    def get_json(self, path):
        status, _h, body = self.request(path)
        return status, json.loads(body)

    def post_json(self, path, payload):
        status, _h, body = self.request(path, json.dumps(payload).encode(), {"Content-Type": "application/json"})
        return status, json.loads(body)

    def post_form(self, path, fields, origin=None):
        data = urlencode(fields).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if origin:
            headers["Origin"] = origin
        return self.request(path, data, headers)

    # ------------------------------------------------------------------ pages
    def test_a_demo_banner_on_fresh_data(self):
        """Runs first (alphabetical order): with only seed data, every page says it is synthetic."""
        for path in ("/", "/dashboard", "/risk", "/alerts", "/plans", "/scenarios"):
            _status, _h, body = self.request(path)
            self.assertIn(b"Demonstration mode", body, path)

    def test_every_page_renders(self):
        for path in ("/", "/dashboard", "/explorer", "/explorer?location=SPR-04&start=2026-05-01&end=2026-06-04",
                     "/risk", "/risk?category=Severe&sort=name", "/risk/SPR-01", "/risk/SPR-15", "/map?layer=exposure",
                     "/alerts", "/alerts?status=active", "/resources", "/plans", "/plans?strategy=population_first",
                     "/scenarios", "/scenarios?run=1&temperature_increase=2", "/reports", "/reports?query=provenance",
                     "/data", "/methodology"):
            status, headers, body = self.request(path)
            self.assertEqual(status, 200, path)
            self.assertIn("text/html", headers["Content-Type"])
            self.assertIn(b"NOOR", body)

    def test_unknown_page_is_friendly_404(self):
        status, _h, body = self.request("/does-not-exist")
        self.assertEqual(status, 404)
        self.assertNotIn(b"Traceback", body)

    def test_bad_weights_show_message_not_crash(self):
        status, _h, body = self.request("/risk?w_hazard=0.9&w_exposure=0.9&w_vulnerability=0.9&w_lack_of_capacity=0.9")
        self.assertEqual(status, 400)
        self.assertIn(b"add up to 1.0", body)

    def test_security_headers(self):
        _s, headers, _b = self.request("/dashboard")
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_static_path_traversal_blocked(self):
        status, _h, _b = self.request("/static/..%2f..%2fsettings.py")
        self.assertEqual(status, 404)

    # ------------------------------------------------------------------ API
    def test_api_health_and_shape(self):
        status, body = self.get_json("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["status"], "ok")

    def test_api_reads(self):
        for path in ("/api/status", "/api/config", "/api/locations", "/api/locations/SPR-01", "/api/risk",
                     "/api/risk/SPR-05", "/api/alerts?status=active", "/api/resources", "/api/plans",
                     "/api/plans/compare", "/api/observations?location=SPR-02&start=2026-06-01",
                     "/api/scenario?temperature_increase=1", "/api/queries/region_summary"):
            status, body = self.get_json(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body["ok"], path)

    def test_api_errors(self):
        status, body = self.get_json("/api/locations/NOPE")
        self.assertEqual((status, body["ok"]), (404, False))
        status, body = self.get_json("/api/alerts?severity=apocalyptic")
        self.assertEqual(status, 400)
        status, body = self.get_json("/api/scenario?temperature_increase=50")
        self.assertEqual(status, 400)
        self.assertIn("between", body["error"]["message"])
        status, body = self.get_json("/api/nothing-here")
        self.assertEqual(status, 404)

    def test_api_post_validation(self):
        status, _h, body = self.request("/api/alerts/run", b"not json", {"Content-Type": "text/plain"})
        self.assertEqual(status, 400)
        status, body = self.post_json("/api/alerts/1/status", {"status": "exploded"})
        self.assertEqual(status, 400)
        status, body = self.post_json("/api/risk/weights", {"weights": {"hazard": 1}})
        self.assertEqual(status, 400)

    def test_api_writes(self):
        status, body = self.post_json("/api/alerts/run", {})
        self.assertEqual(status, 200)
        self.assertIn("rules_fired", body["data"])
        status, body = self.post_json("/api/resources", {"code": "API-01", "name": "API centre", "type": "cooling_centre",
                                                         "location_code": "SPR-02", "amount": 120, "radius_km": 2})
        self.assertEqual(status, 200)
        status, body = self.post_json("/api/resources", {"code": "API-01", "name": "Again", "type": "cooling_centre",
                                                         "location_code": "SPR-02", "amount": 120, "radius_km": 2})
        self.assertEqual(status, 409)
        status, body = self.post_json("/api/resources/API-01", {"status": "limited", "amount": 100})
        self.assertEqual(status, 200)
        status, body = self.post_json("/api/risk/weights", {"weights": {"hazard": 0.5, "exposure": 0.2,
                                                                         "vulnerability": 0.2, "lack_of_capacity": 0.1}})
        self.assertEqual(status, 200)
        self.assertEqual(len(body["data"]), 16)

    # ------------------------------------------------------------------ forms
    def test_form_post_redirects(self):
        status, headers, _b = self.post_form("/alerts/run", {})
        self.assertEqual(status, 303)
        self.assertTrue(headers["Location"].startswith("/alerts?msg="))

    def test_form_error_comes_back_as_message(self):
        status, headers, _b = self.post_form("/resources/add", {"code": "X", "name": "", "type": "cooling_centre",
                                                                 "location_code": "SPR-01", "amount": "-4"})
        self.assertEqual(status, 303)
        self.assertIn("err=", headers["Location"])

    def test_cross_site_post_refused(self):
        status, _h, _b = self.post_form("/alerts/run", {}, origin="https://evil.example")
        self.assertEqual(status, 403)

    def test_csv_upload(self):
        boundary = "----noortest"
        csv = ("location_code,date,t_max,t_min,humidity\nSPR-03,2026-06-04,44.0,31.0,24\n"
               "SPR-03,not-a-date,44,31,24\n")
        fields = {"source_name": "Test logger", "kind": "measured", "licence": "test"}
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields.items()]
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="obs.csv"\r\n'
                     f'Content-Type: text/csv\r\n\r\n{csv}\r\n--{boundary}--\r\n')
        status, _h, body = self.request("/data/import", "".join(parts).encode(),
                                        {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        self.assertEqual(status, 200)
        self.assertIn(b"1 accepted", body)
        self.assertIn(b"1 rejected", body)

    # ------------------------------------------------------------------ charts and exports
    def test_charts_are_png(self):
        for path in ("/chart/risk-map.png", "/chart/risk-map.png?layer=vulnerability", "/chart/risk-bars.png",
                     "/chart/histogram.png", "/chart/heatmap.png", "/chart/trend.png?location=SPR-01",
                     "/chart/allocation.png", "/chart/scenario.png?temperature_increase=1",
                     "/chart/dimensions/SPR-01.png"):
            status, headers, body = self.request(path)
            self.assertEqual(status, 200, path)
            self.assertEqual(headers["Content-Type"], "image/png")
            self.assertTrue(body.startswith(b"\x89PNG"), path)

    def test_exports_have_provenance(self):
        for path in ("/export/risk.csv", "/export/vulnerability.csv", "/export/alerts.csv", "/export/allocation.csv",
                     "/export/scenario.csv?temperature_increase=1", "/export/observations.csv?location=SPR-01"):
            status, headers, body = self.request(path)
            text = body.decode("utf-8")
            self.assertEqual(status, 200, path)
            self.assertIn("attachment", headers["Content-Disposition"])
            self.assertTrue(text.startswith("# NOOR report"), path)
            self.assertIn("# Generated:", text)
            self.assertIn("# Limitations:", text)


if __name__ == "__main__":
    unittest.main()
