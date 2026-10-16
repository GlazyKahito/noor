# JSON API

Base URL: `http://127.0.0.1:3060` locally, or the deployed URL. Implemented in
`noor/web/api.py`, routed in `noor/web/server.py` (`API_GET`, `API_POST`).

## Conventions

- Success: `200` with `{"ok": true, "data": ...}`.
- Failure: `{"ok": false, "error": {"message": "...", "details": [...]}}` with
  `400` (invalid input), `404` (unknown thing or endpoint), `409` (conflict: duplicate code,
  alert already resolved) or `500` (unexpected; logged on the server, no stack trace returned).
- POST bodies must be JSON with `Content-Type: application/json`.
- Dates are `YYYY-MM-DD`. Temperatures °C, humidity %.
- No authentication (see “Security” below).

## Read endpoints (GET)

| Endpoint | Returns |
| --- | --- |
| `/api/health` | `{"status": "ok", "version", "locations"}` |
| `/api/status` | Table row counts, latest observation date, days since, data kinds in use, `synthetic_only`, sources |
| `/api/config` | Weights, indicator bounds, categories, heat-index bands, demand rates, strategies |
| `/api/locations` | All locations with region and source kind |
| `/api/locations/<code>` | One location (404 if unknown) |
| `/api/observations?location=&start=&end=` | Up to 5,000 rows, `truncated` flag |
| `/api/risk?category=` | Latest stored assessment per location |
| `/api/risk/<code>` | Full explained assessment: dimensions, indicator details, reasons, daily window |
| `/api/alerts?status=&severity=` | Alerts, most severe first |
| `/api/resources` | Inventory with `people_per_day` from each resource class |
| `/api/plans?strategy=risk_first\|population_first` | Allocation plan (not saved) |
| `/api/plans/compare` | Population-first (A) vs risk-first (B) |
| `/api/scenario?temperature_increase=&extra_hot_days=&new_cooling_centres=&water_capacity_pct=&medical_capacity_pct=&budget_per_day=&staff_available=` | Scenario comparison |
| `/api/queries/<name>` | One of the SQL summaries in `noor/queries.py` (title, SQL, rows) |

## Write endpoints (POST, JSON body)

| Endpoint | Body | Effect |
| --- | --- | --- |
| `/api/risk/weights` | `{"weights": {"hazard": 0.5, "exposure": 0.2, "vulnerability": 0.2, "lack_of_capacity": 0.1}}` | What-if ranking with these weights (not saved) |
| `/api/alerts/run` | `{}` | Run the warning engine; returns `new_alerts`, `rules_fired` |
| `/api/alerts/<id>/status` | `{"status": "acknowledged"}` or `"resolved"` | Forward-only status change (409 otherwise) |
| `/api/resources` | `{"code", "name", "type", "location_code", "amount", "radius_km", "status"?, "staff"?, "daily_cost"?, "kind"?}` | Add a resource, re-run risk (409 if the code exists) |
| `/api/resources/<code>` | `{"status": "limited", "amount": 300}` | Update, re-run risk |
| `/api/scenario` | Same keys as the GET query | Scenario comparison |

## Examples

```bash
curl http://127.0.0.1:3060/api/health
# {"ok": true, "data": {"status": "ok", "version": "1.0.0", "locations": 16}}

curl "http://127.0.0.1:3060/api/risk?category=Severe"

curl http://127.0.0.1:3060/api/risk/SPR-16
# ... "vulnerability": null, "imputed": ["vulnerability"],
#     "reasons": ["Score 61.7 = Severe.", ..., "No vulnerability data: used the precautionary value 0.5, not zero.", ...]

curl "http://127.0.0.1:3060/api/scenario?temperature_increase=2&new_cooling_centres=5"

curl -X POST http://127.0.0.1:3060/api/alerts/run -H "Content-Type: application/json" -d "{}"

curl -X POST http://127.0.0.1:3060/api/resources/CC-02 -H "Content-Type: application/json" \
     -d "{\"status\": \"offline\", \"amount\": 500}"

curl "http://127.0.0.1:3060/api/scenario?temperature_increase=50"
# 400 {"ok": false, "error": {"message": "temperature_increase must be between 0.0 and 6.0", "details": []}}
```

Python (standard library only):

```python
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:3060/api/plans/compare") as r:
    print(json.load(r)["data"]["risk_weighted_b"])
```

## Other machine-readable outputs

- Charts (PNG): `/chart/risk-map.png?layer=score|hazard|exposure|vulnerability|capacity`,
  `/chart/risk-bars.png`, `/chart/histogram.png`, `/chart/heatmap.png`,
  `/chart/trend.png?location=&start=&end=`, `/chart/allocation.png?strategy=`,
  `/chart/scenario.png?<scenario params>`, `/chart/dimensions/<code>.png`.
- CSV (with `#` provenance header lines): `/export/risk.csv`, `/export/vulnerability.csv`,
  `/export/alerts.csv`, `/export/allocation.csv?strategy=`, `/export/scenario.csv?<params>`,
  `/export/observations.csv?location=&start=&end=`, `/export/template.csv`.
  Text cells starting with `= + - @` are prefixed with `'` so spreadsheets do not run them.

## Security

- Every input is validated (types, ranges, known codes, URL patterns); SQL uses `?` parameters.
- Responses carry `Content-Security-Policy` (no scripts), `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`.
- HTML form posts from another site are refused (`Origin` must match `Host`). JSON POSTs need
  `Content-Type: application/json`.
- Request bodies are limited to 2.5 MB; uploads to 2 MB / 20,000 rows; observation reads to 5,000 rows.
- Logs record method, path (no query string) and status only.
- **No authentication.** Put NOOR behind a login (or a private network) before using real data.
