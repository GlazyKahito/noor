-- NOOR database schema: 8 tables. Run by Database.create_tables().
-- Every table has a PRIMARY KEY; links between tables are FOREIGN KEYs.

-- Where each number came from. kind says how far to trust it.
CREATE TABLE IF NOT EXISTS data_sources (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE,
    kind      TEXT NOT NULL CHECK (kind IN ('measured', 'model_derived', 'estimated', 'synthetic')),
    provider  TEXT NOT NULL,
    licence   TEXT NOT NULL,
    notes     TEXT
);

-- A district or city. is_demo = 1 marks the synthetic demonstration region.
CREATE TABLE IF NOT EXISTS regions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    is_demo     INTEGER NOT NULL DEFAULT 1 CHECK (is_demo IN (0, 1)),
    description TEXT
);

-- A ward inside a region, with exposure and vulnerability inputs (NULL = unknown).
CREATE TABLE IF NOT EXISTS locations (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    code                 TEXT NOT NULL UNIQUE,
    name                 TEXT NOT NULL,
    region_id            INTEGER NOT NULL REFERENCES regions(id),
    grid_x               REAL,
    grid_y               REAL,
    population           INTEGER CHECK (population IS NULL OR population >= 0),
    area_km2             REAL CHECK (area_km2 IS NULL OR area_km2 > 0),
    elderly_share        REAL CHECK (elderly_share IS NULL OR elderly_share BETWEEN 0 AND 1),
    children_share       REAL CHECK (children_share IS NULL OR children_share BETWEEN 0 AND 1),
    outdoor_worker_share REAL CHECK (outdoor_worker_share IS NULL OR outdoor_worker_share BETWEEN 0 AND 1),
    poor_housing_share   REAL CHECK (poor_housing_share IS NULL OR poor_housing_share BETWEEN 0 AND 1),
    low_income_share     REAL CHECK (low_income_share IS NULL OR low_income_share BETWEEN 0 AND 1),
    piped_water_share    REAL CHECK (piped_water_share IS NULL OR piped_water_share BETWEEN 0 AND 1),
    source_id            INTEGER NOT NULL REFERENCES data_sources(id)
);

-- One row per location per day. is_forecast = 1 for forecast days.
CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    obs_date    TEXT NOT NULL,
    is_forecast INTEGER NOT NULL DEFAULT 0 CHECK (is_forecast IN (0, 1)),
    t_max       REAL CHECK (t_max IS NULL OR t_max BETWEEN -40 AND 60),
    t_min       REAL CHECK (t_min IS NULL OR t_min BETWEEN -50 AND 50),
    humidity    REAL CHECK (humidity IS NULL OR humidity BETWEEN 0 AND 100),
    source_id   INTEGER NOT NULL REFERENCES data_sources(id),
    UNIQUE (location_id, obs_date, is_forecast)
);
CREATE INDEX IF NOT EXISTS idx_obs_location_date ON observations(location_id, obs_date);

-- Emergency resources. amount is in the unit of the type (places, litres, patients, members, volunteers).
CREATE TABLE IF NOT EXISTS resources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('cooling_centre', 'water_point', 'medical_unit', 'response_team', 'outreach_team')),
    location_id INTEGER NOT NULL REFERENCES locations(id),
    amount      REAL NOT NULL CHECK (amount > 0),
    status      TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'limited', 'offline')),
    radius_km   REAL NOT NULL CHECK (radius_km > 0),
    staff       INTEGER NOT NULL DEFAULT 0 CHECK (staff >= 0),
    daily_cost  INTEGER NOT NULL DEFAULT 0 CHECK (daily_cost >= 0),
    source_id   INTEGER NOT NULL REFERENCES data_sources(id)
);

-- Results of the risk engine. A new batch of rows is added every time risk is recalculated.
CREATE TABLE IF NOT EXISTS risk_assessments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id   INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    assessed_at   TEXT NOT NULL,
    as_of_date    TEXT NOT NULL,
    hazard        REAL,
    exposure      REAL,
    vulnerability REAL,
    capacity      REAL,
    score         REAL CHECK (score IS NULL OR score BETWEEN 0 AND 100),
    category      TEXT NOT NULL,
    confidence    TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
    reasons       TEXT NOT NULL
);

-- Warnings raised by the rule engine.
CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id   INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    rule          TEXT NOT NULL,
    severity      TEXT NOT NULL CHECK (severity IN ('info', 'advisory', 'warning', 'emergency')),
    message       TEXT NOT NULL,
    trigger_value REAL,
    threshold     REAL,
    period        TEXT NOT NULL,
    actions       TEXT NOT NULL,
    confidence    TEXT NOT NULL,
    issued_at     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'acknowledged', 'resolved')),
    UNIQUE (location_id, rule, period)
);

-- Saved allocation plans: which resource serves which location, and how many people.
CREATE TABLE IF NOT EXISTS allocations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_name      TEXT NOT NULL,
    strategy       TEXT NOT NULL CHECK (strategy IN ('risk_first', 'population_first')),
    resource_id    INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    location_id    INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    people_per_day REAL NOT NULL CHECK (people_per_day > 0),
    created_at     TEXT NOT NULL
);
