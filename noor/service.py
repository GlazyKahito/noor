"""NoorService: the one place where the database and the calculations meet.

The web pages and the JSON API call these methods; they never run SQL or maths themselves.
"""
from datetime import date

from . import settings
from .alerts import WarningEngine
from .allocation import STRATEGIES, AllocationPlanner, compare_plans
from .exceptions import ValidationError
from .importer import read_upload, validate
from .models import Location, make_resource
from .risk import RiskEngine, assess_all
from .scenario import Scenario
from .seed import seed_database


class NoorService:
    """Use-case methods on top of a Database object."""

    def __init__(self, db):
        """Keep a reference to the database (aggregation: the service does not own it)."""
        self.db = db

    # ------------------------------------------------------------------ setup
    def setup(self):
        """Create tables; on a fresh database load the demo data and compute first results.

        On every start the risk is recalculated, so a weight or threshold changed in
        settings.py shows up after a restart."""
        self.db.create_tables()
        if not self.db.is_empty():
            self.recalculate()
            return None
        summary = seed_database(self.db)
        self.recalculate()
        self.run_alerts()
        self.save_plan("Risk-first plan", "risk_first")
        self.save_plan("Population-first baseline", "population_first")
        return summary

    # ------------------------------------------------------------------ loading objects
    def locations(self):
        """All locations as Location objects."""
        result = []
        for row in self.db.list_locations():
            shares = {name: row[name] for name in ("elderly_share", "children_share", "outdoor_worker_share",
                                                   "poor_housing_share", "low_income_share", "piped_water_share")}
            result.append(Location(row["code"], row["name"], row["population"], row["area_km2"],
                                   row["grid_x"], row["grid_y"], **shares))
        return result

    def resources(self):
        """All resources as objects of the right subclass."""
        return [make_resource(r["type"], code=r["code"], name=r["name"], location_code=r["location_code"],
                              amount=r["amount"], status=r["status"], radius_km=r["radius_km"], staff=r["staff"],
                              daily_cost=r["daily_cost"], kind=r["source_kind"])
                for r in self.db.list_resources()]

    def observations_by_code(self):
        """{location code: DataFrame of its observations}."""
        frame = self.db.observations_frame()
        return {code: group for code, group in frame.groupby("location")}

    def as_of_dates(self):
        """Each location is assessed as of the latest observed day in its region."""
        rows = self.db.fetch_all(
            """SELECT l.code, (SELECT MAX(o.obs_date) FROM observations o JOIN locations l2 ON l2.id = o.location_id
                               WHERE l2.region_id = l.region_id AND o.is_forecast = 0) AS as_of
               FROM locations l""")
        today = date.today().isoformat()
        return {r["code"]: r["as_of"] or today for r in rows}

    def synthetic_codes(self):
        """Codes of locations whose inputs come from the synthetic source."""
        return {r["code"] for r in self.db.list_locations() if r["source_kind"] == "synthetic"}

    # ------------------------------------------------------------------ risk
    def assess(self, weights=None):
        """Fresh assessment of every location (not saved)."""
        engine = RiskEngine(weights)
        return assess_all(self.locations(), self.resources(), self.observations_by_code(),
                          self.as_of_dates(), engine)

    def recalculate(self):
        """Assess with the standard weights and save the results."""
        results = self.assess()
        self.db.save_assessments(results)
        return results

    def assessment(self, code, weights=None):
        """Full assessment (with dimension details) for one location."""
        self.db.get_location(code)  # raises NotFoundError for unknown codes
        for result in self.assess(weights):
            if result["code"] == code:
                return result
        raise ValidationError("Location could not be assessed")

    # ------------------------------------------------------------------ alerts
    def run_alerts(self):
        """Evaluate all warning rules and store new alerts. Returns (new, total found)."""
        results = self.assess()
        by_code = {r["code"]: r for r in results}
        plan = AllocationPlanner(self.locations(), self.resources(), by_code).run("risk_first")
        coverage = {row["code"]: row["cooling_centre_coverage"] for row in plan["locations"]}
        synthetic = self.synthetic_codes()
        contexts = [{**r, "cooling_coverage": coverage.get(r["code"]), "synthetic": r["code"] in synthetic}
                    for r in results]
        ids = {row["code"]: row["id"] for row in self.db.list_locations()}
        found = WarningEngine().run(contexts)
        new = 0
        for code, alert in found:
            if self.db.save_alert(alert, ids[code]):
                new += 1
        return new, len(found)

    # ------------------------------------------------------------------ allocation
    def plan(self, strategy="risk_first"):
        """Run the greedy planner (not saved)."""
        if strategy not in STRATEGIES:
            raise ValidationError("Strategy must be one of: " + ", ".join(STRATEGIES))
        by_code = {r["code"]: r for r in self.db.latest_assessments()}
        return AllocationPlanner(self.locations(), self.resources(), by_code).run(strategy)

    def save_plan(self, name, strategy):
        """Run and save a plan under a name."""
        name = (name or "").strip()
        if not 1 <= len(name) <= 60:
            raise ValidationError("Plan name must be 1-60 characters")
        result = self.plan(strategy)
        self.db.save_plan(name, strategy, result["assignments"])
        return result

    def compare(self):
        """Compare the two strategies on today's data."""
        return compare_plans(self.plan("population_first"), self.plan("risk_first"))

    # ------------------------------------------------------------------ scenario
    def scenario(self, params):
        """Run a Scenario Lab calculation."""
        scenario = Scenario(**params)
        return scenario.run(self.locations(), self.resources(), self.observations_by_code(), self.as_of_dates())

    # ------------------------------------------------------------------ data management
    def import_csv(self, data, source_name, kind, licence):
        """Validate an uploaded CSV and store the good rows under a new data source."""
        source_name = (source_name or "").strip()
        licence = (licence or "").strip()
        if not 3 <= len(source_name) <= 80:
            raise ValidationError("Give the data source a name (3-80 characters)")
        if kind not in settings.DATA_KINDS:
            raise ValidationError("Choose what kind of data this is")
        if not 2 <= len(licence) <= 120:
            raise ValidationError("Give the licence or terms (write 'unknown' if you do not know)")
        df = read_upload(data)
        known = {row["code"] for row in self.db.list_locations()}
        clean, errors = validate(df, known)
        report = {"rows": len(df), "accepted": len(clean), "rejected": len(df) - len(clean),
                  "errors": errors[:100], "more_errors": max(0, len(errors) - 100)}
        if clean.empty:
            return report
        name = f"{source_name} ({date.today().isoformat()}, {self.db.fetch_one('SELECT COUNT(*) AS n FROM data_sources')['n'] + 1})"
        source_id = self.db.add_source(name, kind, "Uploaded CSV", licence, "Imported through the Data page")
        ids = {row["code"]: row["id"] for row in self.db.list_locations()}
        self.db.add_observations([
            (ids[r.location_code], r.date, int(r.is_forecast), none_if_nan(r.t_max), none_if_nan(r.t_min),
             none_if_nan(r.humidity), source_id) for r in clean.itertuples()])
        self.recalculate()
        report["source"] = name
        return report

    def add_location(self, form):
        """Add a location to an existing or new region from form fields."""
        region = (form.get("region") or "").strip()
        if not 3 <= len(region) <= 80:
            raise ValidationError("Region name must be 3-80 characters")
        loc = Location(form.get("code"), form.get("name"), form.get("population") or None,
                       form.get("area_km2") or None, to_float(form.get("grid_x")), to_float(form.get("grid_y")),
                       **{k: form.get(k) or None for k in ("elderly_share", "children_share", "outdoor_worker_share",
                                                           "poor_housing_share", "low_income_share",
                                                           "piped_water_share")})
        kind = form.get("kind", "estimated")
        if kind not in settings.DATA_KINDS:
            raise ValidationError("Choose what kind of data this is")
        source = (form.get("source") or "").strip()
        if not 3 <= len(source) <= 80:
            raise ValidationError("Say where the population and indicator numbers come from (3-80 characters)")
        region_id = self.db.get_region_id(region) or self.db.add_region(region, kind == "synthetic", None)
        existing = self.db.fetch_one("SELECT id FROM data_sources WHERE name = ?", (source,))
        source_id = existing["id"] if existing else self.db.add_source(source, kind, "Entered in NOOR", "As stated")
        self.db.add_location(loc, region_id, source_id)
        self.recalculate()
        return loc

    def add_resource(self, form):
        """Add a resource from form fields."""
        location = self.db.get_location((form.get("location_code") or "").strip())
        code = (form.get("code") or "").strip()
        if not 2 <= len(code) <= 20:
            raise ValidationError("Resource code must be 2-20 characters")
        name = (form.get("name") or "").strip()
        if not 2 <= len(name) <= 80:
            raise ValidationError("Resource name must be 2-80 characters")
        amount = to_float(form.get("amount"), "Amount")
        radius = to_float(form.get("radius_km"), "Radius")
        if amount is None or radius is None:
            raise ValidationError("Amount and service radius are required")
        res = make_resource(form.get("type"), code=code, name=name, location_code=location["code"],
                            amount=amount, status=form.get("status", "available"), radius_km=radius,
                            staff=int(to_float(form.get("staff") or 0, "Staff")),
                            daily_cost=int(to_float(form.get("daily_cost") or 0, "Daily cost")))
        kind = form.get("kind", "estimated")
        if kind not in settings.DATA_KINDS:
            raise ValidationError("Choose what kind of data this is")
        source_name = f"Resource inventory entered in NOOR ({settings.DATA_KINDS[kind]})"
        existing = self.db.fetch_one("SELECT id FROM data_sources WHERE name = ?", (source_name,))
        source_id = existing["id"] if existing else self.db.add_source(source_name, kind, "Entered in NOOR", "As stated")
        self.db.add_resource(res, location["id"], source_id)
        self.recalculate()
        return res

    def update_resource(self, code, status, amount):
        """Change status/amount of a resource and recalculate risk."""
        if status not in settings.STATUS_FACTOR:
            raise ValidationError("Status must be available, limited or offline")
        amount = to_float(amount, "Amount")
        if amount is None or amount <= 0:
            raise ValidationError("Amount must be greater than zero")
        self.db.update_resource(code, status, amount)
        self.recalculate()

    def status(self):
        """Counts, data freshness and sources for the status page and /api/status."""
        latest = self.db.fetch_one("SELECT MAX(obs_date) AS d FROM observations WHERE is_forecast = 0")["d"]
        kinds = sorted({s["kind"] for s in self.db.list_sources() if s["observations"] or s["locations"]})
        return {
            "counts": self.db.table_counts(),
            "latest_observation": latest,
            "days_since_latest": (date.today() - date.fromisoformat(latest)).days if latest else None,
            "data_kinds": kinds,
            "synthetic_only": kinds == ["synthetic"],
            "sources": self.db.list_sources(),
        }


def to_float(value, label="Value"):
    """Convert form text to float, or None for empty input."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a number") from None


def none_if_nan(value):
    """Pandas uses NaN for empty cells; SQLite needs None (NULL)."""
    return None if value != value else float(value)  # NaN is the only value not equal to itself
