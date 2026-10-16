"""SQLite access with the built-in sqlite3 module.

Every query uses ? placeholders (never string formatting with user input), so a value like
"x'; DROP TABLE locations; --" is stored as plain text and cannot change the SQL.

The local web server answers requests on several threads. Each request opens its own
Database object (sqlite3 connections should not be shared between threads), and all writes
go through one class-level threading.Lock so two threads never write at the same moment.
"""
import os
import sqlite3
import threading
from datetime import datetime, timezone

import pandas as pd

from . import settings
from .exceptions import ConflictError, NotFoundError


def now_utc():
    """Current time as an ISO string, e.g. 2026-06-04T10:15:00Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Database:
    """A connection to the NOOR SQLite file plus the CRUD operations the app needs."""

    write_lock = threading.Lock()  # class attribute: one lock shared by all Database objects

    def __init__(self, path=None):
        """Open (or create) the database file and switch on foreign-key checks."""
        self.path = path or settings.database_path()
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self):
        """Close the connection (safe to call twice)."""
        if getattr(self, "conn", None) is not None:
            self.conn.close()
            self.conn = None

    def __del__(self):
        """Destructor: make sure the file handle is released when the object is garbage-collected."""
        self.close()

    # ------------------------------------------------------------------ generic helpers
    def create_tables(self):
        """Run schema.sql. CREATE TABLE IF NOT EXISTS makes this safe to repeat."""
        with open(settings.SCHEMA_FILE, encoding="utf-8") as f:
            script = f.read()
        with Database.write_lock:
            self.conn.executescript(script)

    def fetch_all(self, sql, params=()):
        """Run a SELECT and return a list of dicts."""
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def fetch_one(self, sql, params=()):
        """Run a SELECT and return one dict, or None."""
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def execute(self, sql, params=()):
        """Run one INSERT/UPDATE/DELETE inside the write lock and commit. Returns the new row id."""
        with Database.write_lock:
            try:
                with self.conn:  # commits on success, rolls back on error
                    cursor = self.conn.execute(sql, params)
            except sqlite3.IntegrityError as exc:
                raise ConflictError(f"Database rule broken: {exc}") from None
        return cursor.lastrowid

    def execute_many(self, sql, rows):
        """Run the same statement for many rows in one transaction."""
        with Database.write_lock:
            try:
                with self.conn:
                    self.conn.executemany(sql, rows)
            except sqlite3.IntegrityError as exc:
                raise ConflictError(f"Database rule broken: {exc}") from None

    def dataframe(self, sql, params=()):
        """Run a SELECT and return a pandas DataFrame."""
        return pd.read_sql_query(sql, self.conn, params=params)

    def is_empty(self):
        """True when no data source has been added yet (fresh database)."""
        return self.fetch_one("SELECT COUNT(*) AS n FROM data_sources")["n"] == 0

    def table_counts(self):
        """Row count of every table, for the status page."""
        tables = ["data_sources", "regions", "locations", "observations", "resources",
                  "risk_assessments", "alerts", "allocations"]
        return {t: self.fetch_one(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in tables}  # fixed names

    # ------------------------------------------------------------------ sources and regions
    def add_source(self, name, kind, provider, licence, notes=None):
        """Insert a data source and return its id."""
        return self.execute(
            "INSERT INTO data_sources (name, kind, provider, licence, notes) VALUES (?, ?, ?, ?, ?)",
            (name, kind, provider, licence, notes))

    def list_sources(self):
        """All data sources with how many rows use each."""
        return self.fetch_all(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM observations o WHERE o.source_id = s.id) AS observations,
                      (SELECT COUNT(*) FROM locations l WHERE l.source_id = s.id) AS locations,
                      (SELECT COUNT(*) FROM resources r WHERE r.source_id = s.id) AS resources
               FROM data_sources s ORDER BY s.id""")

    def add_region(self, name, is_demo, description):
        """Insert a region and return its id."""
        return self.execute("INSERT INTO regions (name, is_demo, description) VALUES (?, ?, ?)",
                            (name, int(is_demo), description))

    def get_region_id(self, name):
        """Return the id of a region by name, or None."""
        row = self.fetch_one("SELECT id FROM regions WHERE name = ?", (name,))
        return row["id"] if row else None

    # ------------------------------------------------------------------ locations
    def add_location(self, location, region_id, source_id):
        """Insert a models.Location object."""
        return self.execute(
            """INSERT INTO locations (code, name, region_id, grid_x, grid_y, population, area_km2,
                   elderly_share, children_share, outdoor_worker_share, poor_housing_share,
                   low_income_share, piped_water_share, source_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (location.code, location.name, region_id, location.grid_x, location.grid_y,
             location.population, location.area_km2, location.get_share("elderly_share"),
             location.get_share("children_share"), location.get_share("outdoor_worker_share"),
             location.get_share("poor_housing_share"), location.get_share("low_income_share"),
             location.get_share("piped_water_share"), source_id))

    def list_locations(self):
        """All locations with their region name and the kind of their source."""
        return self.fetch_all(
            """SELECT l.*, r.name AS region, r.is_demo, s.kind AS source_kind
               FROM locations l
               JOIN regions r ON r.id = l.region_id
               JOIN data_sources s ON s.id = l.source_id
               ORDER BY l.code""")

    def get_location(self, code):
        """One location by code; raises NotFoundError if missing."""
        row = self.fetch_one(
            """SELECT l.*, r.name AS region, r.is_demo, s.kind AS source_kind, s.name AS source_name
               FROM locations l JOIN regions r ON r.id = l.region_id JOIN data_sources s ON s.id = l.source_id
               WHERE l.code = ?""", (code,))
        if row is None:
            raise NotFoundError(f"No location with code '{code}'")
        return row

    # ------------------------------------------------------------------ observations
    def add_observations(self, rows):
        """Insert or replace daily rows: (location_id, obs_date, is_forecast, t_max, t_min, humidity, source_id)."""
        self.execute_many(
            """INSERT OR REPLACE INTO observations
                   (location_id, obs_date, is_forecast, t_max, t_min, humidity, source_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""", rows)

    def observations_frame(self, codes=None, start=None, end=None):
        """Observations as a DataFrame with location code and source kind, optionally filtered."""
        sql = """SELECT l.code AS location, l.name, o.obs_date AS date, o.is_forecast, o.t_max, o.t_min,
                        o.humidity, s.kind AS source_kind, s.name AS source
                 FROM observations o
                 JOIN locations l ON l.id = o.location_id
                 JOIN data_sources s ON s.id = o.source_id
                 WHERE 1 = 1"""
        params = []
        if codes:
            sql += " AND l.code IN (" + ",".join("?" for _ in codes) + ")"
            params += list(codes)
        if start:
            sql += " AND o.obs_date >= ?"
            params.append(start)
        if end:
            sql += " AND o.obs_date <= ?"
            params.append(end)
        sql += " ORDER BY l.code, o.obs_date"
        return self.dataframe(sql, params)

    # ------------------------------------------------------------------ resources
    def add_resource(self, resource, location_id, source_id):
        """Insert a models.Resource object."""
        return self.execute(
            """INSERT INTO resources (code, name, type, location_id, amount, status, radius_km, staff,
                                      daily_cost, source_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (resource.code, resource.name, resource.type_name, location_id, resource.amount, resource.status,
             resource.radius_km, resource.staff, resource.daily_cost, source_id))

    def list_resources(self):
        """All resources with their location code and source kind."""
        return self.fetch_all(
            """SELECT r.*, l.code AS location_code, l.name AS location_name, s.kind AS source_kind
               FROM resources r
               JOIN locations l ON l.id = r.location_id
               JOIN data_sources s ON s.id = r.source_id
               ORDER BY r.type, r.code""")

    def update_resource(self, code, status, amount):
        """Change a resource's status and amount."""
        if self.fetch_one("SELECT id FROM resources WHERE code = ?", (code,)) is None:
            raise NotFoundError(f"No resource with code '{code}'")
        self.execute("UPDATE resources SET status = ?, amount = ? WHERE code = ?", (status, amount, code))

    def delete_resource(self, code):
        """Delete a resource (its saved allocation rows go with it: ON DELETE CASCADE)."""
        if self.fetch_one("SELECT id FROM resources WHERE code = ?", (code,)) is None:
            raise NotFoundError(f"No resource with code '{code}'")
        self.execute("DELETE FROM resources WHERE code = ?", (code,))

    # ------------------------------------------------------------------ risk assessments
    def save_assessments(self, rows):
        """Store one batch of assessments (list of dicts from RiskEngine)."""
        stamp = now_utc()
        ids = {loc["code"]: loc["id"] for loc in self.list_locations()}
        self.execute_many(
            """INSERT INTO risk_assessments (location_id, assessed_at, as_of_date, hazard, exposure,
                   vulnerability, capacity, score, category, confidence, reasons)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(ids[r["code"]], stamp, r["as_of"], r["hazard"], r["exposure"], r["vulnerability"],
              r["capacity"], r["score"], r["category"], r["confidence"], " | ".join(r["reasons"]))
             for r in rows])

    def latest_assessments(self):
        """The most recent assessment of every location (highest score first)."""
        return self.fetch_all(
            """SELECT l.code, l.name, l.population, l.grid_x, l.grid_y, a.*
               FROM risk_assessments a
               JOIN locations l ON l.id = a.location_id
               WHERE a.id IN (SELECT MAX(id) FROM risk_assessments GROUP BY location_id)
               ORDER BY a.score IS NULL, a.score DESC""")

    # ------------------------------------------------------------------ alerts
    def save_alert(self, alert, location_id):
        """Insert a new alert; if the same rule already fired for this location and period, keep the old one.

        Returns True when a new row was created."""
        existing = self.fetch_one("SELECT id FROM alerts WHERE location_id = ? AND rule = ? AND period = ?",
                                  (location_id, alert.rule, alert.period))
        if existing is not None:
            return False
        self.execute(
            """INSERT INTO alerts (location_id, rule, severity, message, trigger_value, threshold,
                   period, actions, confidence, issued_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (location_id, alert.rule, alert.severity, alert.message, alert.value, alert.threshold,
             alert.period, " | ".join(alert.actions), alert.confidence, now_utc()))
        return True

    def list_alerts(self, status=None, severity=None):
        """Alerts with location names, most severe first; optional filters."""
        sql = """SELECT a.*, l.code, l.name FROM alerts a JOIN locations l ON l.id = a.location_id WHERE 1 = 1"""
        params = []
        if status:
            sql += " AND a.status = ?"
            params.append(status)
        if severity:
            sql += " AND a.severity = ?"
            params.append(severity)
        sql += """ ORDER BY a.status = 'resolved',
                   CASE a.severity WHEN 'emergency' THEN 0 WHEN 'warning' THEN 1 WHEN 'advisory' THEN 2 ELSE 3 END,
                   l.code"""
        return self.fetch_all(sql, params)

    def set_alert_status(self, alert_id, new_status):
        """Move an alert forward: active -> acknowledged -> resolved (never backwards)."""
        row = self.fetch_one("SELECT status FROM alerts WHERE id = ?", (alert_id,))
        if row is None:
            raise NotFoundError(f"No alert with id {alert_id}")
        allowed = {"active": ("acknowledged", "resolved"), "acknowledged": ("resolved",), "resolved": ()}
        if new_status not in allowed[row["status"]]:
            raise ConflictError(f"An alert that is {row['status']} cannot become {new_status}")
        self.execute("UPDATE alerts SET status = ? WHERE id = ?", (new_status, alert_id))

    # ------------------------------------------------------------------ allocation plans
    def save_plan(self, plan_name, strategy, assignments):
        """Store a plan: assignments are (resource_code, location_code, people_per_day)."""
        res_ids = {r["code"]: r["id"] for r in self.list_resources()}
        loc_ids = {l["code"]: l["id"] for l in self.list_locations()}
        stamp = now_utc()
        self.execute_many(
            """INSERT INTO allocations (plan_name, strategy, resource_id, location_id, people_per_day, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(plan_name, strategy, res_ids[rc], loc_ids[lc], round(people, 1), stamp)
             for rc, lc, people in assignments if people > 0])

    def list_plans(self):
        """Saved plans with their size."""
        return self.fetch_all(
            """SELECT plan_name, strategy, MIN(created_at) AS created_at, COUNT(*) AS rows,
                      ROUND(SUM(people_per_day)) AS people_per_day
               FROM allocations GROUP BY plan_name, strategy ORDER BY created_at DESC""")
