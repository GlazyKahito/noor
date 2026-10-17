"""NoorApp: the main window (sidebar + header + screen area + status bar).

Start-up: a splash screen is shown while a background thread prepares the database (on the
first run it creates the tables and loads the demo data). Slow jobs later on (scenarios,
imports, recalculation) also run on a background thread through run_task(), so the window
never freezes. Each thread opens its own Database connection.
"""
import queue
import sqlite3
import threading
import tkinter as tk
import traceback
from tkinter import messagebox, ttk

from .. import settings
from ..database import Database
from ..exceptions import NoorError
from ..service import NoorService
from . import styles
from .alerts_view import AlertsPage
from .dashboard import DashboardPage
from .data_view import DataPage
from .monitoring import MonitoringPage
from .reports_view import ReportsPage
from .resource_allocation import ResourcesPage
from .risk_assessment import RiskPage
from .scenario_lab import ScenarioPage
from .sidebar import Sidebar
from .styles import CARD, FONTS, LINE, MUTED, SAND, WINE

# (key, label in the sidebar, Page class); Ctrl+1 opens the first one, and so on
PAGES = [
    ("overview", "Overview", DashboardPage),
    ("monitoring", "Climate Monitoring", MonitoringPage),
    ("risk", "Risk Assessment", RiskPage),
    ("alerts", "Alerts", AlertsPage),
    ("resources", "Resource Allocation", ResourcesPage),
    ("scenario", "Scenario Lab", ScenarioPage),
    ("reports", "Reports & Analytics", ReportsPage),
    ("data", "Data Management", DataPage),
]


