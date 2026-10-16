"""The HTTP server, built on Python's standard library (http.server).

NoorHandler reads the URL, finds the matching route, calls a page / API / chart function and
writes the response. Locally it runs under ThreadingHTTPServer (one thread per request);
on Vercel the same class is used by api/index.py.
"""
import json
import os
import re
import sys
import threading
import traceback
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from .. import charts, reports, settings
from ..climate import explorer_table
from ..database import Database
from ..exceptions import NoorError, NotFoundError, ValidationError
from ..service import NoorService
from . import api, pages

MAX_BODY_BYTES = 2_500_000
_setup_lock = threading.Lock()
_setup_done = False


def prepare():
    """Create tables and load demo data once per process (thread-safe)."""
    global _setup_done
    with _setup_lock:
        if _setup_done:
            return
        db = Database()
        try:
            NoorService(db).setup()
        finally:
            db.close()
        _setup_done = True


# --------------------------------------------------------------------------- route tables
# (regex, function). Groups in the regex become extra arguments.
PAGE_ROUTES = [
    (r"/", pages.overview),
    (r"/dashboard", pages.dashboard),
    (r"/explorer", pages.explorer),
    (r"/risk", pages.risk),
    (r"/risk/([A-Za-z0-9_-]{2,20})", pages.risk_detail),
    (r"/map", pages.vulnerability_map),
    (r"/alerts", pages.alerts),
    (r"/resources", pages.resources),
    (r"/plans", pages.plans),
    (r"/scenarios", pages.scenarios),
    (r"/reports", pages.reports),
    (r"/data", pages.data_page),
    (r"/methodology", pages.methodology),
]
API_GET = [
    (r"/api/health", api.health),
    (r"/api/status", api.status),
    (r"/api/config", api.config),
    (r"/api/locations", api.locations),
    (r"/api/locations/([A-Za-z0-9_-]{2,20})", api.location),
    (r"/api/observations", api.observations),
    (r"/api/risk", api.risk),
    (r"/api/risk/([A-Za-z0-9_-]{2,20})", api.risk_detail),
    (r"/api/alerts", api.alerts),
    (r"/api/resources", api.resources),
    (r"/api/plans", api.plan),
    (r"/api/plans/compare", api.plan_compare),
    (r"/api/scenario", api.scenario),
    (r"/api/queries/([a-z_]{2,40})", api.query),
]
API_POST = [
    (r"/api/risk/weights", api.risk_weights),
    (r"/api/alerts/run", api.alerts_run),
    (r"/api/alerts/(\d{1,9})/status", api.alert_status),
    (r"/api/resources", api.resource_create),
    (r"/api/resources/([A-Za-z0-9_-]{2,20})", api.resource_update),
    (r"/api/scenario", api.scenario),
]


def match(routes, path):
    """Return (function, captured groups) for the first route that matches the whole path."""
    for pattern, func in routes:
        found = re.fullmatch(pattern, path)
        if found:
            return func, found.groups()
    return None, ()


