"""The website's HTTP server, built on Python's standard library (http.server).

NoorHandler reads the URL, runs the matching screen, action, chart or export and writes the
response. Locally it runs under ThreadingHTTPServer (`python web.py`); on Vercel the same
class is used by api/index.py. Every request opens its own Database connection.
"""
import io
import os
import re
import sqlite3
import sys
import threading
import traceback
import zipfile
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from .. import charts, reports, settings
from ..climate import explorer_table, monthly_means
from ..database import Database
from ..exceptions import ConflictError, NoorError, NotFoundError, ValidationError
from ..importer import REQUIRED, read_upload, validate
from ..service import NoorService
from . import pages
from .html import page

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".svg": "image/svg+xml"}
MAX_BODY_BYTES = 2_500_000
STATUS_CODES = {ValidationError: 400, NotFoundError: 404, ConflictError: 409}
_setup_lock = threading.Lock()
_setup_done = False

SCREENS = {
    "/": pages.overview,
    "/monitoring": pages.monitoring,
    "/risk": pages.risk,
    "/alerts": pages.alerts,
    "/resources": pages.resources,
    "/scenario": pages.scenario,
    "/reports": pages.reports_page,
    "/data": pages.data_page,
}
CODE = r"([A-Za-z0-9_-]{2,20})"


def prepare():
    """Create tables and load the demo data once per server process (thread-safe)."""
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


def chrome(svc):
    """Sidebar badge and data notice, same wording as the desktop app."""
    status = svc.status()
    if status["synthetic_only"]:
        chip, notice = ("SYNTHETIC DEMONSTRATION DATA",
                        "All data is synthetic demonstration data (a fictional district), not IMD observations.")
    else:
        kinds = ", ".join(settings.DATA_KINDS[k] for k in status["data_kinds"])
        chip, notice = ("DATA: " + kinds).upper(), "Data kinds in use: " + kinds + "."
    return {"alerts": len(svc.db.list_alerts(status="active")), "chip": chip, "notice": notice}


