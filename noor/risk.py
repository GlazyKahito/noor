"""Heat-risk scoring.

Method (all numbers in settings.py):
1. Each raw indicator is min-max normalised to 0..1 with fixed bounds: (x - low) / (high - low),
   clipped to 0..1.
2. Inside each of the four dimensions — hazard, exposure, vulnerability, capacity — the
   normalised indicators are combined by a weighted average over the indicators that exist.
   Missing indicators are left out (their weight is shared by the others), never counted as 0.
3. score = 100 * (wH*hazard + wE*exposure + wV*vulnerability + wC*(1 - capacity))
   A dimension with no data at all uses MISSING_DIMENSION_VALUE (0.5) and lowers confidence.
4. If hazard is below 0.2 (a cool week), the score is capped just under "High" so that
   vulnerability alone can never produce a high heat-risk warning.
"""
from datetime import date

import numpy as np
import pandas as pd

from . import settings
from .climate import hazard_inputs
from .exceptions import ValidationError

LOW_HAZARD = 0.2
LOW_HAZARD_CAP = 39.9

LABELS = {
    "peak_heat_index": ("Peak heat index", "°C"),
    "peak_tmax": ("Peak max temperature", "°C"),
    "hot_days": ("Consecutive hot days", "days"),
    "warm_nights": ("Warm nights", "nights"),
    "density": ("Population density", "per km²"),
    "population": ("Population", "people"),
    "elderly_share": ("Residents aged 65+", "share"),
    "children_share": ("Children under 5", "share"),
    "outdoor_worker_share": ("Outdoor workers", "share"),
    "poor_housing_share": ("Informal / heat-trapping housing", "share"),
    "low_income_share": ("Low-income households", "share"),
    "cooling_per_1000": ("Cooling places per 1,000", "places"),
    "water_per_1000": ("Water servings per 1,000", "people"),
    "medical_per_1000": ("Medical slots per 1,000", "patients"),
    "piped_water_share": ("Households with piped water", "share"),
}


def normalise(value, low, high):
    """Min-max normalise one value to 0..1 (clipped). None stays None."""
    if value is None:
        return None
    if high <= low:
        raise ValidationError("Normalisation needs low < high")
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def category_for(score):
    """Category name for a 0-100 score using settings.CATEGORIES (lower bound inclusive)."""
    if score is None:
        return "Insufficient data"
    if not 0 <= score <= 100:
        raise ValidationError("Score must be between 0 and 100")
    for threshold, name in settings.CATEGORIES:
        if score >= threshold:
            return name
    return settings.CATEGORIES[-1][1]


def resource_capacity_per_1000(locations, resources):
    """Cooling, water and medical capacity per 1,000 residents for each location.

    Each resource's capacity() (people per day) is shared between the locations inside its
    service radius in proportion to their population. Locations without a population get None.
    `locations` are models.Location objects, `resources` are models.Resource objects.
    """
    by_code = {loc.code: loc for loc in locations}
    totals = {loc.code: {"cooling_centre": 0.0, "water_point": 0.0, "medical_unit": 0.0} for loc in locations}
    for res in resources:
        if res.type_name not in ("cooling_centre", "water_point", "medical_unit"):
            continue
        home = by_code.get(res.location_code)
        if home is None:
            continue
        served = [loc for loc in locations if loc.population and res.serves(home, loc)]
        people = sum(loc.population for loc in served)
        for loc in served:
            totals[loc.code][res.type_name] += res.capacity() * loc.population / people
    result = {}
    for loc in locations:
        if not loc.population:
            result[loc.code] = {"cooling_per_1000": None, "water_per_1000": None, "medical_per_1000": None}
            continue
        t = totals[loc.code]
        result[loc.code] = {
            "cooling_per_1000": t["cooling_centre"] / loc.population * 1000,
            "water_per_1000": t["water_point"] / loc.population * 1000,
            "medical_per_1000": t["medical_unit"] / loc.population * 1000,
        }
    return result