class NoorApp(tk.Tk):
    """The desktop application window."""

    def __init__(self, db_path=None, splash=True):
        super().__init__()
        self.db_path = db_path or settings.database_path()
        self.db = None
        self.svc = None
        self.pages = {}          # key -> Page object (built the first time it is opened)
        self.stale = set()       # pages whose data changed since they were last shown
        self.current = None
        self.ready = False
        self.busy = False
        self.errors = []         # unexpected errors (the tests check this stays empty)
        self._results = queue.Queue()

        self.title("NOOR — Climate Intelligence")
        self.minsize(1180, 700)
        self.geometry(self._start_geometry())
        styles.apply_styles(self)
        self.report_callback_exception = self._callback_error  # errors in button handlers
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<F5>", lambda e: self.reload_current())

        self.splash = None
        if splash:
            self.withdraw()
            self.splash = Splash(self)
        self.run_task("Preparing the database", lambda svc: svc.setup(), self._on_setup_done)

    def _start_geometry(self):
        """Open at 1400x860, or smaller on small screens, centred."""
        width = min(1400, self.winfo_screenwidth() - 60)
        height = min(860, self.winfo_screenheight() - 90)
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 3)
        return f"{width}x{height}+{x}+{y}"

    # ------------------------------------------------------------------ start-up
    def _on_setup_done(self, summary):
        """Database is ready: open the main connection and build the window."""
        self.db = Database(self.db_path)
        self.svc = NoorService(self.db)
        self._build_layout()
        if self.splash is not None:
            self.splash.destroy()
            self.splash = None
            self.deiconify()
        self.ready = True
        self.navigate("overview")
        if summary:
            self.set_status("First run: created the database and loaded the synthetic demonstration data.", "ok")
        else:
            self.set_status(f"Database loaded from {self.db_path}", "ok")

    def _build_layout(self):
        self.sidebar = Sidebar(self, [(k, label) for k, label, _ in PAGES], self.navigate)
        self.sidebar.pack(side="left", fill="y")

        main = ttk.Frame(self)
        main.pack(side="left", fill="both", expand=True)
        header = ttk.Frame(main, padding=(22, 16, 22, 8))
        header.pack(fill="x")
        self.page_title = ttk.Label(header, text="", style="Title.TLabel")
        self.page_title.pack(side="left", anchor="w")
        self.data_chip = tk.Label(header, text="", bg=styles.WINE_TINT, fg=WINE, font=FONTS["caps"], padx=10, pady=4)
        self.data_chip.pack(side="right", anchor="e")
        self.page_subtitle = ttk.Label(main, text="", style="Muted.TLabel", padding=(24, 0, 22, 8))
        self.page_subtitle.pack(fill="x")

        status = tk.Frame(main, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        status.pack(side="bottom", fill="x")
        self.status_text = tk.Label(status, text="", bg=CARD, fg=MUTED, font=FONTS["small"], anchor="w", padx=12,
                                    pady=5)
        self.status_text.pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=140, style="Wine.Horizontal.TProgressbar")

        self.content = ttk.Frame(main)
        self.content.pack(fill="both", expand=True)
        self.refresh_chrome()

    # ------------------------------------------------------------------ navigation
    def navigate(self, key):
        """Show a screen (building it the first time) and reload it if its data changed."""
        if not self.ready:
            return
        cls = {k: c for k, _l, c in PAGES}[key]
        if self.current is not None:
            self.pages[self.current].pack_forget()
        first_time = key not in self.pages
        if first_time:
            self.pages[key] = cls(self.content, self)
        page = self.pages[key]
        page.pack(fill="both", expand=True)
        self.current = key
        self.sidebar.set_active(key)
        self.page_title.configure(text=page.title)
        self.page_subtitle.configure(text=page.subtitle)
        if first_time or key in self.stale:
            self.stale.discard(key)
            self.safely(page.refresh)

    def page(self, key):
        """Open a screen and return its Page object."""
        self.navigate(key)
        return self.pages[key]

    def reload_current(self):
        """F5: reload the screen on display."""
        if self.current:
            self.safely(self.pages[self.current].refresh)
            self.set_status("Reloaded from the database.", "ok")

    def data_changed(self):
        """Something was saved: reload the current screen now and the others when next opened."""
        self.stale = {key for key in self.pages if key != self.current}
        self.refresh_chrome()
        if self.current:
            self.safely(self.pages[self.current].refresh)

    def refresh_chrome(self):
        """Alert badge in the sidebar and the data-kind chip in the header."""
        active = len(self.db.list_alerts(status="active"))
        self.sidebar.set_badge("alerts", active)
        status = self.svc.status()
        if status["synthetic_only"]:
            self.data_chip.configure(text="SYNTHETIC DEMONSTRATION DATA")
            self.sidebar.set_notice("All data is synthetic demonstration data (a fictional district), "
                                    "not IMD observations.")
        else:
            kinds = ", ".join(settings.DATA_KINDS[k] for k in status["data_kinds"])
            self.data_chip.configure(text=("DATA: " + kinds).upper())
            self.sidebar.set_notice("Data kinds in use: " + kinds + ".")

    # ------------------------------------------------------------------ status bar and errors
    def set_status(self, text, kind="info"):
        """Message at the bottom of the window. kind: info, ok, warn, error."""
        colour = {"ok": styles.OK, "warn": styles.WARN, "error": WINE}.get(kind, MUTED)
        if hasattr(self, "status_text"):
            self.status_text.configure(text=text, fg=colour)

    def show_error(self, exc):
        """Friendly message for any error; never a crash."""
        if isinstance(exc, NoorError):
            self.set_status(exc.message, "error")
            messagebox.showwarning("Please check", exc.message, parent=self)
        elif isinstance(exc, sqlite3.Error):
            self.set_status(f"Database error: {exc}", "error")
            messagebox.showerror("Database error", f"The database could not complete the action.\n\n{exc}", parent=self)
        elif isinstance(exc, OSError):
            self.set_status(f"File error: {exc}", "error")
            messagebox.showerror("File error", str(exc), parent=self)
        else:
            self.errors.append(exc)
            traceback.print_exception(exc)
            self.set_status(f"Unexpected error: {type(exc).__name__}: {exc}", "error")
            messagebox.showerror("Unexpected error", f"{type(exc).__name__}: {exc}", parent=self)

    def safely(self, func, *args):
        """Run func(*args); show any error instead of raising. Returns func's result or None."""
        try:
            return func(*args)
        except Exception as exc:  # noqa: BLE001 - every error is shown to the user
            self.show_error(exc)
            return None

    def _callback_error(self, exc_type, exc, tb):
        """Tkinter calls this for an error inside an event handler."""
        self.show_error(exc)

    # ------------------------------------------------------------------ background work
    def run_task(self, label, work, on_done=None):
        """Run work(service) on a background thread, then on_done(result) on the main thread.

        The thread opens its own Database connection. Only one task runs at a time."""
        if self.busy:
            self.set_status("Please wait: another task is still running.", "warn")
            return False
        self.busy = True
        self.set_status(label + " …")
        if hasattr(self, "progress"):
            self.progress.pack(side="right", padx=10)
            self.progress.start(12)
        if self.splash is not None:
            self.splash.set_message(label + " …")

        def worker():
            db = None
            try:
                db = Database(self.db_path)
                outcome = ("ok", work(NoorService(db)))
            except Exception as exc:  # noqa: BLE001 - passed to the main thread and shown there
                outcome = ("error", exc)
            finally:
                if db is not None:
                    db.close()
            self._results.put(outcome)

        threading.Thread(target=worker, daemon=True).start()
        self.after(40, self._check_task, on_done)
        return True

    def _check_task(self, on_done):
        """Poll the result queue (Tkinter widgets may only be touched on the main thread)."""
        try:
            kind, value = self._results.get_nowait()
        except queue.Empty:
            self.after(40, self._check_task, on_done)
            return
        self.busy = False
        if hasattr(self, "progress"):
            self.progress.stop()
            self.progress.pack_forget()
        if kind == "error":
            if self.splash is not None:  # the database could not even be prepared
                self.splash.destroy()
                self.splash = None
                messagebox.showerror("NOOR could not start", f"{type(value).__name__}: {value}")
                self.destroy()
                return
            self.show_error(value)
        elif on_done is not None:
            self.safely(on_done, value)

    def close(self):
        """Close the database connection and the window."""
        if self.db is not None:
            self.db.close()
        self.destroy()


class Splash(tk.Toplevel):
    """Borderless start-up card shown while the database is prepared."""

    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)
        width, height = 520, 300
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 3
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.configure(bg=WINE)
        tk.Label(self, text="N O O R", bg=WINE, fg=SAND, font=(FONTS["title"][0], 44, "bold")).pack(pady=(54, 0))
        tk.Label(self, text="Climate Intelligence & Resilience", bg=WINE, fg=SAND, font=(FONTS["body"][0], 13)).pack()
        tk.Label(self, text="See the risk. Save lives.", bg=WINE, fg="#E7B9C1",
                 font=(FONTS["body"][0], 10, "italic")).pack(pady=(4, 26))
        bar = ttk.Progressbar(self, mode="indeterminate", length=260, style="Wine.Horizontal.TProgressbar")
        bar.pack()
        bar.start(10)
        self.message = tk.Label(self, text="", bg=WINE, fg="#E7B9C1", font=FONTS["small"])
        self.message.pack(pady=(10, 0))
        self.lift()

    def set_message(self, text):
        self.message.configure(text=text)
