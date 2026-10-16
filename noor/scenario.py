"""Scenario Lab: change the inputs, rerun the same risk and allocation code, compare.

This is a what-if calculation with NOOR's own method. It is not a prediction of what would
really happen, and it has not been validated against real heatwaves.
"""
from . import settings
from .allocation import AllocationPlanner
from .exceptions import ValidationError
from .models import make_resource
from .risk import assess_all

# name: (minimum, maximum, default)
LIMITS = {
    "temperature_increase": (0.0, 6.0, 0.0),     # deg C added to every Tmax and Tmin
    "extra_hot_days": (0, 10, 0),                # days added to the current hot spell
    "new_cooling_centres": (0, 30, 0),           # hypothetical centres to add
    "water_capacity_pct": (25, 300, 100),        # % of today's water-point capacity
    "medical_capacity_pct": (25, 300, 100),      # % of today's medical-unit capacity
    "budget_per_day": (0, 5_000_000, 150_000),   # INR per day available for new centres
    "staff_available": (0, 1000, 40),            # extra staff available for new centres
}
WHOLE_NUMBERS = ("extra_hot_days", "new_cooling_centres", "water_capacity_pct", "medical_capacity_pct",
                 "budget_per_day", "staff_available")


class Scenario:
    """One set of what-if parameters, validated when it is created."""

    def __init__(self, **params):
        """Unknown names are rejected; missing ones take their default."""
        unknown = set(params) - set(LIMITS)
        if unknown:
            raise ValidationError("Unknown scenario setting(s): " + ", ".join(sorted(unknown)))
        self._params = {}
        for name, (low, high, default) in LIMITS.items():
            self._params[name] = self.check(name, params.get(name, default), low, high)

    @staticmethod
    def check(name, value, low, high):
        """Convert to a number and make sure it is inside its limits."""
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValidationError(f"{name} must be a number") from None
        if not low <= value <= high:
            raise ValidationError(f"{name} must be between {low} and {high}")
        if name in WHOLE_NUMBERS:
            if value != int(value):
                raise ValidationError(f"{name} must be a whole number")
            return int(value)
        return value

    @property
    def params(self):
        """A copy of the validated parameters."""
        return dict(self._params)

    @property
    def affordable_centres(self):
        """How many of the requested centres the budget and staff allow."""
        by_budget = self._params["budget_per_day"] // settings.NEW_CENTRE["daily_cost"]
        by_staff = self._params["staff_available"] // settings.NEW_CENTRE["staff"]
        return int(min(self._params["new_cooling_centres"], by_budget, by_staff))

    def adjusted_resources(self, resources):
        """New Resource objects with water and medical capacity scaled (originals untouched)."""
        result = []
        for res in resources:
            amount = res.amount
            if res.type_name == "water_point":
                amount = amount * self._params["water_capacity_pct"] / 100
            elif res.type_name == "medical_unit":
                amount = amount * self._params["medical_capacity_pct"] / 100
            result.append(make_resource(res.type_name, code=res.code, name=res.name,
                                        location_code=res.location_code, amount=amount, status=res.status,
                                        radius_km=res.radius_km, staff=res.staff, daily_cost=res.daily_cost,
                                        kind=res.kind))
        return result

    def run(self, locations, resources, obs_by_code, as_of_by_code):
        """Return baseline, scenario and comparison numbers."""
        p = self._params
        baseline = evaluate(locations, resources, obs_by_code, as_of_by_code)

        changed = self.adjusted_resources(resources)
        placed = []
        if self.affordable_centres > 0:
            stressed = evaluate(locations, changed, obs_by_code, as_of_by_code,
                                p["temperature_increase"], p["extra_hot_days"])
            plan = stressed["plan"]
            for i in range(self.affordable_centres):
                best_code, best_value = None, 0.0
                for row in plan["locations"]:
                    d, s = row["cooling_centre_demand"], row["cooling_centre_served"]
                    if not d or d - s <= 0.5:
                        continue
                    value = (row["score"] or 50) * (d - s)  # risk-weighted unmet cooling demand
                    if value > best_value:
                        best_code, best_value = row["code"], value
                if best_code is None:
                    break
                centre = make_resource("cooling_centre", code=f"NEW-{i + 1:02d}", name=f"New cooling centre {i + 1}",
                                       location_code=best_code, amount=settings.NEW_CENTRE["places"],
                                       radius_km=settings.NEW_CENTRE["radius_km"], staff=settings.NEW_CENTRE["staff"],
                                       daily_cost=settings.NEW_CENTRE["daily_cost"], kind="synthetic")
                changed.append(centre)
                placed.append(best_code)
                planner = AllocationPlanner(locations, changed, stressed["by_code"])
                plan = planner.run("risk_first")

        after = evaluate(locations, changed, obs_by_code, as_of_by_code,
                         p["temperature_increase"], p["extra_hot_days"])
        limited_by = []
        if self.affordable_centres < p["new_cooling_centres"]:
            if p["budget_per_day"] // settings.NEW_CENTRE["daily_cost"] < p["new_cooling_centres"]:
                limited_by.append("budget")
            if p["staff_available"] // settings.NEW_CENTRE["staff"] < p["new_cooling_centres"]:
                limited_by.append("staff")
        return {
            "params": p,
            "placed_centres": placed,
            "limited_by": limited_by,
            "extra_cost_per_day": len(placed) * settings.NEW_CENTRE["daily_cost"],
            "baseline": baseline,
            "scenario": after,
            "comparison": compare(baseline, after),
        }


def evaluate(locations, resources, obs_by_code, as_of_by_code, delta_t=0.0, extra_hot_days=0):
    """Risk for all locations, then a risk-first allocation plan."""
    results = assess_all(locations, resources, obs_by_code, as_of_by_code, None, delta_t, extra_hot_days)
    by_code = {r["code"]: r for r in results}
    plan = AllocationPlanner(locations, resources, by_code).run("risk_first")
    scores = [r["score"] for r in results if r["score"] is not None]
    return {
        "results": results,
        "by_code": by_code,
        "plan": plan,
        "mean_score": round(sum(scores) / len(scores), 1) if scores else None,
        "high_or_above": sum(1 for r in results if r["category"] in ("High", "Severe", "Extreme")),
    }


def compare(before, after):
    """Location-by-location and headline differences."""
    rows = []
    for r in after["results"]:
        b = before["by_code"][r["code"]]
        change = None if r["score"] is None or b["score"] is None else round(r["score"] - b["score"], 1)
        rows.append({"code": r["code"], "name": r["name"], "score_before": b["score"], "score_after": r["score"],
                     "change": change, "category_before": b["category"], "category_after": r["category"]})
    by_type = []
    for rtype in settings.DEMAND_RATES:
        bt, at = before["plan"]["by_type"][rtype], after["plan"]["by_type"][rtype]
        by_type.append({"type": rtype, "unmet_before": bt["unmet"], "unmet_after": at["unmet"],
                        "coverage_before": bt["coverage"], "coverage_after": at["coverage"],
                        "utilisation_before": bt["utilisation"], "utilisation_after": at["utilisation"]})
    still = [row for row in after["plan"]["locations"] if row["code"] in after["plan"]["high_risk_with_gaps"]]
    return {
        "locations": rows,
        "by_type": by_type,
        "mean_score_before": before["mean_score"], "mean_score_after": after["mean_score"],
        "high_before": before["high_or_above"], "high_after": after["high_or_above"],
        "unmet_before": before["plan"]["total_unmet"], "unmet_after": after["plan"]["total_unmet"],
        "still_needing_help": [{"code": r["code"], "name": r["name"], "category": r["category"]} for r in still],
    }
