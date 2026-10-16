"""Tests for the heat index, normalisation, weighting, categories and missing-data handling."""
import unittest

from helpers import daily_frame, location, resource

from noor import settings
from noor.climate import hazard_inputs, heat_index, longest_run, summary_stats
from noor.exceptions import ValidationError
from noor.risk import RiskEngine, category_for, normalise, resource_capacity_per_1000

AS_OF = "2026-06-04"
HOT_WEEK = [44.0, 45.0, 44.5, 46.0, 45.5, 45.0, 46.5]


class HeatIndexTests(unittest.TestCase):
    """Values checked against the NWS heat index chart (Fahrenheit converted to Celsius)."""

    def test_chart_value_90F_50pct(self):
        # NWS chart: 90 F at 50 % humidity feels like about 95 F (35.0 C)
        self.assertAlmostEqual(heat_index(32.22, 50), 35.0, delta=0.6)

    def test_chart_value_100F_40pct(self):
        # NWS chart: 100 F at 40 % feels like about 109 F (42.8 C)
        self.assertAlmostEqual(heat_index(37.78, 40), 42.8, delta=0.8)

    def test_cool_air_uses_simple_formula(self):
        self.assertAlmostEqual(heat_index(20.0, 50), 20.0, delta=1.0)

    def test_humidity_raises_heat_index(self):
        self.assertGreater(heat_index(38, 70), heat_index(38, 30))

    def test_missing_input(self):
        self.assertIsNone(heat_index(None, 40))
        self.assertIsNone(heat_index(40, None))


class NormaliseTests(unittest.TestCase):
    """Min-max normalisation boundaries."""

    def test_bounds(self):
        self.assertEqual(normalise(10, 10, 20), 0.0)
        self.assertEqual(normalise(20, 10, 20), 1.0)
        self.assertEqual(normalise(15, 10, 20), 0.5)

    def test_clipping(self):
        self.assertEqual(normalise(-100, 10, 20), 0.0)
        self.assertEqual(normalise(100, 10, 20), 1.0)

    def test_missing_stays_missing(self):
        self.assertIsNone(normalise(None, 0, 1))

    def test_bad_bounds(self):
        with self.assertRaises(ValidationError):
            normalise(5, 10, 10)


class CategoryTests(unittest.TestCase):
    """Thresholds are lower-bound inclusive."""

    def test_exact_boundaries(self):
        self.assertEqual(category_for(0), "Low")
        self.assertEqual(category_for(19.99), "Low")
        self.assertEqual(category_for(20), "Moderate")
        self.assertEqual(category_for(40), "High")
        self.assertEqual(category_for(60), "Severe")
        self.assertEqual(category_for(80), "Extreme")
        self.assertEqual(category_for(100), "Extreme")

    def test_no_score(self):
        self.assertEqual(category_for(None), "Insufficient data")

    def test_out_of_range(self):
        for bad in (-0.1, 100.1):
            with self.assertRaises(ValidationError):
                category_for(bad)


class WeightTests(unittest.TestCase):
    """Weights are configurable but validated."""

    def test_defaults_add_up_to_one(self):
        self.assertAlmostEqual(sum(settings.RISK_WEIGHTS.values()), 1.0)

    def test_must_add_up_to_one(self):
        with self.assertRaises(ValidationError):
            RiskEngine({"hazard": 0.5, "exposure": 0.5, "vulnerability": 0.5, "lack_of_capacity": 0.5})

    def test_hazard_cannot_be_zero(self):
        with self.assertRaises(ValidationError):
            RiskEngine({"hazard": 0, "exposure": 0.4, "vulnerability": 0.4, "lack_of_capacity": 0.2})

    def test_missing_or_extra_keys(self):
        with self.assertRaises(ValidationError):
            RiskEngine({"hazard": 1.0})

    def test_text_weight(self):
        with self.assertRaises(ValidationError):
            RiskEngine({"hazard": "lots", "exposure": 0.4, "vulnerability": 0.4, "lack_of_capacity": 0.2})

    def test_strings_from_a_form_are_accepted(self):
        engine = RiskEngine({"hazard": "0.4", "exposure": "0.2", "vulnerability": "0.25", "lack_of_capacity": "0.15"})
        self.assertEqual(engine.weights["hazard"], 0.4)


