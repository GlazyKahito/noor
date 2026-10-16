"""Vercel entry point. Vercel's Python runtime calls the class named `handler`.

Vercel's file system is read-only except /tmp, so the database is created in /tmp and filled
from the seed on a cold start (see noor/settings.py). Writes last only as long as that
server instance; see docs/DEPLOYMENT.md.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")  # Matplotlib needs a writable cache folder

from noor.web.server import NoorHandler, prepare  # noqa: E402

prepare()


class handler(NoorHandler):
    """Same handler as the local server."""
