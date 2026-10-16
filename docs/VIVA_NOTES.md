# Viva notes

Where each topic of the *Object Oriented Programming with Python Laboratory* syllabus appears
in NOOR, with the file and the function or class to open. Then: how to change things live.

## 1. Classes and objects

| Topic | Where | What to show |
| --- | --- | --- |
| Class with `__init__` | `noor/models.py` → `Location.__init__` | Every attribute is set through a validating property |
| Class vs instance attributes | `models.py` → `Location.created_count` (class) vs `self._code` (instance); `database.py` → `Database.write_lock` (class, shared) vs `self.conn` (per object) | `test_models.LocationTests.test_class_attribute_counts_instances`, `test_database.test_write_lock_is_shared` |
| `__del__` (destructor) | `noor/database.py` → `Database.__del__` calls `close()` | `test_database.test_close_and_destructor` |
| `__repr__`, `__len__` | `Location.__repr__`, `Region.__len__` | `len(region)` gives the number of wards |
| Static methods | `RiskEngine.check_weights`, `RiskEngine.dimension`, `Scenario.check` | Called without an object |

## 2. Encapsulation

| Topic | Where |
| --- | --- |
| `_protected` attributes | `Location._code`, `_name`, `_population`, `_area_km2`; `Region._locations`; `Scenario._params` |
| `__private` attribute | `Location.__shares` (name-mangled to `_Location__shares`), only reachable through `get_share()` / `set_share()` |
| `@property` getter and setter with validation | `Location.code`, `name`, `population`, `area_km2` (setters raise `ValidationError` for bad values); read-only properties `Location.density`, `Region.locations` (returns a copy), `Scenario.params`, `Scenario.affordable_centres` |

## 3. Aggregation vs composition

| Relationship | Where | Why |
| --- | --- | --- |
| Composition | `Region.add_location()` creates the `Location` objects and keeps them in `self._locations` | A ward does not exist outside its region |
| Aggregation | `AllocationPlanner.__init__` (allocation.py) receives existing `Location` and `Resource` objects | The planner only uses them; they live on after it |
| Aggregation | `NoorService.__init__` (service.py) receives a `Database` | The service does not create or close it |

## 4. Inheritance, method overriding, abstract classes, polymorphism

| Topic | Where |
| --- | --- |
| Abstract base class (`abc`) | `models.Resource(ABC)` with `@abstractmethod capacity()` and `describe()`; `alerts.AlertRule(ABC)` with `@abstractmethod check()` |
| Inheritance | `CoolingCentre`, `WaterPoint`, `MedicalUnit`, `ResponseTeam`, `OutreachTeam` inherit `Resource` (shared `__init__`, `status_factor()`, `serves()`); six rule classes inherit `AlertRule` (shared `confidence_note()`); `NoorHandler` inherits `BaseHTTPRequestHandler`; exceptions inherit `NoorError` |
| Method overriding | Each resource overrides `capacity()` (litres ÷ 4 for water, members × 6 for response teams …) and `describe()`; each rule overrides `check()`; `NoorHandler` overrides `do_GET`, `do_POST`, `log_message` |
| Polymorphism | `AllocationPlanner.run()` calls `res.capacity()` without knowing the type; `WarningEngine.run()` calls `rule.check(ctx)` on every rule; `models.make_resource()` is a factory picking the subclass |
| Cannot instantiate abstract class | `test_models.ResourceTests.test_abstract_class_cannot_be_created` |

## 5. Exception handling

| Topic | Where |
| --- | --- |
| Custom exceptions | `noor/exceptions.py`: `NoorError` → `ValidationError`, `NotFoundError`, `ConflictError` (each with an HTTP status) |
| Raising | `models._check_share`, `Location` setters, `RiskEngine.check_weights`, `Scenario.check`, `importer.read_upload` |
| Converting library errors | `importer.read_upload` turns `UnicodeDecodeError` / `pd.errors.ParserError` into `ValidationError`; `Database.execute` turns `sqlite3.IntegrityError` into `ConflictError` |
| try / except / finally | `web/server.py` → `NoorHandler.handle_safely`: `NoorError` → friendly message, any other `Exception` → logged + generic 500 page, `finally` closes the database |

