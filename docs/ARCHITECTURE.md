# Architecture

## Constraints that shaped it

NOOR is built only with what the *Object Oriented Programming with Python* laboratory covers,
so every line can be explained and changed in a viva:

| Layer | Technology |
| --- | --- |
| Language | Python 3.12+ |
| Desktop GUI | Tkinter + ttk (`ttk.Notebook`, `ttk.Treeview`, `ttk.Style`) |
| Database | SQLite through `sqlite3` |
| Data processing | Pandas |
| Numerical computing | NumPy |
| Charts | Matplotlib, embedded with `FigureCanvasTkAgg` |
| Tests | `unittest` |
| Input / output | CSV |

The rest is the standard library: `threading`, `queue`, `abc`, `argparse`, `datetime`. No
web framework, ORM or extra chart library.

## Layers

```
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ app.py  →  noor/gui/main_window.py  NoorApp(tk.Tk)                         │  presentation
  │   sidebar.py  widgets.py (Page, Card, DataTable, ChartPanel, Form)         │  (Tkinter)
  │   dashboard · monitoring · risk_assessment · alerts_view ·                 │
  │   resource_allocation · scenario_lab · reports_view · data_view           │
  │   charts.py (Matplotlib Figures)   reports.py (CSV text)                   │
  └──────────────────────────────────────────────────────────────────────────┘
                       │  calls only
                       ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ noor/service.py   NoorService  (use cases: setup, assess, alerts, plan,     │  business logic
  │                   scenario, import, add / update / move / delete)         │
  └──────────────────────────────────────────────────────────────────────────┘
        │ objects & DataFrames                         │ SQL
        ▼                                              ▼
  ┌───────────────────────────────┐        ┌────────────────────────────────┐
  │ analytics (no SQL, no GUI)    │        │ noor/database.py  Database     │  persistence
  │ models.py   climate.py        │        │ noor/schema.sql   8 tables     │
  │ risk.py     alerts.py         │        │ noor/queries.py   SQL examples │
  │ allocation.py scenario.py     │        └────────────────────────────────┘
  │ importer.py                   │                        │
  └───────────────────────────────┘               instance/noor.db (SQLite)
```

Rules the code follows:

- Screens never run SQL or maths themselves; they call `NoorService`, `Database` read methods
  and the chart functions.
- Analytics modules never import `database` or `gui`. They take objects and DataFrames and
  return dicts, so the unit tests call them directly.
- All SQL is in `database.py` and `queries.py`, always with `?` parameters.
- All numbers that change behaviour are in `settings.py`.

## Start-up

1. `app.py` creates `NoorApp`. It applies the ttk styles (`styles.apply_styles`), hides the
   main window and shows the `Splash` card.
2. `NoorApp.run_task("Preparing the database", svc.setup, …)` runs on a background thread with
   its own `Database`. `setup()` runs `schema.sql` (`CREATE TABLE IF NOT EXISTS`, safe every
   time). On an empty database it loads the demo data, calculates risk, runs the warning
   rules and saves two plans. On later starts it only recalculates risk.
3. Back on the main thread `_on_setup_done` opens the main connection, builds the sidebar,
   header and status bar, and opens the Overview.

## How a screen works (example: Risk Assessment)

1. Clicking **Risk Assessment** calls `NoorApp.navigate("risk")`. The first time, it creates
   `RiskPage(content, app)`; `Page.__init__` calls `build()` to create the widgets.
2. `refresh()` reads `db.latest_assessments()` and fills a `DataTable` (a `ttk.Treeview`).
3. Selecting a row calls `show_location(code)`, which calls `svc.assessment(code)`. That loads
   `Location` and `Resource` objects and observation DataFrames and runs `RiskEngine.assess`.
   The reasons, the indicator table and `charts.dimension_chart(result)` are shown.
4. A button that changes data (for example **Recalculate and save**) saves through the
   service, then calls `app.data_changed()`. That reloads the current screen and marks the
   others to reload when next opened, so tables and charts never show stale numbers.

## Background work and threads

- `NoorApp.run_task(label, work, on_done)` starts a `threading.Thread`. The thread opens its
  own `sqlite3` connection (connections are not shared between threads), runs `work(service)`
  inside `try / except / finally` (the `finally` closes the connection) and puts the result
  in a `queue.Queue`.
- The main thread polls the queue with `after(40, …)`, because Tkinter widgets may only be
  touched from the main thread. It then calls `on_done(result)` or shows the error.
- Only one task runs at a time; the status bar shows a progress bar meanwhile.
- `Database.write_lock`, a class-level `threading.Lock`, serialises every write.

Used for the first start, recalculation, warning rules, CSV import and the Scenario Lab.

## Errors

- Every expected problem raises a `NoorError` (`ValidationError`, `NotFoundError`,
  `ConflictError`) with a readable message, for example a bad date or weights that do not add
  up to 1.
- `NoorApp.report_callback_exception` and `NoorApp.safely` catch errors from any button or
  screen. `show_error` puts the message in the status bar and a message box. Database and
  file errors get their own titles. Nothing crashes the window, and no traceback is shown
  to the user.

## Charts

`noor/charts.py` builds every chart with `matplotlib.figure.Figure` (the object-oriented API,
no global `pyplot` state) and returns the Figure. `widgets.ChartPanel.show(fig)` wraps it in
`FigureCanvasTkAgg`, so it resizes with the window. `charts.save_png(fig, path)` writes the
same Figure to a file (Reports → Charts, and `scripts/export_charts.py`).

## The website

`noor/web/` shows the same eight screens in a browser. A browser cannot run Tkinter, so each
screen is an HTML page built by `pages.py` from the same data the desktop screen uses; the
sentences and table rows come from `noor/summaries.py`, which both interfaces import.

- `server.py` → `NoorHandler(BaseHTTPRequestHandler)` routes `GET /`, `/monitoring`, `/risk`,
  `/alerts`, `/resources`, `/scenario`, `/reports`, `/data`; `/chart/<name>.png` (the same
  Matplotlib Figures, turned into PNG bytes by `charts.to_png`); `/export/<name>.csv` (the same
  `reports.py` CSVs) and `/export/charts.zip`.
- Buttons that change data are HTML forms posted to `/actions/...`, `/alerts/<id>/status`,
  `/resources/...`, `/plans/save`, `/data/locations` and `/monitoring/import`. The server calls the
  same `NoorService` method as the desktop button, then sends the browser back to the screen with
  the status message (post/redirect/get). Posts from other websites are refused.
- Locally: `python web.py` (a `ThreadingHTTPServer`, one thread and one database connection per
  request). On Vercel: `api/index.py` subclasses the handler; `vercel.json` sends every URL to it.
  The database is created in `/tmp` from the demo data when a server instance starts.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `NOOR_DB_PATH` | `instance/noor.db` | SQLite file (the tests use a temporary file) |
| `VERCEL` | set by Vercel | the website keeps its database in `/tmp/noor.db` |

There are no secrets: NOOR calls no paid API and needs no keys.

## Database lifecycle

- `Database.create_tables()` runs `schema.sql`, safe on every start.
- `NoorService.setup()` seeds only an empty database.
- `python app.py --init` prepares the database without opening a window, and
  `python app.py --reset` deletes it and rebuilds the demo data.
- Changing the schema: edit `schema.sql`, then `python app.py --reset`. A project with real
  data would add `ALTER TABLE` steps instead; see [VIVA_NOTES.md](VIVA_NOTES.md).
