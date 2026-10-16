"""Synthetic demonstration data (reproducible: fixed NumPy random seed).

Everything here is invented and stored under the data source "NOOR synthetic demo data"
with kind = 'synthetic'. Saptapur is a fictional district on a schematic 4 x 4 grid of wards
3 km apart. No value is a real measurement or an official statistic.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .models import Region, make_resource

SEED = 2026
START = date(2026, 3, 1)
AS_OF = date(2026, 6, 4)   # last observed day in the demo
FORECAST_DAYS = 3
SPACING_KM = 3.0
REGION_NAME = "Saptapur (synthetic demo district)"
SOURCE_NAME = "NOOR synthetic demo data"

# code, name, (col,row), population, area km2, heat-island offset C (green/lake wards are cooler), base humidity %, day-night range C,
# shares: elderly, children, outdoor workers, poor housing, low income, piped water (None = unknown)
WARDS = [
    ("SPR-01", "Old Market", (0, 0), 92000, 3.1, 1.8, 34, 11.5, (0.09, 0.09, 0.22, 0.38, 0.33, 0.71)),
    ("SPR-02", "Fort Ward", (1, 0), 64000, 3.8, 0.2, 33, 12.0, (0.12, 0.07, 0.12, 0.20, 0.22, 0.83)),
    ("SPR-03", "Rail Colony", (2, 0), 71000, 4.4, 1.0, 32, 12.5, (0.07, 0.10, 0.25, 0.41, 0.36, 0.66)),
    ("SPR-04", "Mill Lines", (3, 0), 83000, 3.6, 1.6, 31, 12.0, (0.06, 0.12, 0.33, 0.55, 0.47, 0.52)),
    ("SPR-05", "Riverside", (0, 1), 58000, 5.2, -1.2, 56, 9.5, (0.08, 0.11, 0.27, 0.47, 0.42, 0.58)),
    ("SPR-06", "Civil Lines", (1, 1), 41000, 6.0, -2.4, 35, 13.0, (0.13, 0.05, 0.06, 0.05, 0.08, 0.97)),
    ("SPR-07", "Bus Stand", (2, 1), 77000, 3.2, 1.4, 33, 12.0, (0.06, 0.09, 0.29, 0.31, 0.30, 0.74)),
    ("SPR-08", "Industrial Estate", (3, 1), 49000, 7.5, 2.2, 29, 13.0, (0.04, 0.08, 0.34, 0.44, 0.39, 0.61)),
    ("SPR-09", "Lake View", (0, 2), 52000, 6.4, -2.2, 44, 11.0, (0.11, 0.07, 0.10, 0.12, 0.15, 0.90)),
    ("SPR-10", "University Area", (1, 2), 66000, 5.5, -1.6, 34, 12.5, (0.05, 0.06, 0.08, 0.10, 0.18, 0.92)),
    ("SPR-11", "New Township", (2, 2), 104000, 8.1, 0.6, 32, 13.0, (0.07, 0.10, 0.15, 0.18, 0.21, 0.88)),
    ("SPR-12", "Brick Kilns", (3, 2), 38000, 9.6, 1.9, 27, 14.0, (0.05, 0.13, 0.31, 0.58, 0.49, 0.38)),
    ("SPR-13", "Garden Colony", (0, 3), 47000, 6.9, -2.6, 38, 12.5, (0.14, 0.06, 0.07, 0.06, 0.09, 0.95)),
    ("SPR-14", "Canal Road", (1, 3), 69000, 5.9, 0.7, 41, 11.5, (0.09, 0.10, 0.24, 0.36, 0.34, 0.69)),
    # Population unknown on purpose: shows how NOOR handles missing exposure data.
    ("SPR-15", "Airport Road", (2, 3), None, 11.2, 0.9, 30, 13.5, (0.06, 0.08, 0.19, 0.22, 0.24, 0.80)),
    # No vulnerability survey on purpose: shows the precautionary value instead of zero.
    ("SPR-16", "Outer Villages", (3, 3), 56000, 24.0, 1.3, 28, 14.5, (None, None, None, None, None, 0.44)),
]
STALE_WARD = "SPR-09"            # its observations stop 4 days before AS_OF
GAP_WARD, GAP_DAY = "SPR-04", date(2026, 6, 2)   # one missing day inside the window

# code, name, type, ward, amount (unit depends on type), status, radius km, staff, daily cost INR
RESOURCES = [
    ("CC-01", "Old Market community hall", "cooling_centre", "SPR-01", 300, "available", 3.0, 4, 12000),
    ("CC-02", "Civil Lines town hall", "cooling_centre", "SPR-06", 500, "available", 3.5, 6, 18000),
    ("CC-03", "University sports complex", "cooling_centre", "SPR-10", 400, "available", 3.0, 5, 15000),
    ("CC-04", "New Township school", "cooling_centre", "SPR-11", 350, "limited", 3.0, 3, 9000),
    ("CC-05", "Rail Colony institute", "cooling_centre", "SPR-03", 250, "available", 3.0, 3, 9000),
    ("CC-06", "Garden Colony library", "cooling_centre", "SPR-13", 300, "available", 3.0, 3, 10000),
    ("CC-07", "Industrial Estate canteen", "cooling_centre", "SPR-08", 200, "offline", 3.0, 2, 7000),
    ("WP-01", "Old Market water kiosk", "water_point", "SPR-01", 16000, "available", 2.5, 2, 3000),
    ("WP-02", "Bus Stand tanker point", "water_point", "SPR-07", 20000, "available", 3.0, 3, 5000),
    ("WP-03", "Riverside handpumps", "water_point", "SPR-05", 10000, "limited", 2.0, 1, 1500),
    ("WP-04", "Mill Lines water kiosk", "water_point", "SPR-04", 12000, "available", 2.5, 2, 3000),
    ("WP-05", "New Township tanker point", "water_point", "SPR-11", 18000, "available", 3.0, 3, 5000),
    ("WP-06", "Canal Road kiosk", "water_point", "SPR-14", 12000, "available", 2.5, 2, 3000),
    ("WP-07", "Brick Kilns tanker point", "water_point", "SPR-12", 8000, "available", 3.5, 2, 4000),
    ("WP-08", "Fort Ward kiosk", "water_point", "SPR-02", 10000, "available", 2.5, 2, 2500),
    ("MU-01", "Civil Lines dispensary unit", "medical_unit", "SPR-06", 120, "available", 5.0, 6, 25000),
    ("MU-02", "Fort Ward mobile clinic", "medical_unit", "SPR-02", 60, "available", 5.0, 4, 14000),
    ("MU-03", "New Township health post", "medical_unit", "SPR-11", 80, "available", 5.0, 4, 16000),
    ("MU-04", "Canal Road mobile clinic", "medical_unit", "SPR-14", 50, "limited", 4.5, 3, 11000),
    ("RT-01", "Central response team", "response_team", "SPR-07", 10, "available", 8.0, 10, 20000),
    ("RT-02", "North response team", "response_team", "SPR-02", 8, "available", 7.0, 8, 15000),
    ("RT-03", "South response team", "response_team", "SPR-14", 8, "limited", 7.0, 8, 15000),
    ("OT-01", "Ward volunteers north", "outreach_team", "SPR-03", 12, "available", 4.0, 12, 6000),
    ("OT-02", "Ward volunteers centre", "outreach_team", "SPR-10", 15, "available", 4.0, 15, 7000),
    ("OT-03", "Ward volunteers south", "outreach_team", "SPR-14", 10, "available", 4.0, 10, 5000),
]
SHARE_NAMES = ("elderly_share", "children_share", "outdoor_worker_share", "poor_housing_share",
               "low_income_share", "piped_water_share")


def build_region():
    """Create the Region object with its 16 Location objects (composition)."""
    region = Region(REGION_NAME, is_demo=True)
    for code, name, (col, row), pop, area, *_rest, shares in WARDS:
        region.add_location(code, name, population=pop, area_km2=area, grid_x=col * SPACING_KM,
                            grid_y=row * SPACING_KM, **dict(zip(SHARE_NAMES, shares)))
    return region


def build_resources():
    """Create the 25 Resource objects (each the right subclass)."""
    return [make_resource(rtype, code=code, name=name, location_code=ward, amount=amount, status=status,
                          radius_km=radius, staff=staff, daily_cost=cost)
            for code, name, rtype, ward, amount, status, radius, staff, cost in RESOURCES]


def season_curve(days):
    """Base maximum temperature for each day: ~32 C in March rising to ~40 C in late May,
    plus a heat event that peaks on 3 June."""
    index = np.arange(len(days))
    base = 32.0 + 8.0 * np.sin(np.minimum(index, 86) / 86 * np.pi / 2)
    event = np.zeros(len(days))
    for i, d in enumerate(days):
        k = (d - date(2026, 5, 27)).days
        if 0 <= k <= 7:
            event[i] = 3.2 * k / 7                    # build-up
        elif k > 7:
            event[i] = max(0.0, 3.2 - 0.9 * (k - 7))  # easing after the peak
    return base + event


def build_weather():
    """DataFrame of daily synthetic weather for every ward (observed days + forecast days)."""
    rng = np.random.default_rng(SEED)
    days = [START + timedelta(days=i) for i in range((AS_OF - START).days + 1 + FORECAST_DAYS)]
    base = season_curve(days)
    progress = np.minimum(np.arange(len(days)), 86) / 86
    frames = []
    for code, _name, _grid, _pop, _area, heat_island, humidity_base, day_range, _shares in WARDS:
        t_max = base + heat_island + rng.normal(0, 1.0, len(days))
        # pre-monsoon air dries out as the season heats up
        humidity = np.clip(humidity_base + 4 - 16 * progress + rng.normal(0, 3, len(days)), 8, 95)
        t_min = t_max - day_range + (humidity - 35) * 0.05 + rng.normal(0, 0.8, len(days))
        frame = pd.DataFrame({"location_code": code, "date": [d.isoformat() for d in days],
                              "is_forecast": [int(d > AS_OF) for d in days],
                              "t_max": t_max.round(1), "t_min": np.minimum(t_min, t_max).round(1),
                              "humidity": humidity.round(0)})
        # scattered missing days earlier in the season (about 2%)
        drop = (rng.random(len(days)) < 0.02) & (np.array(days) < AS_OF - timedelta(days=8))
        frame = frame[~drop]
        frames.append(frame)
    weather = pd.concat(frames, ignore_index=True)
    stale = (weather["location_code"] == STALE_WARD) & (weather["date"] > (AS_OF - timedelta(days=4)).isoformat()) \
        & (weather["date"] <= AS_OF.isoformat())
    gap = (weather["location_code"] == GAP_WARD) & (weather["date"] == GAP_DAY.isoformat())
    return weather[~stale & ~gap].reset_index(drop=True)


def seed_database(db):
    """Fill an empty database with the demo region, wards, weather and resources."""
    source_id = db.add_source(SOURCE_NAME, "synthetic", "NOOR (noor/seed.py)", "Generated for this project",
                              f"Fictional district; NumPy seed {SEED}; {START} to {AS_OF} + {FORECAST_DAYS} forecast days")
    db.add_source("Open-Meteo (optional import)", "model_derived", "open-meteo.com", "CC BY 4.0",
                  "Gridded weather-model data. Only used if you run scripts/fetch_open_meteo.py and import the CSV.")
    region = build_region()
    region_id = db.add_region(region.name, True, "Fictional district on a schematic grid. Not a real place.")
    for loc in region.locations:
        db.add_location(loc, region_id, source_id)
    ids = {row["code"]: row["id"] for row in db.list_locations()}
    weather = build_weather()
    db.add_observations([
        (ids[r.location_code], r.date, int(r.is_forecast), float(r.t_max), float(r.t_min), float(r.humidity), source_id)
        for r in weather.itertuples()])
    for res in build_resources():
        db.add_resource(res, ids[res.location_code], source_id)
    return {"locations": len(region), "observations": len(weather), "resources": len(RESOURCES)}
