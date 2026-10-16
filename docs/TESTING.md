# Testing

## Automated tests (unittest)

```bash
python -m unittest discover -s tests          # all
python -m unittest discover -s tests -v       # one line per test
python -m unittest tests/test_risk.py         # one file
```

Last full run on the development machine (Python 3.14.6, Windows 11): **150 tests, all passed,
about 27 seconds** (most of the time is the HTTP tests drawing charts).

| File | Tests | What it covers |
| --- | --- | --- |
| `test_models.py` | 20 | Property validation, private attributes, class attribute, composition (`Region`), abstract `Resource`, polymorphic `capacity()`/`describe()`, factory, service radius |
| `test_risk.py` | 38 | Heat index vs NWS chart values, NumPy summary statistics, normalisation boundaries, category boundaries (20/40/60/80 inclusive), weight validation, missing indicators not counted as zero, insufficient data, formula check, precautionary value, low-hazard cap, capacity effect, data age and confidence, capacity sharing by population |
| `test_alerts.py` | 19 | Every rule at and around its threshold, runs that ended before the as-of date, forecast days, synthetic note, engine aggregation |
| `test_allocation.py` | 11 | Demand formula, capacity never exceeded, never over-serving, service radius, risk-first vs population-first under scarcity, offline resources, unknown population, precautionary score, comparison |
| `test_scenario.py` | 12 | Parameter validation, budget/staff limits, no-change baseline, warming raises risk, new centres cut the cooling gap, water capacity, originals untouched |
| `test_importer.py` | 11 | Missing columns, empty/oversized/non-UTF-8 files, BOM and header case, each row-level error with its line number, forecast rows, injection text |
| `test_database.py` | 18 | 8 tables, foreign keys, CHECK constraints, unique codes, `?` parameters storing hostile text literally, alert status lifecycle, no duplicate alerts, cascade delete, resource change re-scores, every named SQL query, HAVING query, synthetic labelling, imported data kind, reproducible seed, demo gaps, close/destructor, shared lock |
| `test_open_meteo.py` | 4 | Response parsing into the import format (through the real import validator), URL, argument checks — no network needed |
| `test_server.py` | 17 | Real HTTP server on a background thread: every page, demo banner, 404 page, inline validation messages, security headers, static path traversal, API reads/errors/writes, form redirects, cross-site POST refused, multipart CSV upload, PNG charts, CSV provenance headers |

Each test that needs data builds an in-memory database (`Database(":memory:")`) or a temporary
file, so tests never touch `instance/noor.db`.

## End-to-end browser checks (headless)

Run during development with headless Chromium (Playwright), not part of the Python suite because
it needs Node.js:

NOOR targets desktop browsers only (1280 px and wider).

- 13 pages × 4 desktop windows (1280×800, 1366×768, 1440×900, 1920×1080): HTTP 200, exactly one
  `<h1>`, no horizontal page overflow, every chart image returns a PNG, no console errors, all 19
  dashboard links work.
- 16 workflow steps in a 1366×768 window: explorer filter shows missing days; invalid and valid
  what-if weights; precautionary value explained; run the warning engine, acknowledge and resolve
  an alert; take a cooling centre offline and see the ward's score rise (31.7 → 33.4); add a
  resource; save a plan; run and reset a scenario; import a CSV with 7 good rows and 1 bad row;
  download a report; keyboard Tab reaches the skip link first; no console errors.

## Bugs the tests found

- A location with too little data reported “medium” confidence; it is now always “low” when
  there is no score (`RiskEngine.assess`).
- The invalid-weights page answered with HTTP 400, which browsers log as a console error; the
  form now comes back with the reason (HTTP 200), same for invalid scenario parameters.
- A `style=` attribute broke the page's own Content-Security-Policy; replaced with a CSS class.
