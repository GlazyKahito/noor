"""Text and table rows shown on screen, built only from computed numbers.

Shared by the desktop app (noor/gui) and the website (noor/web), so both say exactly the same
thing. Nothing here touches Tkinter or HTTP.
"""
from datetime import datetime, timedelta, timezone

from . import settings
from .allocation import HIGH_CATEGORIES
from .models import RESOURCE_CLASSES
from .risk import LABELS, format_value

RULE_LABELS = {
    "heat_index": "Heat index",
    "hot_spell": "Hot spell",
    "warm_nights": "Warm nights",
    "risk_category": "Risk category",
    "cooling_gap": "Cooling gap",
    "stale_data": "Stale data",
}
TYPE_LABELS = {name: cls.label for name, cls in RESOURCE_CLASSES.items()}
STRATEGY_LABELS = {"risk_first": "Risk-first (risk score × population)",
                   "population_first": "Population-first (baseline)"}
DIMENSION_NAMES = {"hazard": "Hazard", "exposure": "Exposure", "vulnerability": "Vulnerability",
                   "capacity": "Response capacity"}
WEIGHT_LABELS = {"hazard": "Hazard", "exposure": "Exposure", "vulnerability": "Vulnerability",
                 "lack_of_capacity": "Lack of capacity"}
IST = timezone(timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------------------- formatting
def fmt(value, digits=0, unit=""):
    """Number with thousands separators; an em dash for missing values."""
    if value is None or value != value:  # None or NaN
        return "—"
    text = f"{value:,.{digits}f}"
    return f"{text} {unit}".strip()


def limit_range(low, high):
    """'0 to 5,000,000' or '0 to 6' for a Scenario Lab setting (no scientific notation)."""
    def show(v):
        return f"{v:,.0f}" if float(v) == int(v) else f"{v:g}"
    return f"{show(low)} to {show(high)}"


def pct(value):
    """0.734 -> '73%'; missing -> em dash."""
    return "—" if value is None else f"{value * 100:.0f}%"


def when(stamp, tz=None):
    """'2026-10-17T10:48:01Z' (UTC) -> '17 Oct 2026, 16:18' in local time (or the given time zone)."""
    if not stamp:
        return "—"
    try:
        moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return stamp
    return moment.astimezone(tz).strftime("%d %b %Y, %H:%M")


# ---------------------------------------------------------------------------- overview
def overview_numbers(svc):
    """The headline numbers of the Overview screen."""
    db = svc.db
    latest = db.latest_assessments()
    locations = db.list_locations()
    active = db.list_alerts(status="active")
    resources = db.list_resources()
    status = svc.status()
    high = [a for a in latest if a["category"] in HIGH_CATEGORIES]
    severity = {s: sum(1 for a in active if a["severity"] == s) for s in ("emergency", "warning", "advisory")}
    by_status = {s: sum(1 for r in resources if r["status"] == s) for s in ("available", "limited", "offline")}
    return {
        "latest": latest, "locations": locations, "active": active, "resources": resources, "status": status,
        "high": high, "severity": severity, "by_status": by_status,
        "regions": len({l["region"] for l in locations}),
        "assessed_at": latest[0]["assessed_at"] if latest else None,
    }


def situation_summary(svc, numbers):
    """Bullet lines for 'Situation summary', written from the computed numbers."""
    latest, high, active, severity = numbers["latest"], numbers["high"], numbers["active"], numbers["severity"]
    lines = []
    scored = [a for a in latest if a["score"] is not None]
    if not latest:
        lines.append("No assessments yet. Press Recalculate risk.")
    else:
        as_of = max(a["as_of_date"] for a in latest)
        names = ", ".join(f"{a['name']} ({a['category']})" for a in high[:4])
        lines.append(f"As of {as_of}, {len(high)} of {len(latest)} locations are at High risk or above"
                     + (f": {names}" + (" and others." if len(high) > 4 else ".") if high else "."))
        if scored:
            top = scored[0]  # latest_assessments() is ordered by score, highest first
            reasons = top["reasons"].split(" | ")
            lines.append(f"Highest score: {top['name']} ({top['code']}) at {top['score']:.1f}, {top['category']}. "
                         + (reasons[1] if len(reasons) > 1 else ""))
    lines.append(f"{len(active)} active alerts: {severity['emergency']} emergency, {severity['warning']} warning, "
                 f"{severity['advisory']} advisory.")
    plan = svc.plan("risk_first")
    coverage = plan["total_served"] / plan["total_demand"] if plan["total_demand"] else None
    lines.append(f"The risk-first resource plan can serve {pct(coverage)} of estimated daily demand "
                 f"(risk-weighted coverage {pct(plan['risk_weighted_coverage'])}); "
                 f"{len(plan['high_risk_with_gaps'])} high-risk location(s) still have unmet needs.")
    if numbers["status"]["synthetic_only"]:
        lines.append("All data is synthetic demonstration data for a fictional district, not IMD observations.")
    lines.append("NOOR supports preparedness. It does not replace IMD or SDMA warnings.")
    return lines


def recent_activity(db, limit=12):
    """Latest recalculation, alerts and saved plans, newest first: [{time, event}]."""
    events = []
    batch = db.fetch_one("SELECT MAX(assessed_at) AS t, COUNT(*) AS n FROM risk_assessments "
                         "WHERE assessed_at = (SELECT MAX(assessed_at) FROM risk_assessments)")
    if batch["t"]:
        events.append({"time": batch["t"], "event": f"Risk recalculated for {batch['n']} locations"})
    for a in db.fetch_all("""SELECT a.id, a.issued_at, a.severity, a.rule, l.name
                             FROM alerts a JOIN locations l ON l.id = a.location_id
                             ORDER BY a.issued_at DESC, a.id DESC LIMIT 8"""):
        events.append({"time": a["issued_at"], "event": f"{a['severity'].title()} alert: {a['name']} "
                                                       f"({RULE_LABELS.get(a['rule'], a['rule'])})"})
    for p in db.list_plans()[:4]:
        events.append({"time": p["created_at"], "event": f"Plan saved: {p['plan_name']}"})
    events.sort(key=lambda e: e["time"], reverse=True)
    return events[:limit]


# ---------------------------------------------------------------------------- risk
def method_text():
    """The formula and thresholds, read from settings.py so they always match the code."""
    w = settings.RISK_WEIGHTS
    bands = ", ".join(f"{name} ≥ {threshold:.0f}" for threshold, name in settings.CATEGORIES)
    return (f"Score = 100 × ({w['hazard']:.2f} × hazard + {w['exposure']:.2f} × exposure + "
            f"{w['vulnerability']:.2f} × vulnerability + {w['lack_of_capacity']:.2f} × (1 − capacity)). "
            f"Each dimension is a weighted average of min-max normalised indicators (0 = best, 1 = worst). "
            f"Categories: {bands}. A dimension with no data uses {settings.MISSING_DIMENSION_VALUE}, not 0. "
            f"Fewer than {settings.MIN_OBSERVED_DAYS} observed days in the {settings.WINDOW_DAYS}-day window "
            f"gives 'Insufficient data'.")


def recommended_actions(db, code):
    """Actions from the location's open (not resolved) alerts, without repeats."""
    open_alerts = [a for a in db.list_alerts() if a["code"] == code and a["status"] != "resolved"]
    actions = []
    for alert in open_alerts:
        for action in alert["actions"].split(" | "):
            if action and action not in actions:
                actions.append(action)
    if not actions:
        return ["No warning rule has fired for this location; continue routine monitoring."]
    return actions + [f"From {len(open_alerts)} open alert(s) for this location (see the Alerts screen)."]


def indicator_rows(result):
    """Every indicator the risk engine used for one location."""
    rows = []
    for dim, items in result["details"].items():
        for item in items:
            label, unit = LABELS[item["indicator"]]
            rows.append({"id": item["indicator"], "dimension": DIMENSION_NAMES[dim], "indicator": label,
                         "value": format_value(item["raw"], unit), "normalised": item["normalised"],
                         "weight": item["weight"]})
    return rows


def data_note_for(result):
    """One line about the data behind an assessment."""
    return (f"Assessed as of {result['as_of']}: {result['observed_days']} observed day(s) in the "
            f"{settings.WINDOW_DAYS}-day window, {len(result['missing_days'])} missing; "
            f"{result['completeness'] * 100:.0f}% of indicators available.")


# ---------------------------------------------------------------------------- scenario
def scenario_explanation(result):
    """Plain sentences built only from the calculated scenario numbers."""
    p, c = result["params"], result["comparison"]
    lines = [f"Settings: +{p['temperature_increase']:g} °C, {p['extra_hot_days']} extra hot day(s), "
             f"{p['new_cooling_centres']} new centre(s) requested, water {p['water_capacity_pct']}%, "
             f"medical {p['medical_capacity_pct']}%, budget ₹{p['budget_per_day']:,}/day, "
             f"{p['staff_available']} staff."]
    if c["mean_score_before"] is not None and c["mean_score_after"] is not None:
        diff = c["mean_score_after"] - c["mean_score_before"]
        lines.append(f"The mean risk score moves from {c['mean_score_before']:.1f} to {c['mean_score_after']:.1f} "
                     f"({diff:+.1f}); {c['high_after']} location(s) are High or above, against {c['high_before']} "
                     f"today.")
    moved = [r for r in c["locations"] if r["category_before"] != r["category_after"]]
    if moved:
        lines.append("Category changes: " + "; ".join(f"{r['name']} {r['category_before']} → {r['category_after']}"
                                                      for r in moved[:6]) + ("…" if len(moved) > 6 else "."))
    else:
        lines.append("No location changes category.")
    if result["placed_centres"]:
        lines.append("New cooling centres placed at: " + ", ".join(result["placed_centres"]) + ".")
    if result["limited_by"]:
        lines.append("Fewer centres than requested could be placed: limited by "
                     + " and ".join(result["limited_by"]) + ".")
    lines.append(f"Unmet demand changes from {fmt(c['unmet_before'])} to {fmt(c['unmet_after'])} per day.")
    if c["still_needing_help"]:
        lines.append("Still needing intervention: " + ", ".join(f"{r['name']} ({r['category']})"
                                                                 for r in c["still_needing_help"]) + ".")
    return lines


def plan_location_rows(plan):
    """Per-location 'served / demand' text for each resource type."""
    rows = []
    for r in plan["locations"]:
        row = {"code": r["code"], "name": r["name"], "category": r["category"]}
        for t in settings.DEMAND_RATES:
            d, s = r[t + "_demand"], r[t + "_served"]
            row[t] = "—" if d is None else f"{fmt(s)} / {fmt(d)}"
        rows.append(row)
    return rows
