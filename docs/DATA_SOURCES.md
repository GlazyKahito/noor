# Data sources and limitations

## 1. NOOR synthetic demonstration data (bundled, used by default)

| | |
| --- | --- |
| Source | `noor/seed.py` in this repository |
| Kind | `synthetic` |
| Retrieval | Generated on first start with NumPy (`default_rng(2026)`), so every install gets identical data |
| Coverage | Fictional district “Saptapur”: 16 wards on a 4 × 4 schematic grid, 3 km apart |
| Time range | 2026-03-01 to 2026-06-04 observed, plus 3 forecast days (to 2026-06-07) |
| Variables and units | Daily Tmax and Tmin (°C), daily mean relative humidity (%); ward population, area (km²) and six shares (0–1); 25 resources |
| Update frequency | None (static) |
| Missing data | About 2 % of days dropped at random before late May; Lake View (SPR-09) stops 4 days early; Mill Lines (SPR-04) misses 2 June; Airport Road (SPR-15) has no population; Outer Villages (SPR-16) has no vulnerability shares. These are deliberate, to demonstrate missing-data handling |
| Licence | Generated for this project; free to reuse |
| Limitations | **Not real.** Temperatures follow a smooth pre-monsoon warming curve plus a heat event peaking on 3 June, with ward offsets (built-up wards hotter, green and lake-side wards cooler) and random noise. The shapes are plausible for inland India but no value is a measurement, census figure or official statistic |

## 2. Open-Meteo (optional, real model-derived weather)

| | |
| --- | --- |
| Source | Open-Meteo historical weather API, `https://archive-api.open-meteo.com/v1/archive` |
| Kind | `model_derived` — gridded reanalysis model output, not weather-station measurements |
| Retrieval | `scripts/fetch_open_meteo.py CODE LAT LON START END` writes a CSV; you then import it on the Data page. Verified reachable on 2026-10-16 with a 3-day request for Ahmedabad (23.03 N, 72.58 E) |
| Coverage | Global grid; any past date range up to a year per request |
| Variables | `temperature_2m_max`, `temperature_2m_min` (°C), `relative_humidity_2m_mean` (%), daily, Asia/Kolkata time zone |
| Licence | CC BY 4.0, free for non-commercial use; credit “Weather data by Open-Meteo.com” |
| Limitations | A grid cell, not a street; values are smoothed; the app is not connected to it live |

## 3. Your own data (CSV import)

The Data page accepts `location_code,date,t_max,t_min,humidity[,is_forecast]`. You must name
the source, choose its kind (measured, model-derived, estimated, synthetic) and give its licence
(“unknown” is allowed, but must be written). Each upload becomes a new `data_sources` row, and
every imported observation points at it.

Validation (see `noor/importer.py`): UTF-8 only; ≤ 2 MB and ≤ 20,000 rows; known location codes;
`YYYY-MM-DD` dates; observed dates not in the future; forecast dates ≤ 16 days ahead; numeric
ranges (Tmax −40..60, Tmin −50..50, humidity 0..100); not all values empty; Tmax ≥ Tmin; no
duplicate rows. Bad rows are rejected with their line number; good rows are kept.

## Sources considered and not used

- **India Meteorological Department (IMD)** station observations and heat-wave warnings: no
  stable open API was available for NOOR to rely on, so NOOR does not claim to use IMD data.
  Users with access to IMD data can import it as CSV with kind `measured`. NOOR does not quote
  IMD's heat-wave criteria; its own thresholds are labelled as NOOR defaults.
- **Census population and demographic data**: not connected. Ward-level vulnerability shares in
  the demo are synthetic.

## What NOOR never does

- It does not invent live data or claim a connection it does not have.
- It does not present synthetic numbers as measurements: the banner, the data kind column and
  every CSV header say what the data is.
- It does not report accuracy figures (none can be computed without real outcome data).
- It does not send notifications.
