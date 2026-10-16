"""CSV reports. Each starts with '#' lines saying when, from what data and how it was made."""
import io

import pandas as pd

from . import settings
from .database import now_utc

LIMITATIONS = ("Decision support only; not an official warning. Thresholds and weights are NOOR defaults "
               "(see settings.py), not validated against health outcomes.")
METHODS = {
    "risk": "score = 100 x (0.40 hazard + 0.20 exposure + 0.25 vulnerability + 0.15 (1 - capacity)); "
            "min-max normalised indicators; missing dimensions use 0.5, not 0.",
    "alerts": "Fixed if/elif threshold rules in noor/alerts.py (NWS heat-index bands; NOOR hot-spell, warm-night, "
              "risk and capacity rules).",
    "allocation": "Greedy loop: locations by risk x population, nearest reachable resources first; "
                  "demand = population x planning rate x score / 100.",
    "scenario": "Same risk and allocation code rerun on changed inputs; a what-if, not a prediction.",
    "observations": "Stored daily rows; empty cells are missing values.",
    "vulnerability": "Raw indicator shares and the vulnerability dimension (0-1) from the risk engine.",
}


def safe(value):
    """Stop spreadsheet apps from running text that starts with = + - @ as a formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def to_csv(frame, title, method_key, data_note):
    """DataFrame -> CSV text with a provenance header."""
    frame = frame.map(safe) if not frame.empty else frame
    header = [
        f"# NOOR report: {title}",
        f"# Generated: {now_utc()}",
        f"# Data: {data_note}",
        f"# Method: {METHODS[method_key]}",
        f"# Limitations: {LIMITATIONS}",
    ]
    buffer = io.StringIO()
    buffer.write("\n".join(header) + "\n")
    frame.to_csv(buffer, index=False, lineterminator="\n")
    return buffer.getvalue()


def risk_report(assessments, data_note):
    """Latest risk assessment per location."""
    cols = ["code", "name", "as_of_date", "score", "category", "confidence", "hazard", "exposure",
            "vulnerability", "capacity", "reasons"]
    frame = pd.DataFrame(assessments)
    frame = frame[cols] if not frame.empty else pd.DataFrame(columns=cols)
    return to_csv(frame, "Regional heat-risk summary", "risk", data_note)


def vulnerability_report(locations, assessments, data_note):
    """Vulnerability inputs next to the computed vulnerability dimension."""
    scores = {a["code"]: a for a in assessments}
    rows = []
    for loc in locations:
        a = scores.get(loc["code"], {})
        rows.append({"code": loc["code"], "name": loc["name"], "population": loc["population"],
                     "elderly_share": loc["elderly_share"], "children_share": loc["children_share"],
                     "outdoor_worker_share": loc["outdoor_worker_share"],
                     "poor_housing_share": loc["poor_housing_share"], "low_income_share": loc["low_income_share"],
                     "vulnerability": a.get("vulnerability"), "category": a.get("category"),
                     "data_kind": loc["source_kind"]})
    return to_csv(pd.DataFrame(rows), "Vulnerability assessment", "vulnerability", data_note)


def alerts_report(alerts, data_note):
    """All alerts with their status."""
    cols = ["id", "code", "name", "severity", "rule", "message", "trigger_value", "threshold", "period",
            "status", "issued_at", "actions", "confidence"]
    frame = pd.DataFrame(alerts)
    frame = frame[cols] if not frame.empty else pd.DataFrame(columns=cols)
    return to_csv(frame, "Alert report", "alerts", data_note)


def allocation_report(plan, data_note):
    """Per-location demand and served numbers for one plan."""
    frame = pd.DataFrame(plan["locations"])
    return to_csv(frame, f"Allocation plan ({plan['strategy']})", "allocation", data_note)


def scenario_report(result, data_note):
    """Before/after per location for one scenario run."""
    frame = pd.DataFrame(result["comparison"]["locations"])
    params = ", ".join(f"{k}={v}" for k, v in result["params"].items())
    return to_csv(frame, f"Scenario comparison ({params})", "scenario", data_note)


def observations_report(frame, data_note):
    """Raw observations (one row per location per day)."""
    return to_csv(frame, "Climate observations", "observations", data_note)


def data_note(status):
    """Short provenance line from NoorService.status()."""
    kinds = ", ".join(settings.DATA_KINDS.get(k, k) for k in status["data_kinds"]) or "none"
    note = f"kinds in use: {kinds}; latest observation {status['latest_observation']}"
    if status["synthetic_only"]:
        note += "; ALL DATA IS SYNTHETIC DEMONSTRATION DATA"
    return note
