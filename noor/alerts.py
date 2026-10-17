"""Early-warning rules: simple if/elif thresholds, one class per rule.

Each rule's check() looks at one location's context and returns an Alert or None. Rules do
not touch the database or the screen, so each one can be unit-tested on its own.

NOOR alerts support preparedness only. They do not replace warnings from the India
Meteorological Department (IMD), State Disaster Management Authorities or local officials.
"""
from abc import ABC, abstractmethod

import pandas as pd

from . import settings

DISCLAIMER = "Follow official IMD / SDMA warnings; NOOR does not replace them."


class Alert:
    """One warning for one location."""

    def __init__(self, rule, severity, message, value, threshold, period, actions, confidence):
        """Store the alert fields (see the alerts table)."""
        self.rule = rule
        self.severity = severity
        self.message = message
        self.value = value
        self.threshold = threshold
        self.period = period
        self.actions = actions
        self.confidence = confidence


class AlertRule(ABC):
    """Abstract rule. Subclasses override check()."""

    name = "rule"

    @abstractmethod
    def check(self, ctx):
        """Return an Alert or None for one location context."""

    @staticmethod
    def confidence_note(ctx):
        """Confidence text attached to every alert."""
        note = f"Data confidence: {ctx['confidence']}."
        if ctx.get("synthetic"):
            note += " Based on synthetic demonstration data (illustration only)."
        return note + " " + DISCLAIMER


def runs_reaching(flags, dates, as_of):
    """Longest run of consecutive True flags that is still going on or ahead (ends on/after as_of).

    Returns (length, first date, last date); (0, None, None) if there is none.
    """
    best = (0, None, None)
    start = None
    length = 0
    for i, flag in enumerate(flags):
        if flag:
            if length == 0:
                start = dates[i]
            length += 1
            run_ends_here = i == len(flags) - 1 or not flags[i + 1]
            if run_ends_here and dates[i] >= as_of and length > best[0]:
                best = (length, start, dates[i])
        else:
            length = 0
    return best


def day(ts):
    """Timestamp -> 'YYYY-MM-DD'."""
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


class HeatIndexRule(AlertRule):
    """Heat index today or in the forecast reaches an NWS band."""

    name = "heat_index"

    def check(self, ctx):
        """Highest band reached by today's or a forecast day's heat index."""
        daily = ctx["daily"]
        upcoming = daily[daily.index >= pd.Timestamp(ctx["as_of"])]["heat_index"].dropna()
        if upcoming.empty:
            return None
        peak = float(upcoming.max())
        peak_day = day(upcoming.idxmax())
        for threshold, severity, label in settings.HEAT_INDEX_BANDS:  # highest band first
            if peak >= threshold:
                actions = {
                    "emergency": ["Activate the local heat action plan with the authorities.",
                                  "Put medical units on standby near the highest-risk wards."],
                    "warning": ["Open cooling centres for longer hours and publicise them.",
                                "Ask outreach teams to check on older people living alone."],
                    "advisory": ["Share heat-safety advice: water, shade, avoid midday sun.",
                                 "Check that drinking-water points are stocked."],
                }[severity]
                return Alert(self.name, severity,
                             f"{ctx['name']}: heat index {peak:.1f} °C on {peak_day} ({label} band starts at {threshold} °C).",
                             peak, threshold, f"{day(upcoming.index[0])} to {day(upcoming.index[-1])}",
                             actions, self.confidence_note(ctx))
        return None


class HotSpellRule(AlertRule):
    """Several consecutive days with Tmax >= HOT_DAY_C, still going on or forecast."""

    name = "hot_spell"

    def check(self, ctx):
        """Warning at 3+ days, emergency at 5+ days (settings)."""
        daily = ctx["daily"]
        flags = list(daily["t_max"] >= settings.HOT_DAY_C)
        length, first, last = runs_reaching(flags, list(daily.index), pd.Timestamp(ctx["as_of"]))
        if length >= settings.HOT_SPELL_EMERGENCY_DAYS:
            severity, threshold = "emergency", settings.HOT_SPELL_EMERGENCY_DAYS
        elif length >= settings.HOT_SPELL_WARNING_DAYS:
            severity, threshold = "warning", settings.HOT_SPELL_WARNING_DAYS
        else:
            return None
        return Alert(self.name, severity,
                     f"{ctx['name']}: {length} days in a row at or above {settings.HOT_DAY_C:.0f} °C.",
                     length, threshold, f"{day(first)} to {day(last)}",
                     ["Plan staff rotation for cooling centres and water points over several days.",
                      "Check stocks of oral rehydration salts at medical units."], self.confidence_note(ctx))