class DimensionTests(unittest.TestCase):
    """Weighted averages leave missing indicators out instead of counting them as zero."""

    def test_missing_indicator_is_not_zero(self):
        indicators = {"a": (0, 1, 0.5), "b": (0, 1, 0.5)}
        value, coverage, _rows = RiskEngine.dimension({"a": 0.8, "b": None}, indicators)
        self.assertAlmostEqual(value, 0.8)      # not (0.8 + 0) / 2
        self.assertAlmostEqual(coverage, 0.5)

    def test_all_missing(self):
        value, coverage, _rows = RiskEngine.dimension({}, {"a": (0, 1, 1.0)})
        self.assertIsNone(value)
        self.assertEqual(coverage, 0.0)

    def test_weights_matter(self):
        indicators = {"a": (0, 1, 0.75), "b": (0, 1, 0.25)}
        value, _cov, _rows = RiskEngine.dimension({"a": 1.0, "b": 0.0}, indicators)
        self.assertAlmostEqual(value, 0.75)


class HazardTests(unittest.TestCase):
    """Hazard indicators from daily rows."""

    def test_longest_run(self):
        self.assertEqual(longest_run([True, True, False, True, True, True]), 3)
        self.assertEqual(longest_run([]), 0)

    def test_hot_week(self):
        hz = hazard_inputs(daily_frame(AS_OF, HOT_WEEK), AS_OF)
        self.assertEqual(hz["observed_days"], 7)
        self.assertEqual(hz["peak_tmax"], 46.5)
        self.assertEqual(hz["hot_days"], 7)

    def test_missing_day_breaks_run(self):
        week = [44, 44, 44, None, 44, 44, 44]
        hz = hazard_inputs(daily_frame(AS_OF, week), AS_OF)
        self.assertEqual(hz["hot_days"], 3)
        self.assertEqual(len(hz["missing_days"]), 1)

    def test_too_few_days_gives_no_hazard(self):
        hz = hazard_inputs(daily_frame(AS_OF, [None, None, None, None, None, 44, 45]), AS_OF)
        self.assertEqual(hz["observed_days"], 2)
        self.assertIsNone(hz["peak_heat_index"])

    def test_forecast_days_count(self):
        hz = hazard_inputs(daily_frame(AS_OF, HOT_WEEK, forecast=3), AS_OF)
        self.assertEqual(hz["hot_days"], 10)

    def test_summary_stats_ignore_missing(self):
        stats = summary_stats([40.0, None, 42.0, float("nan"), 44.0])
        self.assertEqual((stats["count"], stats["mean"], stats["min"], stats["max"]), (3, 42.0, 40.0, 44.0))
        self.assertAlmostEqual(stats["std"], 1.633, places=3)  # population std of 40, 42, 44
        self.assertIsNone(summary_stats([None])["mean"])

    def test_scenario_warming_raises_peak(self):
        base = hazard_inputs(daily_frame(AS_OF, HOT_WEEK), AS_OF)
        warmer = hazard_inputs(daily_frame(AS_OF, HOT_WEEK), AS_OF, delta_t=2.0)
        self.assertAlmostEqual(warmer["peak_tmax"] - base["peak_tmax"], 2.0)


