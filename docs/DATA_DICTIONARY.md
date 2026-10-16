# Database schema and data dictionary

SQLite, created from `noor/schema.sql`. 8 tables, foreign keys switched on for every
connection (`PRAGMA foreign_keys = ON`). All queries use `?` parameters.

```
data_sources ─┬─< locations >── regions
              ├─< observations >── locations
              └─< resources >── locations
locations ─┬─< risk_assessments
           ├─< alerts
           └─< allocations >── resources
```

## data_sources — where each number came from

| Column | Type | Rules | Meaning |
| --- | --- | --- | --- |
| id | INTEGER | PK | |
| name | TEXT | NOT NULL, UNIQUE | e.g. “NOOR synthetic demo data” |
| kind | TEXT | `measured` / `model_derived` / `estimated` / `synthetic` | How far to trust it |
| provider | TEXT | NOT NULL | Who produced it |
| licence | TEXT | NOT NULL | Terms of use (“unknown” is allowed but must be said) |
| notes | TEXT | | Coverage, retrieval method, limitations |

## regions

| Column | Type | Rules | Meaning |
| --- | --- | --- | --- |
| id | INTEGER | PK | |
| name | TEXT | NOT NULL, UNIQUE | District or city |
| is_demo | INTEGER | 0 or 1 | 1 = synthetic demonstration region |
| description | TEXT | | |

## locations — wards

| Column | Type | Rules | Meaning |
| --- | --- | --- | --- |
| id | INTEGER | PK | |
| code | TEXT | NOT NULL, UNIQUE | e.g. SPR-01 |
| name | TEXT | NOT NULL | |
| region_id | INTEGER | FK → regions | |
| grid_x, grid_y | REAL | | Position on the schematic grid, km (not real coordinates) |
| population | INTEGER | NULL or ≥ 0 | NULL = unknown (never guessed) |
| area_km2 | REAL | NULL or > 0 | |
| elderly_share | REAL | NULL or 0–1 | Residents aged 65+ |
| children_share | REAL | NULL or 0–1 | Children under 5 |
| outdoor_worker_share | REAL | NULL or 0–1 | Main work outdoors |
| poor_housing_share | REAL | NULL or 0–1 | Informal or heat-trapping housing |
| low_income_share | REAL | NULL or 0–1 | Low-income households |
| piped_water_share | REAL | NULL or 0–1 | Households with piped water (a capacity input) |
| source_id | INTEGER | FK → data_sources | Source of population and shares |

## observations — one row per location per day

| Column | Type | Rules | Meaning |
| --- | --- | --- | --- |
| id | INTEGER | PK | |
| location_id | INTEGER | FK → locations, ON DELETE CASCADE | |
| obs_date | TEXT | NOT NULL, `YYYY-MM-DD` | |
| is_forecast | INTEGER | 0 or 1 | 1 = forecast day |
| t_max | REAL | NULL or −40..60 | Daily maximum temperature, °C |
| t_min | REAL | NULL or −50..50 | Daily minimum temperature, °C |
| humidity | REAL | NULL or 0..100 | Daily mean relative humidity, % |
| source_id | INTEGER | FK → data_sources | |
| | | UNIQUE (location_id, obs_date, is_forecast) | A later import replaces the row and its source |

Index: `idx_obs_location_date (location_id, obs_date)`.

## resources

| Column | Type | Rules | Meaning |
| --- | --- | --- | --- |
| id | INTEGER | PK | |
| code | TEXT | NOT NULL, UNIQUE | e.g. CC-01 |
| name | TEXT | NOT NULL | |
| type | TEXT | one of 5 types | cooling_centre, water_point, medical_unit, response_team, outreach_team |
| location_id | INTEGER | FK → locations | Where it is |
| amount | REAL | > 0 | Unit depends on type: places/day, litres/day, patients/day, members, volunteers |
| status | TEXT | available / limited / offline | Counts as 100 % / 50 % / 0 % |
| radius_km | REAL | > 0 | Service radius |
| staff | INTEGER | ≥ 0 | |
| daily_cost | INTEGER | ≥ 0 | INR per day |
| source_id | INTEGER | FK → data_sources | |

## risk_assessments — output of the risk engine

| Column | Type | Rules | Meaning |
| --- | --- | --- | --- |
| id | INTEGER | PK | Newest row per location = current assessment |
| location_id | INTEGER | FK → locations, CASCADE | |
| assessed_at | TEXT | NOT NULL | UTC time of calculation |
| as_of_date | TEXT | NOT NULL | Data date the assessment describes |
| hazard, exposure, vulnerability, capacity | REAL | NULL = could not be computed | Dimension values 0–1 |
| score | REAL | NULL or 0–100 | NULL = insufficient data |
| category | TEXT | NOT NULL | Low … Extreme, or Insufficient data |
| confidence | TEXT | high / medium / low | |
| reasons | TEXT | NOT NULL | Explanation lines joined with “ \| ” |

## alerts

| Column | Type | Rules | Meaning |
| --- | --- | --- | --- |
| id | INTEGER | PK | |
| location_id | INTEGER | FK → locations, CASCADE | |
| rule | TEXT | NOT NULL | heat_index, hot_spell, warm_nights, risk_category, cooling_gap, stale_data |
| severity | TEXT | info / advisory / warning / emergency | |
| message | TEXT | NOT NULL | |
| trigger_value, threshold | REAL | | What was measured vs the limit |
| period | TEXT | NOT NULL | Dates the alert covers |
| actions | TEXT | NOT NULL | Recommended actions joined with “ \| ” |
| confidence | TEXT | NOT NULL | Data confidence + synthetic note + disclaimer |
| issued_at | TEXT | NOT NULL | UTC |
| status | TEXT | active / acknowledged / resolved | Moves forward only (checked in `Database.set_alert_status`) |
| | | UNIQUE (location_id, rule, period) | No duplicates when the engine runs again |

## allocations — saved plans

| Column | Type | Rules | Meaning |
| --- | --- | --- | --- |
| id | INTEGER | PK | |
| plan_name | TEXT | NOT NULL | |
| strategy | TEXT | risk_first / population_first | |
| resource_id | INTEGER | FK → resources, CASCADE | |
| location_id | INTEGER | FK → locations, CASCADE | |
| people_per_day | REAL | > 0 | Capacity assigned |
| created_at | TEXT | NOT NULL | UTC |

## Useful SQL

`noor/queries.py` holds readable examples (also runnable on the Reports page and at
`/api/queries/<name>`): risk by region (JOIN + GROUP BY), locations with many hot days
(GROUP BY + HAVING), inventory by type and status, monthly climate (strftime), alerts per
location (LEFT JOIN), rows per source (provenance), and missing days per location (HAVING).