class RiskEngine:
    """Scores locations with configurable dimension weights."""

    def __init__(self, weights=None):
        """Use settings.RISK_WEIGHTS unless other weights are given (they are validated)."""
        self.weights = self.check_weights(weights or settings.RISK_WEIGHTS)

    @staticmethod
    def check_weights(weights):
        """Weights must be the four known keys, each 0..1, adding up to 1, hazard above 0."""
        keys = set(settings.RISK_WEIGHTS)
        if set(weights) != keys:
            raise ValidationError("Weights need exactly: " + ", ".join(sorted(keys)))
        clean = {}
        for key, value in weights.items():
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValidationError(f"Weight '{key}' must be a number") from None
            if not 0 <= value <= 1:
                raise ValidationError(f"Weight '{key}' must be between 0 and 1")
            clean[key] = value
        if abs(sum(clean.values()) - 1.0) > 0.001:
            raise ValidationError(f"Weights must add up to 1.0 (they add up to {sum(clean.values()):.2f})")
        if clean["hazard"] <= 0:
            raise ValidationError("Hazard weight must be above 0: this is a heat-risk score")
        return clean

    @staticmethod
    def dimension(raw, indicators):
        """Combine one dimension's indicators.

        raw: {indicator: raw value or None}; indicators: {indicator: (low, high, weight)}.
        Returns (value or None, coverage 0..1, detail rows).
        """
        details = []
        values = []
        weights = []
        total_weight = 0.0
        for name, (low, high, weight) in indicators.items():
            total_weight += weight
            norm = normalise(raw.get(name), low, high)
            details.append({"indicator": name, "raw": raw.get(name), "normalised": norm, "weight": weight})
            if norm is not None:
                values.append(norm)
                weights.append(weight)
        if not values:
            return None, 0.0, details
        value = float(np.average(values, weights=weights))  # weighted average of present indicators
        return value, sum(weights) / total_weight, details

    def assess(self, location, obs_df, as_of, capacity_inputs, delta_t=0.0, extra_hot_days=0):
        """Assess one location.

        location: models.Location; obs_df: its observation rows; as_of: date string;
        capacity_inputs: dict from resource_capacity_per_1000 for this location.
        """
        hz = hazard_inputs(obs_df, as_of, delta_t, extra_hot_days)
        hazard, h_cov, h_rows = self.dimension(hz, settings.HAZARD_INDICATORS)
        exposure, e_cov, e_rows = self.dimension(
            {"density": location.density, "population": location.population}, settings.EXPOSURE_INDICATORS)
        vulnerability, v_cov, v_rows = self.dimension(
            {name: location.get_share(name) for name in settings.VULNERABILITY_INDICATORS},
            settings.VULNERABILITY_INDICATORS)
        cap_raw = dict(capacity_inputs)
        cap_raw["piped_water_share"] = location.get_share("piped_water_share")
        capacity, c_cov, c_rows = self.dimension(cap_raw, settings.CAPACITY_INDICATORS)

        imputed = []
        score = None
        if hazard is not None:
            e = exposure
            v = vulnerability
            c = capacity
            if e is None:
                e = settings.MISSING_DIMENSION_VALUE
                imputed.append("exposure")
            if v is None:
                v = settings.MISSING_DIMENSION_VALUE
                imputed.append("vulnerability")
            if c is None:
                c = settings.MISSING_DIMENSION_VALUE
                imputed.append("capacity")
            w = self.weights
            score = 100 * (w["hazard"] * hazard + w["exposure"] * e + w["vulnerability"] * v
                           + w["lack_of_capacity"] * (1 - c))
            if hazard < LOW_HAZARD:
                score = min(score, LOW_HAZARD_CAP)
            score = round(score, 1)

        all_rows = h_rows + e_rows + v_rows + c_rows
        completeness = sum(1 for r in all_rows if r["normalised"] is not None) / len(all_rows)
        latest = obs_df[(obs_df["is_forecast"] == 0) & obs_df["t_max"].notna()]["date"].max() if len(obs_df) else None
        age = None
        if isinstance(latest, str):
            age = (date.fromisoformat(str(as_of)[:10]) - date.fromisoformat(latest[:10])).days
        confidence = self.confidence(completeness, age, imputed)

        result = {
            "code": location.code, "name": location.name, "as_of": str(as_of),
            "hazard": rounded(hazard), "exposure": rounded(exposure),
            "vulnerability": rounded(vulnerability), "capacity": rounded(capacity),
            "score": score, "category": category_for(score), "confidence": confidence,
            "completeness": round(completeness, 2), "data_age_days": age, "imputed": imputed,
            "observed_days": hz["observed_days"], "missing_days": hz["missing_days"],
            "details": {"hazard": h_rows, "exposure": e_rows, "vulnerability": v_rows, "capacity": c_rows},
            "daily": hz["table"],
        }
        result["reasons"] = self.reasons(result)
        return result

    @staticmethod
    def confidence(completeness, age_days, imputed):
        """high / medium / low from how complete and how recent the data is."""
        if age_days is None:
            return "low"
        if completeness >= 0.85 and age_days <= 2 and not imputed:
            return "high"
        if completeness >= 0.6 and age_days <= 7:
            return "medium"
        return "low"

    def reasons(self, result):
        """Plain-language explanation built only from the computed numbers."""
        if result["score"] is None:
            return [f"No score: only {result['observed_days']} of {settings.WINDOW_DAYS} days have a temperature "
                    f"reading (at least {settings.MIN_OBSERVED_DAYS} needed)."]
        lines = [f"Score {result['score']} = {result['category']}."]
        # the three indicators pushing the score up the most
        pushes = []
        dim_weight = {"hazard": self.weights["hazard"], "exposure": self.weights["exposure"],
                      "vulnerability": self.weights["vulnerability"], "capacity": self.weights["lack_of_capacity"]}
        for dim, rows in result["details"].items():
            total = sum(r["weight"] for r in rows)
            for r in rows:
                if r["normalised"] is None:
                    continue
                level = 1 - r["normalised"] if dim == "capacity" else r["normalised"]
                pushes.append((dim_weight[dim] * r["weight"] / total * level, dim, r))
        pushes.sort(key=lambda p: p[0], reverse=True)
        for _, dim, r in pushes[:3]:
            label, unit = LABELS[r["indicator"]]
            lines.append(f"{label}: {format_value(r['raw'], unit)} ({dim}).")
        if result["hazard"] is not None and result["hazard"] < LOW_HAZARD:
            lines.append("Heat hazard is low this week, so the score is capped below High.")
        for dim in result["imputed"]:
            lines.append(f"No {dim} data: used the precautionary value {settings.MISSING_DIMENSION_VALUE}, not zero.")
        missing = [LABELS[r["indicator"]][0] for rows in result["details"].values() for r in rows
                   if r["raw"] is None]
        if missing:
            lines.append("Missing: " + ", ".join(missing) + ".")
        if result["missing_days"]:
            lines.append(f"{len(result['missing_days'])} day(s) without observations in the window.")
        return lines


