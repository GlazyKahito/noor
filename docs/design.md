# NOOR design record (Phase 1)

This is the plan written before any code. Later documents (architecture, methodology,
data dictionary, API) describe what was actually built; where they differ, they win.

## Inspection

The NOOR directory was empty when work started. No prior NOOR work existed to preserve.
Nothing outside this directory was used.

## Stack decision

| Need | Choice | Why |
| --- | --- | --- |
| Web + API | Flask 3 (WSGI) | One small dependency; runs locally and as a Vercel Python function without changes. |
| Analytics | Python standard library (`statistics`, `math`, `csv`) | The data volume is small (hundreds to a few thousand daily rows). Pandas/NumPy would add ~100 MB to a serverless bundle for no analytical gain. |
| Database | SQLite (stdlib `sqlite3`) | Relational, constraints and foreign keys, zero setup. |
| Frontend | Jinja templates + vanilla JS modules + hand-built SVG charts | No build step, no CDN, works offline, small payload. |
| Tests | pytest; headless Playwright smoke script for end-to-end | Unit/integration in Python; browser checks optional. |

Hosting constraint (Vercel): the function filesystem is read-only except `/tmp`, instances are
short-lived and not shared. NOOR therefore creates its SQLite database in `/tmp` on a cold
start and fills it from the deterministic seed. Writes on the hosted demo are per-instance
and temporary. Local mode keeps a persistent database in `instance/noor.db`.

## Architecture

```
 Browser ── pages (Jinja) ──┐            ┌── JSON API (/api/*) ── fetch() from page JS
                            ▼            ▼
                     noor.web          noor.api            (presentation / HTTP)
                            \          /
                             noor.services                  (use cases: run assessment,
                                  |                          generate alerts, plan, scenario)
              ┌───────────────────┼────────────────────┐
        noor.analytics       noor.repository        noor.reports
   (pure functions: heat      (all SQL, parameterised,  (CSV + printable HTML with
    index, normalisation,      transactions)             provenance + limitations)
    risk, warnings,                 |
    allocation, scenarios,     noor.db (connection, migrations, seed)
    CSV validation)                 |
                                 SQLite
        noor.sources.open_meteo (optional fetch of model-derived weather, CLI only)
```

Analytics never touch the database or Flask; they take plain data and config and return
plain results, so they are unit-testable.

## Data model (planned)

- `data_sources` — every number points at one; `kind` is `measured`, `model_derived`,
  `estimated` or `synthetic`.
- `regions`, `locations` (population and area nullable; `is_demo` flag; schematic grid
  position for demonstration regions; optional lat/lon).
- `observations` (daily Tmax, Tmin, mean RH; `period_type` observed/forecast; unique per
  location/date/source/period; range checks).
- `import_batches` (provenance of uploaded CSV files).
- `indicators` (definitions) and `location_indicators` (values, source, date).
- `resources` (cooling centres, water points, medical units, response teams, outreach teams).
- `risk_runs` and `risk_assessments` (one row per location per run; dimension scores,
  completeness, confidence, explanation JSON).
- `alerts` (rule, severity, triggers, period, status lifecycle).
- `allocation_plans` and `allocation_items`.
- `scenario_runs` (parameters and before/after results).

## Methods (planned)

- Heat index: NOAA/NWS Rothfusz regression with the published adjustments.
- Risk: four dimensions kept separate — Hazard, Exposure, Vulnerability, Lack of response
  capacity — each 0–1 from min–max normalised sub-indicators with configurable bounds;
  combined by a weighted geometric mean so that strong capacity cannot fully cancel an
  extreme hazard and no hazard means no heat risk. Missing data is never read as zero:
  weights are renormalised over available indicators, and if coverage is too low a
  precautionary value is used and confidence drops.
- Warnings: deterministic rule table (heat index, hot spell, warm nights, risk category,
  capacity gap, stale data), evaluated by a pure function; persistence separate.
- Allocation: baseline proportional split, plus a documented greedy priority heuristic.
- Scenarios: perturb inputs (temperature, duration, capacities, budget, staff), rerun the
  same risk and allocation code, compare.

## External data

- Open-Meteo (open-meteo.com) archive and forecast APIs were reachable during design
  (checked with a 3-day request). Data is model output (reanalysis / NWP), licensed CC BY 4.0,
  free for non-commercial use. NOOR labels it `model_derived`, never `measured`.
- IMD station data is not openly available through a stable public API, so NOOR does not
  claim to use it. Users can import official data they hold through the CSV importer.
- Population, demographic and facility statistics: no reliable openly licensed source was
  connected. The demonstration region and every number in it are synthetic and labelled so.
