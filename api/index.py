"""Vercel entry point. Vercel's Python runtime calls the class named `handler`.

vercel.json rewrites every URL to this file and passes the original path in the query
parameter `__path` (for example /risk/SPR-01 arrives as /api/index?__path=risk/SPR-01).
restore_path() puts the original path back before NoorHandler routes the request.

Vercel's file system is read-only except /tmp, so the database is created in /tmp and filled
from the seed on a cold start (see noor/settings.py). Writes last only as long as that
server instance; see docs/DEPLOYMENT.md.
"""
import os
import sys
from urllib.parse import parse_qsl, urlencode, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")  # Matplotlib needs a writable cache folder

from noor.web.server import NoorHandler, prepare  # noqa: E402

prepare()


class handler(NoorHandler):
    """The local NoorHandler plus one step: undo Vercel's rewrite."""

    def restore_path(self):
        """Turn /api/index?__path=risk/SPR-01&path=risk/SPR-01&x=1 back into /risk/SPR-01?x=1."""
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/index"):
            return
        params = parse_qsl(parsed.query, keep_blank_values=True)
        captured = next((value for key, value in params if key == "__path"), "")
        original = "/" + captured.lstrip("/")
        # Vercel also appends the rewrite's capture as `path=...`; drop that echo too.
        rest = urlencode([(key, value) for key, value in params
                          if key != "__path" and not (key == "path" and value == captured)])
        self.path = original + ("?" + rest if rest else "")

    def do_GET(self):
        """Restore the path, then handle as usual."""
        self.restore_path()
        super().do_GET()

    def do_HEAD(self):
        """Restore the path, then handle as usual."""
        self.restore_path()
        super().do_HEAD()

    def do_POST(self):
        """Restore the path, then handle as usual."""
        self.restore_path()
        super().do_POST()
