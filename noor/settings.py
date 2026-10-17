"""All settings and every number NOOR's methods use, in one file.

To change how NOOR scores risk or raises warnings, edit the values here. None of these
numbers are official Indian warning criteria. The heat-index bands follow the US National
Weather Service heat index chart (converted to Celsius); everything else is a NOOR default
chosen for the demonstration and meant to be reviewed by the people who use the tool.
"""
import os

# ---------------------------------------------------------------------------- paths
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PACKAGE_DIR)
SCHEMA_FILE = os.path.join(PACKAGE_DIR, "schema.sql")


def database_path():
    """Return the SQLite file path: instance/noor.db inside the project folder.

    The NOOR_DB_PATH environment variable overrides it (the tests use a temporary file)."""
    if os.environ.get("NOOR_DB_PATH"):
        return os.environ["NOOR_DB_PATH"]
    return os.path.join(PROJECT_DIR, "instance", "noor.db")


# ---------------------------------------------------------------------------- risk score
# The four dimension weights must add up to 1.0.
# score = 100 * (hazard*w1 + exposure*w2 + vulnerability*w3 + (1 - capacity)*w4)
RISK_WEIGHTS = {
    "hazard": 0.40,
    "exposure": 0.20,
    "vulnerability": 0.25,
    "lack_of_capacity": 0.15,
}

# Min-max bounds: a raw value at `low` becomes 0, at `high` becomes 1, values outside are clipped.
# Fixed bounds (not the min/max of today's data) keep scores comparable between days.
HAZARD_INDICATORS = {
    # name: (low, high, weight inside the hazard dimension)
    "peak_heat_index": (27.0, 52.0, 0.40),   # deg C; 27 = NWS "caution", 52 = NWS "extreme danger"
    "peak_tmax": (35.0, 47.0, 0.25),         # deg C
    "hot_days": (0.0, 6.0, 0.20),            # longest run of days with Tmax >= HOT_DAY_C
    "warm_nights": (0.0, 6.0, 0.15),         # nights with Tmin >= WARM_NIGHT_C
}
EXPOSURE_INDICATORS = {
    "density": (1000.0, 40000.0, 0.6),       # people per km2
    "population": (20000.0, 400000.0, 0.4),  # people
}
VULNERABILITY_INDICATORS = {
    "elderly_share": (0.03, 0.15, 0.25),
    "children_share": (0.05, 0.14, 0.15),
    "outdoor_worker_share": (0.05, 0.35, 0.20),
    "poor_housing_share": (0.0, 0.60, 0.25),
    "low_income_share": (0.05, 0.50, 0.15),
}
CAPACITY_INDICATORS = {
    # Response capacity: higher is better. Per-1,000 values come from the resource inventory.
    "cooling_per_1000": (0.0, 5.0, 0.35),
    "water_per_1000": (0.0, 50.0, 0.20),
    "medical_per_1000": (0.0, 0.5, 0.25),
    "piped_water_share": (0.3, 1.0, 0.20),
}

WINDOW_DAYS = 7          # observed days used for the hazard, ending on the as-of date
FORECAST_DAYS = 3        # forecast days after the as-of date also count
MIN_OBSERVED_DAYS = 3    # fewer observed days than this -> "insufficient data", no score
HOT_DAY_C = 40.0
WARM_NIGHT_C = 28.0

# A dimension with no data at all is NOT treated as zero. It gets this precautionary value
# (mid-range) and the assessment's confidence is lowered.
MISSING_DIMENSION_VALUE = 0.5

# Category thresholds (lower bound inclusive) on the 0-100 score.
CATEGORIES = [
    (80.0, "Extreme"),
    (60.0, "Severe"),
    (40.0, "High"),
    (20.0, "Moderate"),
    (0.0, "Low"),
]

# ---------------------------------------------------------------------------- warnings
HEAT_INDEX_BANDS = [
    # (threshold deg C, severity, label) — NWS heat index chart, converted from Fahrenheit
    (51.7, "emergency", "extreme danger"),
    (39.4, "warning", "danger"),
    (32.2, "advisory", "extreme caution"),
]
HOT_SPELL_WARNING_DAYS = 3
HOT_SPELL_EMERGENCY_DAYS = 5
WARM_NIGHTS_ADVISORY = 2
STALE_DATA_DAYS = 3
COOLING_GAP_SHARE = 0.5  # advisory if a High+ location gets under 50% of its cooling demand

# ---------------------------------------------------------------------------- planning
# Demand (people per day) = population * rate * risk_score / 100. These are planning
# assumptions, not measured rates. Change them to match local norms.
DEMAND_RATES = {
    "cooling_centre": 0.005,
    "water_point": 0.05,
    "medical_unit": 0.0005,
    "response_team": 0.0003,
    "outreach_team": 0.01,
}
STATUS_FACTOR = {"available": 1.0, "limited": 0.5, "offline": 0.0}
LITRES_PER_PERSON = 4.0       # drinking water a water point must supply per person per day
VISITS_PER_RESPONDER = 6      # emergency visits one response-team member can make per day
CONTACTS_PER_VOLUNTEER = 40   # outreach contacts one volunteer can make per day

# A hypothetical cooling centre added in the Scenario Lab.
NEW_CENTRE = {"places": 400, "daily_cost": 15000, "staff": 4, "radius_km": 3.0}

DATA_KINDS = {
    "measured": "Measured",
    "model_derived": "Model-derived",
    "estimated": "Estimated",
    "synthetic": "Synthetic (demo)",
}