class NoorHandler(BaseHTTPRequestHandler):
    """Handles one HTTP request."""

    protocol_version = "HTTP/1.1"
    server_version = "NOOR/2.0"
    sys_version = ""

    # ------------------------------------------------------------------ responses
    def send(self, status, body, content_type, extra=None):
        """Write status, security headers and body."""
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                                                    "script-src 'self'; form-action 'self'; frame-ancestors 'none'; "
                                                    "base-uri 'self'")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def redirect(self, location):
        """303 See Other after a form post, so refreshing does not resubmit."""
        self.send(303, "", "text/plain", {"Location": location})

    def log_message(self, fmt, *args):
        """Quieter log: one line per request on stderr."""
        sys.stderr.write("%s %s\n" % (self.command, self.path[:120]))

    # ------------------------------------------------------------------ parsing
    def query(self):
        return {k: v[0].strip() for k, v in parse_qs(urlparse(self.path).query).items()}

    def read_form(self):
        """Fields (and uploaded files) of a urlencoded or multipart form."""
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self.close_connection = True
            raise ValidationError("Request is too large (limit 2.5 MB)")
        raw = self.rfile.read(length) if length else b""
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
        return {k: v[0].strip() for k, v in parse_qs(raw.decode("utf-8", "replace")).items()}, {}

    def same_origin(self):
        """Refuse form posts from other websites."""
        origin = self.headers.get("Origin")
        return not origin or origin == "null" or urlparse(origin).netloc == self.headers.get("Host")

    # ------------------------------------------------------------------ verbs
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path.startswith("/static/"):
            return self.static(path)
        if path == "/health":
            return self.send(200, '{"ok": true}', "application/json")
        self.safely(lambda svc: self.route_get(svc, path))

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if not self.same_origin():
            self.close_connection = True
            return self.send(403, "Cross-site request refused.", "text/plain; charset=utf-8")
        self.safely(lambda svc: self.route_post(svc, path))

    def safely(self, action):
        """Open the database, run the action, and turn any error into a friendly page."""
        db = None
        try:
            prepare()
            db = Database()
            action(NoorService(db))
        except NoorError as exc:
            self.error_page(db, STATUS_CODES.get(type(exc), 400), exc.message)
        except sqlite3.Error as exc:
            traceback.print_exc(file=sys.stderr)
            self.error_page(db, 500, f"The database could not complete the action ({exc}).")
        except Exception:  # noqa: BLE001 - log it, never show a traceback to the visitor
            traceback.print_exc(file=sys.stderr)
            self.error_page(db, 500, "Something went wrong. The error has been logged.")
        finally:
            if db is not None:
                db.close()

    def error_page(self, db, status, message):
        if self.path.startswith(("/chart/", "/export/")) or db is None:
            return self.send(status, message, "text/plain; charset=utf-8")
        svc = NoorService(db)
        self.send(status, page("", "Please check", "", pages.error_body(message), chrome(svc), err=message),
                  "text/html; charset=utf-8")

    # ------------------------------------------------------------------ GET
    def route_get(self, svc, path):
        q = self.query()
        if path in SCREENS:
            key, title, subtitle, body = SCREENS[path](svc, q)
            html = page(key, title, subtitle, body, chrome(svc), q.get("msg"), q.get("err"))
            return self.send(200, html, "text/html; charset=utf-8", {"Cache-Control": "no-store"})
        found = re.fullmatch(r"/chart/([a-z]+)\.png", path)
        if found:
            png = charts.to_png(self.chart(svc, found.group(1), q))
            return self.send(200, png, "image/png", {"Cache-Control": "no-store"})
        found = re.fullmatch(r"/export/([a-z_]+)\.(csv|zip)", path)
        if found:
            return self.export(svc, found.group(1), found.group(2), q)
        raise NotFoundError("There is no page at this address.")

    def chart(self, svc, name, q):
        """Draw one chart (the same functions the desktop app uses)."""
        db = svc.db
        if name == "distribution":
            return charts.risk_distribution(db.latest_assessments())
        if name == "heatmap":
            return charts.temperature_heatmap(db.observations_frame(), int(q.get("days", 30)))
        if name == "monthly":
            return charts.monthly_chart(monthly_means(db.observations_frame()))
        if name == "trend":
            code = q.get("code", "")
            observed = db.observations_frame([code])
            observed = observed[observed["is_forecast"] == 0]
            if observed.empty:
                return charts.empty_chart("No observations for this location")
            start = pages.check_date(q.get("start"), "From") or observed["date"].min()
            end = pages.check_date(q.get("end"), "To") or observed["date"].max()
            return charts.trend_chart(explorer_table(observed, min(start, end), max(start, end)),
                                      f"{code}: daily temperatures")
        if name == "allocation":
            return charts.allocation_chart(svc.plan(q.get("strategy", "risk_first")))
        if name == "scenario":
            return charts.scenario_chart(svc.scenario(pages.scenario_params(q))["comparison"])
        if name == "dimensions":
            weights = {k: q[k] for k in settings.RISK_WEIGHTS if k in q} or None
            return charts.dimension_chart(svc.assessment(q.get("code", ""), weights))
        if name == "report":
            return self.report_chart(svc, int(q.get("i", 0)))
        if name == "empty":
            return charts.empty_chart("No observations")
        raise NotFoundError("Unknown chart")

    @staticmethod
    def report_chart(svc, index):
        """The nine charts of Reports & Analytics, in the desktop order."""
        db = svc.db
        makers = [
            lambda: charts.risk_bars(db.latest_assessments()),
            lambda: charts.risk_distribution(db.latest_assessments()),
            lambda: charts.score_histogram(db.latest_assessments()),
            lambda: charts.risk_map(db.latest_assessments(), "score"),
            lambda: charts.risk_map(svc.assess(), "hazard"),
            lambda: charts.risk_map(svc.assess(), "vulnerability"),
            lambda: charts.temperature_heatmap(db.observations_frame()),
            lambda: charts.monthly_chart(monthly_means(db.observations_frame())),
            lambda: charts.allocation_chart(svc.plan("risk_first")),
        ]
        if not 0 <= index < len(makers):
            raise NotFoundError("Unknown chart")
        return makers[index]()

    def export(self, svc, name, ext, q):
        """CSV reports (with provenance headers), the import template and a ZIP of all charts."""
        db = svc.db
        note = reports.data_note(svc.status())
        if ext == "zip" and name == "charts":
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
                for i, title in enumerate(pages.REPORT_CHARTS):
                    fname = "".join(ch if ch.isalnum() else "_" for ch in title.lower()).strip("_") + ".png"
                    z.writestr(fname, charts.to_png(self.report_chart(svc, i)))
            return self.download(buffer.getvalue(), "noor_charts.zip", "application/zip")
        texts = {
            "risk": lambda: reports.risk_report(db.latest_assessments(), note),
            "vulnerability": lambda: reports.vulnerability_report(db.list_locations(), db.latest_assessments(), note),
            "alerts": lambda: reports.alerts_report(db.list_alerts(), note),
            "plan_risk": lambda: reports.allocation_report(svc.plan("risk_first"), note),
            "plan_population": lambda: reports.allocation_report(svc.plan("population_first"), note),
            "observations": lambda: reports.observations_report(pages.filtered_observations(svc, q), note),
            "scenario": lambda: reports.scenario_report(svc.scenario(pages.scenario_params(q)), note),
            "template": lambda: ",".join(REQUIRED + ["is_forecast"]) + "\n",
        }
        if ext != "csv" or name not in texts:
            raise NotFoundError("Unknown export")
        return self.download(texts[name]().encode("utf-8"), f"noor_{name}.csv", "text/csv; charset=utf-8")

    def download(self, data, filename, ctype):
        self.send(200, data, ctype, {"Content-Disposition": f'attachment; filename="{filename}"',
                                     "Cache-Control": "no-store"})

    def static(self, path):
        name = os.path.basename(path)
        full = os.path.join(STATIC_DIR, name)
        ext = os.path.splitext(name)[1]
        if ext not in STATIC_TYPES or not os.path.isfile(full):
            return self.send(404, "Not found", "text/plain; charset=utf-8")
        with open(full, "rb") as f:
            self.send(200, f.read(), STATIC_TYPES[ext], {"Cache-Control": "public, max-age=300"})

    # ------------------------------------------------------------------ POST (form actions)
    def route_post(self, svc, path):
        fields, files = self.read_form()
        back = fields.get("back", "/")
        if not back.startswith("/") or back.startswith("//"):
            back = "/"
        if path == "/monitoring/import":
            return self.import_csv(svc, fields, files)
        try:
            message = self.action(svc, path, fields)
        except NoorError as exc:
            return self.redirect(self.with_message(back, "err", exc.message))
        self.redirect(self.with_message(back, "msg", message))

    @staticmethod
    def with_message(back, key, text):
        joiner = "&" if "?" in back else "?"
        return back + joiner + urlencode({key: text})

    def action(self, svc, path, f):
        """Run one form action and return the status message (same wording as the desktop app)."""
        if path == "/actions/recalculate":
            return f"Risk recalculated and saved for {len(svc.recalculate())} locations."
        if path == "/actions/alerts":
            new, found = svc.run_alerts()
            return (f"Warning rules fired {found} time(s); {new} new alert(s) saved (alerts already on record are "
                    f"not repeated).")
        found = re.fullmatch(r"/alerts/(\d{1,9})/status", path)
        if found:
            svc.db.set_alert_status(int(found.group(1)), f.get("status", ""))
            return f"Alert #{found.group(1)} marked {f.get('status')}."
        if path == "/resources/add":
            resource = svc.add_resource(f)
            return f"Added {resource.code}: {resource.describe()}. Risk recalculated."
        found = re.fullmatch(r"/resources/" + CODE + r"/(update|move|delete)", path)
        if found:
            code, verb = found.groups()
            if verb == "update":
                svc.update_resource(code, f.get("status", ""), f.get("amount", ""))
                return f"Saved {code}: {f.get('status')}, amount {f.get('amount')}. Risk recalculated."
            if verb == "move":
                svc.move_resource(code, f.get("location", ""))
                return f"Moved {code} to {f.get('location')}. Risk recalculated."
            svc.delete_resource(code)
            return f"Deleted {code}. Risk recalculated."
        if path == "/plans/save":
            name, strategy = f.get("name", ""), f.get("strategy", "risk_first")
            svc.save_plan(name, strategy)
            return f"Plan '{name.strip()}' saved."
        if path == "/data/locations":
            location = svc.add_location(f)
            return (f"Added location {location.code} ({location.name}). Risk recalculated; it will be 'Insufficient "
                    f"data' until observations are imported for it.")
        raise NotFoundError("Unknown action")

    def import_csv(self, svc, fields, files):
        """Check or import an uploaded CSV, then show the result on the Import tab."""
        data = files.get("file") or b""
        msg = err = None
        try:
            if not data:
                raise ValidationError("Choose a CSV file first")
            if fields.get("action") == "check":
                df = read_upload(data)
                clean, errors = validate(df, {l["code"] for l in svc.db.list_locations()})
                report = {"text": f"{len(df):,} row(s) read: {len(clean):,} valid, {len(df) - len(clean):,} rejected. "
                                  f"Nothing was saved (check only).", "errors": errors[:500]}
                msg = "File checked; nothing saved."
            else:
                result = svc.import_csv(data, fields.get("source"), fields.get("kind"), fields.get("licence"))
                extra = (f"Saved under the data source '{result['source']}' and risk recalculated."
                         if result.get("source") else "Nothing was saved because no row was valid.")
                if result["more_errors"]:
                    extra += f" ({result['more_errors']} more problems not listed.)"
                report = {"text": f"{result['rows']:,} row(s) read: {result['accepted']:,} valid, "
                                  f"{result['rejected']:,} rejected. {extra}", "errors": result["errors"]}
                msg = f"Imported {result['accepted']:,} rows." if result.get("source") else None
                err = None if result.get("source") else "No valid rows: nothing imported."
        except NoorError as exc:
            report, err = {"text": exc.message, "errors": []}, exc.message
        key, title, subtitle, body = pages.monitoring(svc, {"tab": "import"}, report)
        self.send(200, page(key, title, subtitle, body, chrome(svc), msg, err), "text/html; charset=utf-8",
                  {"Cache-Control": "no-store"})


def run(port=3060, host="127.0.0.1"):
    """Serve the website locally until Ctrl+C."""
    prepare()
    server = ThreadingHTTPServer((host, port), NoorHandler)
    print(f"NOOR website on http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