class WarmNightsRule(AlertRule):
    """Consecutive nights that stay warm, so bodies cannot recover."""

    name = "warm_nights"

    def check(self, ctx):
        """Advisory at 2+ consecutive warm nights."""
        daily = ctx["daily"]
        flags = list(daily["t_min"] >= settings.WARM_NIGHT_C)
        length, first, last = runs_reaching(flags, list(daily.index), pd.Timestamp(ctx["as_of"]))
        if length < settings.WARM_NIGHTS_ADVISORY:
            return None
        return Alert(self.name, "advisory",
                     f"{ctx['name']}: {length} nights in a row at or above {settings.WARM_NIGHT_C:.0f} °C.",
                     length, settings.WARM_NIGHTS_ADVISORY, f"{day(first)} to {day(last)}",
                     ["Check on vulnerable residents in the morning.",
                      "Consider keeping a cooling centre open in the evening."], self.confidence_note(ctx))


class RiskCategoryRule(AlertRule):
    """The combined NOOR risk score is Severe or Extreme."""

    name = "risk_category"

    def check(self, ctx):
        """Warning for Severe, emergency for Extreme."""
        if ctx["category"] == "Extreme":
            severity = "emergency"
        elif ctx["category"] == "Severe":
            severity = "warning"
        else:
            return None
        return Alert(self.name, severity,
                     f"{ctx['name']}: NOOR risk score {ctx['score']} ({ctx['category']}).",
                     ctx["score"], 80.0 if severity == "emergency" else 60.0, ctx["as_of"],
                     ["Prioritise this location in today's resource plan.",
                      "Confirm its vulnerability and capacity data are current."], self.confidence_note(ctx))


class CoolingGapRule(AlertRule):
    """A High-or-worse location where less than half the cooling demand can be met."""

    name = "cooling_gap"

    def check(self, ctx):
        """Advisory when cooling coverage < COOLING_GAP_SHARE."""
        coverage = ctx.get("cooling_coverage")
        if coverage is None or ctx["category"] not in ("High", "Severe", "Extreme"):
            return None
        if coverage >= settings.COOLING_GAP_SHARE:
            return None
        return Alert(self.name, "advisory",
                     f"{ctx['name']}: only {coverage * 100:.0f}% of estimated cooling demand can be met.",
                     round(coverage, 2), settings.COOLING_GAP_SHARE, ctx["as_of"],
                     ["Look for temporary cooling spaces (schools, halls) within reach.",
                      "Review the allocation plan for this ward."], self.confidence_note(ctx))


class StaleDataRule(AlertRule):
    """Observations are missing or old, so the score may understate the hazard."""

    name = "stale_data"

    def check(self, ctx):
        """Info alert if data is older than STALE_DATA_DAYS or absent."""
        age = ctx.get("data_age_days")
        if age is not None and age <= settings.STALE_DATA_DAYS:
            return None
        text = "no observations recorded" if age is None else f"latest observation is {age} days old"
        return Alert(self.name, "info", f"{ctx['name']}: {text}.", age, settings.STALE_DATA_DAYS, ctx["as_of"],
                     ["Update observations before relying on this location's score."], self.confidence_note(ctx))


class WarningEngine:
    """Runs every rule over every location (polymorphism: each rule has its own check())."""

    def __init__(self, rules=None):
        """Default rule set, or a custom list (handy in tests)."""
        self.rules = rules or [HeatIndexRule(), HotSpellRule(), WarmNightsRule(),
                               RiskCategoryRule(), CoolingGapRule(), StaleDataRule()]

    def run(self, contexts):
        """Return a list of (location code, Alert) pairs."""
        found = []
        for ctx in contexts:
            for rule in self.rules:
                alert = rule.check(ctx)
                if alert is not None:
                    found.append((ctx["code"], alert))
        return found
