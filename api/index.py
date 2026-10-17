"""Vercel entry point for the NOOR website. Vercel's Python runtime calls the class `handler`.

vercel.json rewrites every URL to this file and passes the original path in `__path` (for
example /risk?code=SPR-01 arrives as /api/index?__path=risk&code=SPR-01). restore_path() puts
the original path back before NoorHandler routes the request.

Only /tmp can be written on Vercel, so the database is created there from the demo data when a
server instance starts (noor/settings.py). Changes last only as long as that instance.
"""
import os
import sys
from urllib.parse import parse_qsl, urlencode, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")  # Matplotlib needs a writable cache folder

from noor.web.server import NoorHandler, prepare  # noqa: E402

prepare()


class handler(NoorHandler):
    """NoorHandler plus one step: undo Vercel's rewrite."""

    def restore_path(self):
        """Turn /api/index?__path=risk&code=SPR-01 back into /risk?code=SPR-01."""
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/index"):
            return
        params = parse_qsl(parsed.query, keep_blank_values=True)
        captured = next((value for key, value in params if key == "__path"), "")
        rest = urlencode([(key, value) for key, value in params
                          if key != "__path" and not (key == "path" and value == captured)])
        self.path = "/" + captured.lstrip("/") + ("?" + rest if rest else "")

    def do_GET(self):
        self.restore_path()
        super().do_GET()

    def do_HEAD(self):
        self.restore_path()
        super().do_HEAD()

    def do_POST(self):
        self.restore_path()
        super().do_POST()
