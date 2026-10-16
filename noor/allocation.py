"""Resource allocation with a simple greedy loop.

Demand (people per day) for a resource type in a location:
    demand = population * DEMAND_RATES[type] * risk_score / 100
(a location without a score uses 50, a precautionary middle value; a location without a
population has unknown demand and is listed separately, not dropped silently).

Greedy loop:
1. Sort locations by priority — "risk_first": risk score x population (default);
   "population_first": population only (a simpler baseline to compare against).
2. For each location in that order, for each resource type, take capacity from the
   nearest resources of that type that can reach it, until its demand is met or the
   resources run out.

This is a transparent heuristic, not an optimum, and it has not been validated against
real operations. Every assumption is in settings.py and can be changed.
"""
from . import settings
from .exceptions import ValidationError

STRATEGIES = {
    "risk_first": "Highest risk score x population first",
    "population_first": "Largest population first (ignores risk)",
}
PRECAUTIONARY_SCORE = 50.0
HIGH_CATEGORIES = ("High", "Severe", "Extreme")


class AllocationPlanner:
    """Plans which resource serves which location.

    Aggregation: the planner only *uses* Location and Resource objects that exist elsewhere;
    they keep existing after the planner is gone.
    """

    def __init__(self, locations, resources, assessments):
        """locations: Location objects; resources: Resource objects; assessments: {code: {score, category}}."""
        self.locations = locations
        self.resources = resources
        self.assessments = assessments
        self._by_code = {loc.code: loc for loc in locations}

    def score_of(self, code):
        """Risk score used for demand and priority (precautionary 50 when unknown)."""
        score = self.assessments.get(code, {}).get("score")
        return PRECAUTIONARY_SCORE if score is None else score

    def demand(self):
        """{location code: {type: people per day or None}}."""
        table = {}
        for loc in self.locations:
            table[loc.code] = {}
            for rtype, rate in settings.DEMAND_RATES.items():
                if loc.population is None:
                    table[loc.code][rtype] = None
                else:
                    table[loc.code][rtype] = loc.population * rate * self.score_of(loc.code) / 100
        return table

    def priority_order(self, strategy):
        """Locations sorted by the strategy's priority (highest first)."""
        if strategy == "risk_first":
            def key(loc):
                return self.score_of(loc.code) * (loc.population or 0)
        elif strategy == "population_first":
            def key(loc):
                return loc.population or 0
        else:
            raise ValidationError("Strategy must be one of: " + ", ".join(STRATEGIES))
        return sorted(self.locations, key=key, reverse=True)

    def run(self, strategy="risk_first"):
        """Run the greedy loop and return a result dict (see summarise())."""
        demand = self.demand()
        order = self.priority_order(strategy)
        left = {res.code: res.capacity() for res in self.resources}  # capacity still free
        served = {loc.code: {t: 0.0 for t in settings.DEMAND_RATES} for loc in self.locations}
        assignments = []
        for loc in order:
            for rtype in settings.DEMAND_RATES:
                need = demand[loc.code][rtype]
                if not need:
                    continue
                # resources of this type that reach the location, nearest first
                options = []
                for res in self.resources:
                    home = self._by_code.get(res.location_code)
                    if res.type_name == rtype and home is not None and res.serves(home, loc):
                        options.append((home.distance_to(loc), res.code, res))
                options.sort(key=lambda option: (option[0], option[1]))
                for _, _, res in options:
                    give = min(need, left[res.code])
                    if give <= 0:
                        continue
                    left[res.code] -= give
                    need -= give
                    served[loc.code][rtype] += give
                    assignments.append((res.code, loc.code, give))
                    if need <= 0:
                        break
        return self.summarise(strategy, demand, served, left, assignments)

    def summarise(self, strategy, demand, served, left, assignments):
        """Totals per type, per location and per resource, plus headline numbers."""
        by_type = {}
        for rtype in settings.DEMAND_RATES:
            total_demand = sum(d[rtype] for d in demand.values() if d[rtype] is not None)
            total_served = sum(served[c][rtype] for c in served if demand[c][rtype] is not None)
            capacity = sum(r.capacity() for r in self.resources if r.type_name == rtype)
            used = sum(r.capacity() - left[r.code] for r in self.resources if r.type_name == rtype)
            by_type[rtype] = {
                "demand": round(total_demand), "served": round(total_served),
                "unmet": round(total_demand - total_served),
                "coverage": round(total_served / total_demand, 3) if total_demand else None,
                "capacity": round(capacity), "utilisation": round(used / capacity, 3) if capacity else None,
            }
        rows = []
        weighted_need = 0.0
        weighted_served = 0.0
        high_unmet = []
        for loc in self.locations:
            row = {"code": loc.code, "name": loc.name, "population": loc.population,
                   "score": self.assessments.get(loc.code, {}).get("score"),
                   "category": self.assessments.get(loc.code, {}).get("category")}
            gap = False
            for rtype in settings.DEMAND_RATES:
                d = demand[loc.code][rtype]
                s = served[loc.code][rtype]
                row[rtype + "_demand"] = None if d is None else round(d)
                row[rtype + "_served"] = None if d is None else round(s)
                row[rtype + "_coverage"] = None if not d else round(s / d, 3)
                if d:
                    weighted_need += self.score_of(loc.code) * d
                    weighted_served += self.score_of(loc.code) * s
                    if d - s > 0.5:
                        gap = True
            if gap and row["category"] in HIGH_CATEGORIES:
                high_unmet.append(loc.code)
            rows.append(row)
        resources = [{"code": r.code, "name": r.name, "type": r.type_name, "status": r.status,
                      "capacity": round(r.capacity()), "used": round(r.capacity() - left[r.code]),
                      "utilisation": round((r.capacity() - left[r.code]) / r.capacity(), 3) if r.capacity() else None}
                     for r in self.resources]
        total_demand = sum(v["demand"] for v in by_type.values())
        total_served = sum(v["served"] for v in by_type.values())
        return {
            "strategy": strategy,
            "by_type": by_type,
            "locations": rows,
            "resources": resources,
            "assignments": assignments,
            "total_demand": total_demand,
            "total_served": total_served,
            "total_unmet": total_demand - total_served,
            "risk_weighted_coverage": round(weighted_served / weighted_need, 3) if weighted_need else None,
            "high_risk_with_gaps": high_unmet,
            "unknown_demand": [loc.code for loc in self.locations if loc.population is None],
        }


def compare_plans(plan_a, plan_b):
    """Side-by-side numbers for two plan results (B minus A)."""
    rows = []
    for rtype in settings.DEMAND_RATES:
        a = plan_a["by_type"][rtype]
        b = plan_b["by_type"][rtype]
        rows.append({"type": rtype, "served_a": a["served"], "served_b": b["served"],
                     "unmet_a": a["unmet"], "unmet_b": b["unmet"], "difference": b["served"] - a["served"]})
    return {
        "rows": rows,
        "risk_weighted_a": plan_a["risk_weighted_coverage"],
        "risk_weighted_b": plan_b["risk_weighted_coverage"],
        "high_gaps_a": plan_a["high_risk_with_gaps"],
        "high_gaps_b": plan_b["high_risk_with_gaps"],
    }