## 6. Modules and packages

`noor/` is a package; `noor/web/` a sub-package. Relative imports (`from . import settings`,
`from ..service import NoorService`). `run.py` and `api/index.py` import the package.

## 7. Multithreading

| Topic | Where |
| --- | --- |
| Threads | `web/server.py` → `run()` uses `NoorHTTPServer` (a `ThreadingHTTPServer`): one thread per connection |
| `threading.Lock` | `Database.write_lock` (every INSERT/UPDATE/DELETE in `Database.execute` / `execute_many` runs `with Database.write_lock:`); `charts.CHART_LOCK` (Matplotlib is not thread-safe); `server._setup_lock` (seed the database only once) |
| Starting a thread | `tests/test_server.py` → `setUpClass` runs the server with `threading.Thread(target=..., daemon=True)` |

## 8. Collections

- **list**: `seed.WARDS`, `seed.RESOURCES`, `AllocationPlanner.run` → `assignments`
- **dict**: `settings.RISK_WEIGHTS`, `settings.DEMAND_RATES`, `models.RESOURCE_CLASSES` (type name → class)
- **tuple**: indicator specs `(low, high, weight)` in `settings.py`; `settings.CATEGORIES` as `(threshold, name)` pairs
- **set**: `importer.validate` (`bad_lines`), `NoorService.synthetic_codes()`, `known` location codes

## 9. NumPy

| Function | Where |
| --- | --- |
| arrays, `np.arange`, `np.sin`, `np.minimum` | `seed.season_curve()` |
| random numbers with a seed | `seed.build_weather()` → `np.random.default_rng(2026)`, `rng.normal`, `rng.random` |
| `np.clip` | `risk.normalise()` (min-max normalisation) |
| `np.average(..., weights=)` | `RiskEngine.dimension()` |
| `np.nanmax`, `np.sum`, boolean arrays | `climate.hazard_inputs()` |
| `np.mean`, `np.min`, `np.max`, `np.std`, boolean mask | `climate.summary_stats()` (shown on the Data explorer page) |

## 10. Pandas

| Function | Where |
| --- | --- |
| `read_csv` | `importer.read_upload()` |
| `to_csv` | `reports.to_csv()`; `scripts/fetch_open_meteo.py` |
| `read_sql_query` | `Database.dataframe()` |
| Boolean masking | `importer.validate()` → `flag(mask, ...)`; `climate.daily_window()` → `keep` mask |
| Indexing (`loc`, `set_index`, `reindex`) | `climate.daily_window()`, `climate.explorer_table()` (reindex to every day, so gaps appear) |
| `groupby` + aggregation | `climate.location_comparison()` (`agg` mean/max/count), `climate.monthly_means()`, `NoorService.observations_by_code()`; `pivot_table` in `charts.temperature_heatmap()` |
| Cleaning | `dropna` in `alerts.HeatIndexRule.check`; `fillna("missing")` in `climate.explorer_table()`; `drop_duplicates` in `climate.daily_window()`; `pd.to_numeric(errors="coerce")`, `pd.to_datetime(errors="coerce")` in `importer.validate()` |

## 11. Matplotlib and Seaborn (PNG)

All in `noor/charts.py`, returned as PNG bytes (`_png()` → `fig.savefig(..., format="png")`);
`scripts/export_charts.py` saves them as files.

| Chart | Function |
| --- | --- |
| Line | `trend_chart()` (Tmax, Tmin, heat index; missing days marked) |
| Bar | `risk_bars()` (horizontal), `allocation_chart()`, `scenario_chart()`, `dimension_chart()` |
| Histogram | `score_histogram()` |
| Heatmap (Seaborn) | `risk_map()` (schematic ward grid), `temperature_heatmap()` (wards × days) |