def rounded(value):
    """Round to 3 decimals, keeping None."""
    return None if value is None else round(value, 3)


def format_value(value, unit):
    """Readable value with unit for explanations."""
    if value is None:
        return "missing"
    if unit == "share":
        return f"{value * 100:.0f}%"
    if unit in ("people", "per km²"):
        return f"{value:,.0f} {unit}"
    if unit == "°C":
        return f"{value:.1f} °C"
    return f"{value:.1f} {unit}"


EMPTY_OBSERVATIONS = pd.DataFrame(columns=["date", "is_forecast", "t_max", "t_min", "humidity"])


def assess_all(locations, resources, obs_by_code, as_of_by_code, engine=None, delta_t=0.0, extra_hot_days=0):
    """Assess every location. Returns a list of result dicts (same order as `locations`).

    obs_by_code: {location code: DataFrame of its observations}
    as_of_by_code: {location code: 'YYYY-MM-DD' date the assessment is made for}
    """
    engine = engine or RiskEngine()
    capacity = resource_capacity_per_1000(locations, resources)
    results = []
    for loc in locations:
        obs = obs_by_code.get(loc.code, EMPTY_OBSERVATIONS)
        results.append(engine.assess(loc, obs, as_of_by_code[loc.code], capacity[loc.code],
                                     delta_t, extra_hot_days))
    return results
