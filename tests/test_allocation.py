"""Tests for the greedy allocation loop and capacity constraints."""
import unittest

from helpers import location, resource

from noor import settings
from noor.allocation import AllocationPlanner, compare_plans
from noor.exceptions import ValidationError


def scores(**by_code):
    """{'A-01': 70} -> assessment dicts."""
    return {code: {"score": s, "category": "Severe" if s and s >= 60 else "Moderate"} for code, s in by_code.items()}


class AllocationTests(unittest.TestCase):
    """Capacity, radius and priority rules."""

    def setUp(self):
        self.a = location("A-01", population=10000, x=0)
        self.b = location("B-01", population=10000, x=1)
        self.far = location("F-01", population=10000, x=50)

    def test_demand_formula(self):
        planner = AllocationPlanner([self.a], [], scores(**{"A-01": 80}))
        expected = 10000 * settings.DEMAND_RATES["cooling_centre"] * 80 / 100
        self.assertAlmostEqual(planner.demand()["A-01"]["cooling_centre"], expected)

    def test_capacity_never_exceeded(self):
        centre = resource(where="A-01", amount=100)
        plan = AllocationPlanner([self.a, self.b], [centre], scores(**{"A-01": 90, "B-01": 90})).run()
        used = sum(p for r, _l, p in plan["assignments"] if r == centre.code)
        self.assertLessEqual(used, centre.capacity() + 1e-9)

    def test_never_serves_more_than_demand(self):
        big = resource(where="A-01", amount=100000)
        plan = AllocationPlanner([self.a], [big], scores(**{"A-01": 50})).run()
        row = plan["locations"][0]
        self.assertEqual(row["cooling_centre_served"], row["cooling_centre_demand"])

    def test_radius_respected(self):
        centre = resource(where="A-01", amount=1000, radius=3)
        plan = AllocationPlanner([self.a, self.far], [centre], scores(**{"A-01": 10, "F-01": 99})).run()
        far_row = [r for r in plan["locations"] if r["code"] == "F-01"][0]
        self.assertEqual(far_row["cooling_centre_served"], 0)

    def test_risk_first_serves_highest_risk_when_scarce(self):
        centre = resource(where="A-01", amount=20)  # far less than demand
        plan = AllocationPlanner([self.a, self.b], [centre], scores(**{"A-01": 30, "B-01": 90})).run("risk_first")
        served = {r["code"]: r["cooling_centre_served"] for r in plan["locations"]}
        self.assertEqual(served["B-01"], 20)
        self.assertEqual(served["A-01"], 0)

    def test_population_first_ignores_risk(self):
        small = location("S-01", population=1000, x=1)
        centre = resource(where="A-01", amount=5)
        plan = AllocationPlanner([small, self.a], [centre], scores(**{"S-01": 99, "A-01": 20})).run("population_first")
        served = {r["code"]: r["cooling_centre_served"] for r in plan["locations"]}
        self.assertEqual(served["A-01"], 5)

    def test_offline_resource_gives_nothing(self):
        centre = resource(where="A-01", amount=500, status="offline")
        plan = AllocationPlanner([self.a], [centre], scores(**{"A-01": 90})).run()
        self.assertEqual(plan["assignments"], [])

    def test_unknown_population_listed_not_dropped(self):
        unknown = location("U-01", population=None, x=0)
        plan = AllocationPlanner([unknown], [resource(where="U-01")], scores(**{"U-01": 90})).run()
        self.assertEqual(plan["unknown_demand"], ["U-01"])

    def test_missing_score_uses_precautionary_value(self):
        planner = AllocationPlanner([self.a], [], scores(**{"A-01": None}))
        self.assertEqual(planner.score_of("A-01"), 50.0)

    def test_unknown_strategy(self):
        with self.assertRaises(ValidationError):
            AllocationPlanner([self.a], [], {}).run("random")

    def test_compare(self):
        centre = resource(where="A-01", amount=20)
        planner = AllocationPlanner([self.a, self.b], [centre], scores(**{"A-01": 30, "B-01": 90}))
        result = compare_plans(planner.run("population_first"), planner.run("risk_first"))
        self.assertEqual(len(result["rows"]), len(settings.DEMAND_RATES))
        self.assertGreaterEqual(result["risk_weighted_b"], result["risk_weighted_a"])


if __name__ == "__main__":
    unittest.main()
