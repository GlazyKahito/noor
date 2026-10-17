# Testing

## Automated tests (unittest)

```bash
python -m unittest discover -s tests          # all
python -m unittest discover -s tests -v       # one line per test
python -m unittest tests/test_risk.py         # one file
```

Last full run on the development machine (Python 3.14.6, Tk 8.6, Windows 11, numpy 2.5.4,
pandas 3.0.6, matplotlib 3.11.2): **153 tests, all passed, about 42 seconds.**

| File | Tests | What it covers |
| --- | --- | --- |
| `test_models.py` | 20 | Property validation, private attributes, class attribute, composition (`Region`), abstract `Resource`, polymorphic `capacity()`/`describe()`, factory, service radius |
| `test_risk.py` | 38 | Heat index vs NWS chart values, NumPy summary statistics, normalisation boundaries, category boundaries (20/40/60/80 inclusive), weight validation, missing indicators not counted as zero, insufficient data, formula check, precautionary value, low-hazard cap, capacity effect, data age and confidence, capacity sharing by population |
| `test_alerts.py` | 19 | Every rule at and around its threshold, runs that ended before the as-of date, forecast days, synthetic note, recommended actions, engine aggregation |
| `test_allocation.py` | 11 | Demand formula, capacity never exceeded, never over-serving, service radius, risk-first vs population-first under scarcity, offline resources, unknown population, precautionary score, comparison |
| `test_scenario.py` | 12 | Parameter validation, budget/staff limits, no-change baseline, warming raises risk, new centres cut the cooling gap, water capacity, originals untouched |
| `test_importer.py` | 11 | Missing columns, empty/oversized/non-UTF-8 files, BOM and header case, each row-level error with its line number, forecast rows, injection text |
| `test_database.py` | 21 | 8 tables, foreign keys, CHECK constraints, unique codes, `?` parameters storing hostile text literally, alert status lifecycle, no duplicate alerts, cascade delete, resource change re-scores, resource reassignment and deletion through the service, every named SQL query, HAVING query, synthetic labelling, imported data kind, reproducible seed, demo gaps, close/destructor, shared lock |
| `test_charts.py` | 4 | Every chart returns a Matplotlib `Figure` with axes; empty data gives a message, not an error; category counts match the assessments; PNG export |
| `test_open_meteo.py` | 4 | Response parsing into the import format (through the real import validator), URL, argument checks; no network needed |
| `test_gui.py` | 13 | The real `NoorApp` window (created hidden) with a temporary database: start-up seeds the database; every screen opens with no error; Overview numbers equal the database; observation filters and a rejected date; CSV check and import (one good row saved, one bad row listed); exports; risk detail and invalid/valid what-if weights; acknowledge and resolve saved, never backwards; edit, reassign, add (and reject a bad code), delete a resource; save and export a plan; Scenario Lab runs the real calculation on the background thread and shows a bad setting as a message instead of crashing; every report and chart export; SQL query with a bad and a good parameter; add a location and reject a share above 1 |

Tests that need data build an in-memory database (`Database(":memory:")`) or a temporary
file, so they never touch `instance/noor.db`. The GUI tests replace message boxes with a
recorder so nothing waits for a click, and are skipped automatically where Tk cannot open a
window.

## Visual check

During development every screen and tab was captured at 1400 × 860 from the running app,
with the window made invisible and click-through, and checked by eye. Problems found and
fixed this way:

- Large numbers and titles used the body font, because an `option_add("*Font")` line
  overrode the ttk styles. The line was removed.
- The right-hand detail panels (Risk Assessment, Alerts, Resource Allocation) were pushed
  past the window edge. `widgets.split_panes` now places the divider at a fixed share of
  the width.
- Long reasons in the risk detail panel were cut off; they now wrap to the panel width.

## Bugs the tests found

- A location with too little data reported "medium" confidence; it is now always "low" when
  there is no score (`RiskEngine.assess`).
- One GUI test depended on test order (another test had added a location); it now counts only
  the demo locations.
- Old chart images were freed by Python's garbage collector on the background thread, which
  Tk does not allow; `ChartPanel.show` now frees the old chart on the main thread.