class NoorHandler(BaseHTTPRequestHandler):
    """Handles one HTTP request."""

    protocol_version = "HTTP/1.1"  # keep-alive; every response sends Content-Length
    server_version = "NOOR/1.0"
    sys_version = ""

    # ------------------------------------------------------------------ responses
    def send(self, status, body, content_type, extra_headers=None):
        """Write status, security headers and body."""
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'none'; "
                         "form-action 'self'; frame-ancestors 'none'; base-uri 'self'")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status, payload):
        """JSON response."""
        self.send(status, json.dumps(api.clean(payload), default=str), "application/json; charset=utf-8",
                  {"Cache-Control": "no-store"})

    def redirect(self, location):
        """303 See Other after a form POST (so refreshing does not resubmit)."""
        self.send(303, "", "text/plain", {"Location": location})

    def send_error_page(self, status, message):
        """HTML or JSON error depending on the URL."""
        if self.parsed.path.startswith("/api/"):
            self.send_json(status, {"ok": False, "error": {"message": message}})
        else:
            self.send(status, pages.error_page(status, message), "text/html; charset=utf-8")

    # ------------------------------------------------------------------ request parsing
    def query(self):
        """Query string as a dict of single values."""
        return {k: v[0].strip() for k, v in parse_qs(self.parsed.query, keep_blank_values=False).items()}

    def read_body(self):
        """Raw request body (limited in size)."""
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self.close_connection = True  # the unread body must not be parsed as a new request
            raise ValidationError("Request is too large (limit 2.5 MB)")
        return self.rfile.read(length) if length else b""

    def form(self, raw):
        """Parse a urlencoded or multipart form into (fields, files)."""
        ctype = self.headers.get("Content-Type", "")
        if ctype.startswith("multipart/form-data"):
            message = BytesParser(policy=email_policy).parsebytes(
                b"Content-Type: " + ctype.encode("latin-1") + b"\r\n\r\n" + raw)
            fields, files = {}, {}
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if part.get_filename() is not None:
                    files[name] = part.get_payload(decode=True) or b""
                else:
                    fields[name] = (part.get_payload(decode=True) or b"").decode("utf-8", "replace").strip()
            return fields, files
        fields = {k: v[0].strip() for k, v in parse_qs(raw.decode("utf-8", "replace")).items()}
        return fields, {}

    def same_origin(self):
        """Reject cross-site form posts: if the browser sends Origin, it must match our Host."""
        origin = self.headers.get("Origin")
        if not origin or origin == "null":
            return True
        return urlparse(origin).netloc == self.headers.get("Host")

    # ------------------------------------------------------------------ HTTP verbs
    def do_HEAD(self):
        """Same as GET without the body."""
        self.do_GET()

    def do_GET(self):
        """Pages, API reads, charts, exports and static files."""
        self.parsed = urlparse(self.path)
        path = self.parsed.path.rstrip("/") or "/"
        if path.startswith("/static/"):
            return self.static(path)
        self.handle_safely(lambda svc: self.route_get(svc, path))

    def do_POST(self):
        """Form submissions and API writes."""
        self.parsed = urlparse(self.path)
        path = self.parsed.path.rstrip("/") or "/"
        if not self.same_origin():
            self.close_connection = True  # body not read: close instead of keeping the connection
            return self.send_error_page(403, "Cross-site request refused.")
        self.handle_safely(lambda svc: self.route_post(svc, path))

    def handle_safely(self, action):
        """Open the database, run the action, and turn errors into friendly responses."""
        db = None
        try:
            prepare()
            db = Database()
            action(NoorService(db))
        except NoorError as exc:
            if self.parsed.path.startswith("/api/"):
                self.send_json(exc.status, {"ok": False, "error": {"message": exc.message, "details": exc.details}})
            else:
                self.send_error_page(exc.status, exc.message)
        except Exception:  # anything unexpected: log it, never show the traceback to the user
            traceback.print_exc(file=sys.stderr)
            self.send_error_page(500, "Something went wrong on our side. The error has been logged.")
        finally:
            if db is not None:
                db.close()

    # ------------------------------------------------------------------ GET routing
    def route_get(self, svc, path):
        """Find and run the GET handler for a path."""
        q = self.query()
        if path.startswith("/api/"):
            func, args = match(API_GET, path)
            if func is None:
                raise NotFoundError("Unknown API endpoint")
            return self.send_json(200, {"ok": True, "data": func(svc, q, *args)})
        if path.startswith("/chart/"):
            return self.send(200, self.chart(svc, path, q), "image/png", {"Cache-Control": "no-store"})
        if path.startswith("/export/"):
            filename, text = self.export(svc, path, q)
            return self.send(200, text, "text/csv; charset=utf-8",
                             {"Content-Disposition": f'attachment; filename="{filename}"'})
        func, args = match(PAGE_ROUTES, path)
        if func is None:
            raise NotFoundError("Page not found.")
        self.send(200, func(svc, q, *args), "text/html; charset=utf-8")

    def chart(self, svc, path, q):
        """Draw the requested chart and return PNG bytes."""
        if path == "/chart/risk-map.png":
            layer = q.get("layer", "score")
            if layer not in ("score", "hazard", "exposure", "vulnerability", "capacity"):
                raise ValidationError("Unknown layer")
            return charts.risk_map(svc.db.latest_assessments() if layer == "score" else svc.assess(), layer)
        if path == "/chart/risk-bars.png":
            return charts.risk_bars(svc.db.latest_assessments())
        if path == "/chart/histogram.png":
            return charts.score_histogram(svc.db.latest_assessments())
        if path == "/chart/heatmap.png":
            return charts.temperature_heatmap(svc.db.observations_frame())
        if path == "/chart/trend.png":
            code = q.get("location", "")
            svc.db.get_location(code)
            frame = svc.db.observations_frame([code])
            if frame.empty:
                return charts.empty_chart("No observations for this location")
            start = q.get("start") or frame["date"].min()
            end = q.get("end") or frame["date"].max()
            check_date(start)
            check_date(end)
            return charts.trend_chart(explorer_table(frame, min(start, end), max(start, end)), f"{code}: daily temperatures")
        if path == "/chart/allocation.png":
            return charts.allocation_chart(svc.plan(q.get("strategy", "risk_first")))
        if path == "/chart/scenario.png":
            params = {k: v for k, v in q.items() if k != "run"}
            return charts.scenario_chart(svc.scenario(params)["comparison"])
        found = re.fullmatch(r"/chart/dimensions/([A-Za-z0-9_-]{2,20})\.png", path)
        if found:
            return charts.dimension_chart(svc.assessment(found.group(1)))
        raise NotFoundError("Unknown chart")

    def export(self, svc, path, q):
        """Build a CSV report. Returns (filename, text)."""
        note = reports.data_note(svc.status())
        if path == "/export/risk.csv":
            return "noor-risk.csv", reports.risk_report(svc.db.latest_assessments(), note)
        if path == "/export/vulnerability.csv":
            return "noor-vulnerability.csv", reports.vulnerability_report(
                svc.db.list_locations(), svc.db.latest_assessments(), note)
        if path == "/export/alerts.csv":
            return "noor-alerts.csv", reports.alerts_report(svc.db.list_alerts(), note)
        if path == "/export/allocation.csv":
            return "noor-allocation.csv", reports.allocation_report(svc.plan(q.get("strategy", "risk_first")), note)
        if path == "/export/scenario.csv":
            params = {k: v for k, v in q.items() if k != "run"}
            return "noor-scenario.csv", reports.scenario_report(svc.scenario(params), note)
        if path == "/export/observations.csv":
            codes = [q["location"]] if q.get("location") else None
            if codes:
                svc.db.get_location(codes[0])
            for key in ("start", "end"):
                if q.get(key):
                    check_date(q[key])
            frame = svc.db.observations_frame(codes, q.get("start"), q.get("end"))
            return "noor-observations.csv", reports.observations_report(frame, note)
        if path == "/export/template.csv":
            return "noor-import-template.csv", ("location_code,date,t_max,t_min,humidity,is_forecast\n"
                                                "SPR-01,2026-06-03,44.1,31.0,28,0\n")
        raise NotFoundError("Unknown export")

    # ------------------------------------------------------------------ POST routing
    def route_post(self, svc, path):
        """Find and run the POST handler for a path."""
        raw = self.read_body()
        if path.startswith("/api/"):
            func, args = match(API_POST, path)
            if func is None:
                raise NotFoundError("Unknown API endpoint")
            if not self.headers.get("Content-Type", "").startswith("application/json") and raw:
                raise ValidationError("Send JSON with Content-Type: application/json")
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except (ValueError, UnicodeDecodeError):
                raise ValidationError("Body is not valid JSON") from None
            return self.send_json(200, {"ok": True, "data": func(svc, self.query(), body, *args)})
        fields, files = self.form(raw)
        try:
            self.form_action(svc, path, fields, files)
        except NoorError as exc:
            # send the user back to the page the form was on, with the problem shown at the top
            back = "/" + path.strip("/").split("/")[0]
            self.redirect(f"{back}?err={quote(exc.message)}")

    def form_action(self, svc, path, fields, files):
        """HTML form handlers (each ends with a redirect or a page)."""
        if path == "/alerts/run":
            new, found = svc.run_alerts()
            return self.redirect(f"/alerts?msg={quote(f'Warning engine ran: {found} rule hits, {new} new alert(s).')}")
        found = re.fullmatch(r"/alerts/(\d{1,9})/status", path)
        if found:
            svc.db.set_alert_status(int(found.group(1)), fields.get("status"))
            return self.redirect(f"/alerts?msg={quote('Alert updated.')}")
        if path == "/resources/add":
            res = svc.add_resource(fields)
            return self.redirect(f"/resources?msg={quote(f'Added {res.code}. Risk recalculated.')}")
        found = re.fullmatch(r"/resources/([A-Za-z0-9_-]{2,20})/delete", path)
        if found:
            svc.db.delete_resource(found.group(1))
            svc.recalculate()
            return self.redirect(f"/resources?msg={quote(f'Deleted {found.group(1)}. Risk recalculated.')}")
        found = re.fullmatch(r"/resources/([A-Za-z0-9_-]{2,20})", path)
        if found:
            svc.update_resource(found.group(1), fields.get("status"), fields.get("amount"))
            return self.redirect(f"/resources?msg={quote(f'Updated {found.group(1)}. Risk recalculated.')}")
        if path == "/plans/save":
            svc.save_plan(fields.get("plan_name"), fields.get("strategy", "risk_first"))
            return self.redirect(f"/plans?strategy={quote(fields.get('strategy', 'risk_first'))}&msg={quote('Plan saved.')}")
        if path == "/data/import":
            data = files.get("file")
            if not data:
                raise ValidationError("Choose a CSV file to upload")
            report = svc.import_csv(data, fields.get("source_name"), fields.get("kind"), fields.get("licence"))
            return self.send(200, pages.data_page(svc, {}, report), "text/html; charset=utf-8")
        if path == "/data/location":
            loc = svc.add_location(fields)
            return self.redirect(f"/data?msg={quote(f'Added location {loc.code}. Risk recalculated.')}")
        raise NotFoundError("Unknown form action")

    # ------------------------------------------------------------------ static files
    def static(self, path):
        """Serve files from noor/static (no directory traversal)."""
        name = path[len("/static/"):]
        if not re.fullmatch(r"[a-z0-9_-]+\.(css|svg|png)", name):
            return self.send(404, "Not found", "text/plain")
        full = os.path.join(settings.STATIC_DIR, name)
        if not os.path.isfile(full):
            return self.send(404, "Not found", "text/plain")
        types = {"css": "text/css; charset=utf-8", "svg": "image/svg+xml", "png": "image/png"}
        with open(full, "rb") as f:
            self.send(200, f.read(), types[name.rsplit(".", 1)[1]], {"Cache-Control": "public, max-age=3600"})

    def log_message(self, fmt, *args):
        """Log method, path (without query string) and status — nothing the user typed."""
        path = urlparse(self.path).path if hasattr(self, "path") else "-"
        sys.stderr.write(f"{self.log_date_time_string()} {self.command} {path} {args[1] if len(args) > 1 else ''}\n")


def check_date(text):
    """Reject anything that is not YYYY-MM-DD."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(text)):
        raise ValidationError("Dates must be YYYY-MM-DD")


def run(port=3060, host="127.0.0.1"):
    """Start the local server (Ctrl+C to stop)."""
    prepare()
    server = ThreadingHTTPServer((host, port), NoorHandler)
    print(f"NOOR running at http://{host}:{port}  (database: {settings.database_path()})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