class AssessTests(unittest.TestCase):
    """Whole-location assessments."""

    def assess(self, loc, frame=None, capacity=None):
        frame = daily_frame(AS_OF, HOT_WEEK) if frame is None else frame
        capacity = capacity or {"cooling_per_1000": 2.0, "water_per_1000": 20.0, "medical_per_1000": 0.2}
        return RiskEngine().assess(loc, frame, AS_OF, capacity)

    def test_score_in_range_and_explained(self):
        r = self.assess(location())
        self.assertTrue(0 <= r["score"] <= 100)
        self.assertEqual(r["category"], category_for(r["score"]))
        self.assertTrue(r["reasons"][0].startswith("Score"))
        self.assertEqual(r["confidence"], "high")

    def test_score_matches_formula(self):
        r = self.assess(location())
        w = settings.RISK_WEIGHTS
        expected = 100 * (w["hazard"] * r["hazard"] + w["exposure"] * r["exposure"] + w["vulnerability"]
                          * r["vulnerability"] + w["lack_of_capacity"] * (1 - r["capacity"]))
        self.assertAlmostEqual(r["score"], expected, delta=0.1)

    def test_missing_vulnerability_is_not_zero_vulnerability(self):
        none = {k: None for k in settings.VULNERABILITY_INDICATORS}
        zero = {k: 0.0 for k in settings.VULNERABILITY_INDICATORS}
        unknown = self.assess(location(**none))
        least = self.assess(location(**zero))
        self.assertIn("vulnerability", unknown["imputed"])
        self.assertGreater(unknown["score"], least["score"])  # unknown is treated as mid-range, not best case
        self.assertNotEqual(unknown["confidence"], "high")

    def test_missing_population_flags_exposure(self):
        r = self.assess(location(population=None))
        self.assertIn("exposure", r["imputed"])
        self.assertIsNone(r["exposure"])

    def test_insufficient_data(self):
        r = self.assess(location(), daily_frame(AS_OF, [None] * 5 + [44, 45]))
        self.assertIsNone(r["score"])
        self.assertEqual(r["category"], "Insufficient data")
        self.assertEqual(r["confidence"], "low")

    def test_cool_week_is_capped_below_high(self):
        cool = daily_frame(AS_OF, [30.0] * 7, [20.0] * 7)
        worst = {k: 1.0 for k in settings.VULNERABILITY_INDICATORS}
        r = self.assess(location(population=400000, area=5, **worst), cool,
                        {"cooling_per_1000": 0.0, "water_per_1000": 0.0, "medical_per_1000": 0.0})
        self.assertLess(r["hazard"], 0.2)
        self.assertLess(r["score"], 40)

    def test_more_capacity_lowers_score(self):
        weak = self.assess(location(), capacity={"cooling_per_1000": 0.0, "water_per_1000": 0.0, "medical_per_1000": 0.0})
        strong = self.assess(location(), capacity={"cooling_per_1000": 5.0, "water_per_1000": 50.0, "medical_per_1000": 0.5})
        self.assertLess(strong["score"], weak["score"])

    def test_old_data_lowers_confidence(self):
        frame = daily_frame("2026-05-31", [44.0] * 10)  # 3 days inside the window, 4 days old
        r = RiskEngine().assess(location(), frame, AS_OF, {"cooling_per_1000": 2, "water_per_1000": 20,
                                                           "medical_per_1000": 0.2})
        self.assertEqual(r["data_age_days"], 4)
        self.assertEqual(r["confidence"], "medium")


class CapacityShareTests(unittest.TestCase):
    """Resource capacity is shared by population within the radius."""

    def test_shared_by_population(self):
        a = location("A-01", population=1000, x=0)
        b = location("B-01", population=3000, x=2)
        c = location("C-01", population=1000, x=10)  # out of reach
        cap = resource_capacity_per_1000([a, b, c], [resource(where="A-01", amount=40, radius=3)])
        self.assertAlmostEqual(cap["A-01"]["cooling_per_1000"], 10.0)   # 40 * 1/4 per 1000 people
        self.assertAlmostEqual(cap["B-01"]["cooling_per_1000"], 10.0)   # 40 * 3/4 per 3000 people
        self.assertEqual(cap["C-01"]["cooling_per_1000"], 0.0)

    def test_unknown_population_gets_none(self):
        cap = resource_capacity_per_1000([location(population=None)], [resource()])
        self.assertIsNone(cap["T-01"]["cooling_per_1000"])


if __name__ == "__main__":
    unittest.main()
