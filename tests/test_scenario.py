"""Tests for the Scenario Lab on the synthetic district."""
import unittest

from noor import settings
from noor.database import Database
from noor.exceptions import ValidationError
from noor.scenario import Scenario
from noor.service import NoorService


class ScenarioValidationTests(unittest.TestCase):
    """Parameters are checked before anything runs."""

    def test_defaults(self):
        self.assertEqual(Scenario().params["temperature_increase"], 0.0)

    def test_out_of_range(self):
        with self.assertRaises(ValidationError):
            Scenario(temperature_increase=10)

    def test_unknown_parameter(self):
        with self.assertRaises(ValidationError):
            Scenario(rainfall=5)

    def test_whole_numbers(self):
        with self.assertRaises(ValidationError):
            Scenario(new_cooling_centres=1.5)

    def test_text_rejected(self):
        with self.assertRaises(ValidationError):
            Scenario(temperature_increase="hot")

    def test_budget_and_staff_limit_centres(self):
        cost, staff = settings.NEW_CENTRE["daily_cost"], settings.NEW_CENTRE["staff"]
        self.assertEqual(Scenario(new_cooling_centres=10, budget_per_day=cost * 3, staff_available=1000).affordable_centres, 3)
        self.assertEqual(Scenario(new_cooling_centres=10, budget_per_day=10**6, staff_available=staff * 2).affordable_centres, 2)


class ScenarioRunTests(unittest.TestCase):
    """Run against the seeded demo data (in memory)."""

    @classmethod
    def setUpClass(cls):
        cls.db = Database(":memory:")
        cls.svc = NoorService(cls.db)
        cls.svc.setup()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_no_change_means_no_difference(self):
        c = self.svc.scenario({})["comparison"]
        self.assertEqual(c["mean_score_before"], c["mean_score_after"])
        self.assertEqual(c["unmet_before"], c["unmet_after"])

    def test_warming_raises_risk(self):
        c = self.svc.scenario({"temperature_increase": 3})["comparison"]
        self.assertGreater(c["mean_score_after"], c["mean_score_before"])
        self.assertGreaterEqual(c["high_after"], c["high_before"])

    def test_new_centres_cut_cooling_shortfall(self):
        result = self.svc.scenario({"new_cooling_centres": 4})
        cooling = [r for r in result["comparison"]["by_type"] if r["type"] == "cooling_centre"][0]
        self.assertEqual(len(result["placed_centres"]), 4)
        self.assertLess(cooling["unmet_after"], cooling["unmet_before"])
        self.assertEqual(result["extra_cost_per_day"], 4 * settings.NEW_CENTRE["daily_cost"])

    def test_budget_limit_reported(self):
        result = self.svc.scenario({"new_cooling_centres": 10, "budget_per_day": 30000})
        self.assertEqual(len(result["placed_centres"]), 2)
        self.assertIn("budget", result["limited_by"])

    def test_more_water_capacity_reduces_water_shortfall(self):
        result = self.svc.scenario({"water_capacity_pct": 200})
        water = [r for r in result["comparison"]["by_type"] if r["type"] == "water_point"][0]
        self.assertLess(water["unmet_after"], water["unmet_before"])

    def test_original_resources_untouched(self):
        before = [r.amount for r in self.svc.resources()]
        self.svc.scenario({"water_capacity_pct": 300, "new_cooling_centres": 3})
        self.assertEqual(before, [r.amount for r in self.svc.resources()])


if __name__ == "__main__":
    unittest.main()
