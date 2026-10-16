# Architecture and setup

## Constraints that shaped it

NOOR is built only with what an Object Oriented Programming with Python laboratory course
covers, so every line can be explained and changed by the team:

- Python standard library: `http.server`, `sqlite3`, `threading`, `abc`, `unittest`, `urllib`, `json`, `csv`/`email` parsing.
- NumPy, Pandas, Matplotlib and Seaborn — the only third-party packages.
- No web framework, ORM, JavaScript framework or chart library. Pages are server-rendered
  HTML strings with one stylesheet (`noor/static/style.css`, the vintage theme). The only
  JavaScript is `noor/static/intro.js` (about 25 lines) for the landing-page intro; every page
  works without it.

## Layers

```
            Browser (HTML forms, PNG charts)          Scripts / other tools (JSON)
                       │                                         │
                       ▼                                         ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ noor/web/server.py   NoorHandler(BaseHTTPRequestHandler)                 │  presentation
  │   routes ─► pages.py (HTML)   api.py (JSON)   charts.py (PNG)   reports.py│
  └──────────────────────────────────────────────────────────────────────────┘
                       │  calls only
                       ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ noor/service.py   NoorService  (use cases: assess, alerts, plan,         │  business logic
  │                                 scenario, import, add/update)            │
  └──────────────────────────────────────────────────────────────────────────┘
        │ objects & DataFrames                         │ SQL
        ▼                                              ▼
  ┌───────────────────────────────┐        ┌────────────────────────────────┐
  │ analytics (pure functions /   │        │ noor/database.py  Database     │  persistence
  │ classes, no SQL, no HTTP)     │        │ noor/schema.sql   8 tables     │
  │ models.py   climate.py        │        │ noor/queries.py   SQL examples │
  │ risk.py     alerts.py         │        └────────────────────────────────┘
  │ allocation.py scenario.py     │                        │
  │ importer.py                   │                     SQLite file
  └───────────────────────────────┘
```

Rules the code follows:

- Pages and API functions never run SQL or maths themselves; they call `NoorService`.
- Analytics modules never import `database` or `web`. They take objects and DataFrames and
  return dicts, so the unit tests can call them directly.
- All SQL is in `database.py` and `queries.py`, always with `?` parameters.
- All numbers that change behaviour are in `settings.py`.

## Request flow (example: open `/risk/SPR-01`)

1. `NoorHandler.do_GET` parses the URL and calls `handle_safely`.
2. `handle_safely` makes sure the database exists (`prepare()`), opens a `Database`, wraps
   it in a `NoorService`, and catches errors (friendly page, no traceback).
3. `route_get` matches `/risk/([A-Za-z0-9_-]{2,20})` in `PAGE_ROUTES` → `pages.risk_detail`.
4. `risk_detail` calls `svc.assessment("SPR-01")`, which loads `Location` and `Resource`
   objects plus observation DataFrames and runs `RiskEngine.assess` for every ward.
5. The page builds HTML with `html.esc()` on every value; the dimension chart is an `<img>`
   pointing at `/chart/dimensions/SPR-01.png`, drawn by Matplotlib under `CHART_LOCK`.

## Concurrency

The local server is a `ThreadingHTTPServer` (one thread per connection, HTTP/1.1 keep-alive).

- Each request opens its own `sqlite3` connection.
- `Database.write_lock` (a class-level `threading.Lock`) serialises every write.
- `charts.CHART_LOCK` serialises Matplotlib, whose `pyplot` keeps global state.
- `server._setup_lock` makes sure the database is created and seeded once.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py                   # http://127.0.0.1:3060
```

Settings (all optional, see `.env.example`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `NOOR_DB_PATH` | `instance/noor.db` (local), `/tmp/noor.db` (Vercel) | SQLite file |
| `NOOR_PORT` | `3060` | Port for `run.py` |

There are no secrets: NOOR calls no paid API and needs no keys.

## Database lifecycle

- `Database.create_tables()` runs `schema.sql` (`CREATE TABLE IF NOT EXISTS`), so it is safe on
  every start.
- `NoorService.setup()` seeds only an empty database, then computes the first risk run,
  alerts and two saved plans.
- Changing the schema: edit `schema.sql`, then `python run.py --reset` to rebuild the demo
  database. (A project with real data would add `ALTER TABLE` steps instead; see
  [VIVA_NOTES.md](VIVA_NOTES.md#add-a-table-column).)

## Troubleshooting

**Downloads cut off or pages stalling when testing with `curl` on Windows.** Some antivirus
"web shields" (Avast on the development machine) inspect local HTTP traffic and can reset a
connection that closes straight after a large response. Python's own `python -m http.server`
showed the same failures on that machine, so it is not specific to NOOR. Browsers reuse
connections (keep-alive), which NOOR supports, and were not affected. If you see it, add an
exception for `127.0.0.1` in the antivirus or use a keep-alive client.
