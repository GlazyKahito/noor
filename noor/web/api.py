"""JSON API. Every response is {"ok": true, "data": ...} or {"ok": false, "error": {...}}.

The functions here return plain Python data; server.py turns it into JSON.
"""
import math

from .. import __version__, settings
from ..allocation import STRATEGIES
from ..exceptions import NotFoundError, ValidationError
from ..queries import QUERIES, run_query

MAX_OBSERVATION_ROWS = 5000


def clean(value):
    """Make a value JSON-safe: NaN -> None, numpy numbers -> Python numbers."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):  # numpy scalar
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def assessment_json(result):
    """Assessment dict without the DataFrame, with the daily window as a list."""
    out = {k: v for k, v in result.items() if k != "daily"}
    daily = result["daily"].reset_index()
    daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")
    out["daily"] = daily.to_dict(orient="records")
    return clean(out)


def health(svc, q):
    """Liveness and basic counts."""
    return {"status": "ok", "version": __version__, "locations": svc.db.table_counts()["locations"]}


def status(svc, q):
    """Counts, data freshness and sources."""
    return svc.status()


def locations(svc, q):
    """All locations."""
    return svc.db.list_locations()


def location(svc, q, code):
    """One location."""
    return svc.db.get_location(code)


def observations(svc, q):
    """Observations, filtered by ?location=CODE&start=YYYY-MM-DD&end=YYYY-MM-DD (max 5000 rows)."""
    codes = [q["location"]] if q.get("location") else None
    if codes:
        svc.db.get_location(codes[0])
    frame = svc.db.observations_frame(codes, q.get("start"), q.get("end"))
    truncated = len(frame) > MAX_OBSERVATION_ROWS
    return {"rows": clean(frame.head(MAX_OBSERVATION_ROWS).to_dict(orient="records")), "truncated": truncated}


def risk(svc, q):
    """Latest stored assessment of every location (optionally ?category=High)."""
    rows = svc.db.latest_assessments()
    if q.get("category"):
        rows = [r for r in rows if r["category"] == q["category"]]
    return rows


def risk_detail(svc, q, code):
    """Full explained assessment of one location."""
    return assessment_json(svc.assessment(code))


def risk_weights(svc, q, body):
    """POST {"weights": {...}}: what-if ranking with custom weights (not saved)."""
    weights = body.get("weights") if isinstance(body, dict) else None
    if not isinstance(weights, dict):
        raise ValidationError('Send {"weights": {"hazard": .., "exposure": .., "vulnerability": .., "lack_of_capacity": ..}}')
    results = svc.assess(weights)
    return [{k: r[k] for k in ("code", "name", "score", "category", "hazard", "exposure", "vulnerability",
                               "capacity", "confidence")} for r in results]


def alerts(svc, q):
    """Alerts filtered by ?status= and ?severity=."""
    if q.get("status") and q["status"] not in ("active", "acknowledged", "resolved"):
        raise ValidationError("status must be active, acknowledged or resolved")
    if q.get("severity") and q["severity"] not in ("info", "advisory", "warning", "emergency"):
        raise ValidationError("severity must be info, advisory, warning or emergency")
    return svc.db.list_alerts(q.get("status"), q.get("severity"))


def alerts_run(svc, q, body):
    """POST: run the warning engine."""
    new, found = svc.run_alerts()
    return {"new_alerts": new, "rules_fired": found}


def alert_status(svc, q, body, alert_id):
    """POST {"status": "acknowledged" | "resolved"}."""
    new_status = body.get("status") if isinstance(body, dict) else None
    if new_status not in ("acknowledged", "resolved"):
        raise ValidationError('Send {"status": "acknowledged"} or {"status": "resolved"}')
    svc.db.set_alert_status(int(alert_id), new_status)
    return {"id": int(alert_id), "status": new_status}


def resources(svc, q):
    """Inventory with people-per-day capacity from each Resource subclass."""
    objects = {r.code: r for r in svc.resources()}
    rows = svc.db.list_resources()
    for row in rows:
        row["people_per_day"] = round(objects[row["code"]].capacity(), 1)
    return rows


def resource_create(svc, q, body):
    """POST a new resource (same fields as the form)."""
    if not isinstance(body, dict):
        raise ValidationError("Send a JSON object")
    res = svc.add_resource({k: str(v) for k, v in body.items()})
    return {"code": res.code, "people_per_day": res.capacity()}


def resource_update(svc, q, body, code):
    """POST {"status": .., "amount": ..} to change a resource."""
    if not isinstance(body, dict) or "status" not in body or "amount" not in body:
        raise ValidationError('Send {"status": "available|limited|offline", "amount": number}')
    svc.update_resource(code, body["status"], body["amount"])
    return {"code": code, "status": body["status"], "amount": body["amount"]}


def plan(svc, q):
    """Allocation plan for ?strategy=risk_first|population_first."""
    strategy = q.get("strategy", "risk_first")
    result = svc.plan(strategy)
    result["assignments"] = [{"resource": r, "location": l, "people_per_day": round(p, 1)}
                             for r, l, p in result["assignments"]]
    return result


def plan_compare(svc, q):
    """Population-first (A) vs risk-first (B)."""
    return svc.compare()


def scenario(svc, q, body=None):
    """Scenario Lab via GET query parameters or a POST JSON body."""
    params = body if isinstance(body, dict) else {k: v for k, v in q.items() if k != "run"}
    result = svc.scenario(params)
    return {"params": result["params"], "placed_centres": result["placed_centres"],
            "limited_by": result["limited_by"], "extra_cost_per_day": result["extra_cost_per_day"],
            "comparison": result["comparison"]}


def query(svc, q, name):
    """Run one of the named SQL summaries in queries.py."""
    if name not in QUERIES:
        raise NotFoundError("Unknown query. Known: " + ", ".join(QUERIES))
    title, rows = run_query(svc.db, name)
    return {"title": title, "sql": QUERIES[name]["sql"].strip(), "rows": rows}


def config(svc, q):
    """The method's numbers (weights, bounds, thresholds)."""
    return {"weights": settings.RISK_WEIGHTS, "hazard": settings.HAZARD_INDICATORS,
            "exposure": settings.EXPOSURE_INDICATORS, "vulnerability": settings.VULNERABILITY_INDICATORS,
            "capacity": settings.CAPACITY_INDICATORS, "categories": settings.CATEGORIES,
            "heat_index_bands": settings.HEAT_INDEX_BANDS, "demand_rates": settings.DEMAND_RATES,
            "strategies": STRATEGIES}
