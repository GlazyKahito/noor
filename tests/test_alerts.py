"""Tests for each warning rule at and around its threshold."""
import unittest

from helpers import daily_frame

from noor import settings
from noor.alerts import (CoolingGapRule, HeatIndexRule, HotSpellRule, RiskCategoryRule, StaleDataRule,
                         WarmNightsRule, WarningEngine, runs_reaching)
from noor.climate import daily_window

AS_OF = "2026-06-04"


def context(t_max, t_min=None, humidity=None, forecast=0, **extra):
    """A rule context built from simple temperature lists."""
    frame = daily_frame(AS_OF, t_max, t_min, humidity, forecast)
    ctx = {"code": "T-01", "name": "Test", "as_of": AS_OF, "daily": daily_window(frame, AS_OF),
           "category": "Moderate", "score": 30.0, "confidence": "high", "data_age_days": 0,
           "cooling_coverage": 1.0, "synthetic": False}
    ctx.update(extra)
    return ctx


class RunTests(unittest.TestCase):
    """Only runs that are still going on (or forecast) count."""

    def test_run_must_reach_as_of(self):
        flags = [True, True, True, False, False]
        self.assertEqual(runs_reaching(flags, [1, 2, 3, 4, 5], 5)[0], 0)
        self.assertEqual(runs_reaching([False, True, True], [1, 2, 3], 3)[0], 2)


class HeatIndexRuleTests(unittest.TestCase):
    """NWS bands: advisory 32.2, warning 39.4, emergency 51.7 deg C."""

    def test_below_all_bands(self):
        self.assertIsNone(HeatIndexRule().check(context([25.0] * 7, humidity=[30.0] * 7)))

    def test_band_reached(self):
        alert = HeatIndexRule().check(context([44.0] * 7, humidity=[25.0] * 7))
        self.assertEqual(alert.severity, "warning")
        self.assertGreaterEqual(alert.value, 39.4)
        self.assertIn("IMD", alert.confidence)

    def test_emergency_with_humid_heat(self):
        alert = HeatIndexRule().check(context([42.0] * 7, humidity=[60.0] * 7))
        self.assertEqual(alert.severity, "emergency")

    def test_only_today_and_forecast_count(self):
        hot_then_cool = [46.0, 46.0, 46.0, 46.0, 46.0, 46.0, 25.0]
        alert = HeatIndexRule().check(context(hot_then_cool, humidity=[30.0] * 7))
        self.assertIsNone(alert)


class HotSpellRuleTests(unittest.TestCase):
    """Warning at 3 days, emergency at 5."""

    def test_two_days_nothing(self):
        self.assertIsNone(HotSpellRule().check(context([35, 35, 35, 35, 35, 41, 41])))

    def test_three_days_warning(self):
        alert = HotSpellRule().check(context([35, 35, 35, 35, 41, 41, 41]))
        self.assertEqual((alert.severity, alert.value), ("warning", 3))

    def test_exactly_threshold_temperature_counts(self):
        alert = HotSpellRule().check(context([35, 35, 35, 35] + [settings.HOT_DAY_C] * 3))
        self.assertEqual(alert.value, 3)

    def test_five_days_emergency(self):
        alert = HotSpellRule().check(context([35, 35, 41, 41, 41, 41, 41]))
        self.assertEqual(alert.severity, "emergency")

    def test_forecast_extends_spell(self):
        alert = HotSpellRule().check(context([35, 35, 35, 35, 35, 41, 41], forecast=1))
        self.assertEqual(alert.value, 3)

    def test_finished_spell_does_not_fire(self):
        self.assertIsNone(HotSpellRule().check(context([41, 41, 41, 41, 35, 35, 35])))


class OtherRuleTests(unittest.TestCase):
    """Warm nights, risk category, cooling gap and stale data."""

    def test_warm_nights(self):
        t_min = [20, 20, 20, 20, 20, 29, 29]
        alert = WarmNightsRule().check(context([40] * 7, t_min))
        self.assertEqual((alert.severity, alert.value), ("advisory", 2))
        self.assertIsNone(WarmNightsRule().check(context([40] * 7, [20] * 6 + [29])))

    def test_risk_category(self):
        self.assertIsNone(RiskCategoryRule().check(context([30] * 7, category="High", score=59.9)))
        self.assertEqual(RiskCategoryRule().check(context([30] * 7, category="Severe", score=60)).severity, "warning")
        self.assertEqual(RiskCategoryRule().check(context([30] * 7, category="Extreme", score=80)).severity, "emergency")

    def test_cooling_gap_boundary(self):
        rule = CoolingGapRule()
        self.assertIsNone(rule.check(context([30] * 7, category="High", cooling_coverage=0.5)))
        self.assertIsNotNone(rule.check(context([30] * 7, category="High", cooling_coverage=0.49)))
        self.assertIsNone(rule.check(context([30] * 7, category="Moderate", cooling_coverage=0.1)))
        self.assertIsNone(rule.check(context([30] * 7, category="High", cooling_coverage=None)))

    def test_stale_data(self):
        rule = StaleDataRule()
        self.assertIsNone(rule.check(context([30] * 7, data_age_days=3)))
        self.assertEqual(rule.check(context([30] * 7, data_age_days=4)).severity, "info")
        self.assertIsNotNone(rule.check(context([30] * 7, data_age_days=None)))

    def test_synthetic_label_in_note(self):
        alert = RiskCategoryRule().check(context([30] * 7, category="Extreme", score=85, synthetic=True))
        self.assertIn("synthetic", alert.confidence)

    def test_sms_preview_is_short(self):
        alert = HotSpellRule().check(context([41] * 7))
        self.assertLessEqual(len(alert.sms_preview()), 300)


class EngineTests(unittest.TestCase):
    """The engine runs every rule polymorphically."""

    def test_engine_collects_alerts(self):
        found = WarningEngine().run([context([46.0] * 7, [30.0] * 7, [25.0] * 7, category="Severe", score=65)])
        rules = {alert.rule for _code, alert in found}
        self.assertEqual(rules, {"heat_index", "hot_spell", "warm_nights", "risk_category"})

    def test_calm_week_has_no_alerts(self):
        self.assertEqual(WarningEngine().run([context([28.0] * 7, [18.0] * 7, [40.0] * 7)]), [])


if __name__ == "__main__":
    unittest.main()