## 12. SQLite with `sqlite3`

| Topic | Where |
| --- | --- |
| CREATE TABLE with PRIMARY KEY and FOREIGN KEY, CHECK, UNIQUE | `noor/schema.sql` (8 tables) |
| Connect, `PRAGMA foreign_keys = ON`, `row_factory` | `Database.__init__` |
| Create | `Database.add_source`, `add_region`, `add_location`, `add_observations` (`executemany`), `add_resource`, `save_alert`, `save_plan` |
| Read | `Database.list_locations`, `get_location`, `list_resources`, `list_alerts`, `latest_assessments` |
| Update | `Database.update_resource`, `set_alert_status` |
| Delete | `Database.delete_resource` (allocations follow by `ON DELETE CASCADE`) |
| `?` parameters | every query; `test_database.test_parameters_store_text_literally` stores `x'); DROP TABLE locations; --` as plain text |
| JOIN, GROUP BY, HAVING, LEFT JOIN, sub-query | `noor/queries.py` (also on the Reports page) |

## 13. Unit testing

`tests/` — 150 `unittest` tests (`python -m unittest discover -s tests`). Classes inherit
`unittest.TestCase`, use `setUp` / `tearDown` / `setUpClass`, `assertEqual`, `assertRaises`,
`assertAlmostEqual`. See [TESTING.md](TESTING.md).

---

## How to change things live

Restart the server after editing a `.py` file (`Ctrl+C`, then `python run.py`). Risk is
recalculated on every start.

### Change a weight

1. Open `noor/settings.py`, find `RISK_WEIGHTS`.
2. For example make hazard count more: `"hazard": 0.50` and `"vulnerability": 0.15`
   (the four must still add up to 1.0 — `RiskEngine.check_weights` refuses otherwise).
3. Restart. The Dashboard, Risk page and Method page all show the new weights and scores.

Without editing code: the **Risk** page has a “Try different weights” form (not saved).

### Add or change a threshold

- A category boundary: in `settings.CATEGORIES` change `(60.0, "Severe")` to `(55.0, "Severe")`.
- A warning threshold: `settings.HOT_DAY_C = 38.0` or `settings.HOT_SPELL_WARNING_DAYS = 2`.
- A new rule: add a class to `noor/alerts.py` and list it in `WarningEngine.__init__`:

```python
class HumidHeatRule(AlertRule):
    """Advisory when today's humidity is above 60 % and Tmax is at least 38 C."""

    name = "humid_heat"

    def check(self, ctx):
        """Look only at the as-of day."""
        today = ctx["daily"].loc[pd.Timestamp(ctx["as_of"])]
        if today["humidity"] >= 60 and today["t_max"] >= 38:
            return Alert(self.name, "advisory", f"{ctx['name']}: humid heat today.",
                         today["humidity"], 60, ctx["as_of"],
                         ["Advise rest breaks in shade for outdoor workers."], self.confidence_note(ctx))
        return None
```

Then press **Run the warning engine now** on the Alerts page.

### Add a table column

Example: a contact phone number for each resource.

1. `noor/schema.sql` — in `CREATE TABLE resources` add `phone TEXT,`.
2. `noor/database.py` — in `add_resource` add `phone` to the column list, one more `?`, and the value.
3. `noor/models.py` — give `Resource.__init__` a `phone=None` parameter and store `self.phone`.
4. Rebuild the demo database: `python run.py --reset`.
   (With real data you would not reset; you would run once:
   `ALTER TABLE resources ADD COLUMN phone TEXT;` in `sqlite3 instance/noor.db`.)
5. Show it: add a column in `pages.resources` (the `rows.append([...])` list and the header list).

### Run a SQL query live

Open **Reports → SQL summaries**, pick a query, or open `instance/noor.db` with any SQLite
tool and paste a query from `noor/queries.py`. To add one, add an entry to the `QUERIES`
dict; it appears in the drop-down automatically.
