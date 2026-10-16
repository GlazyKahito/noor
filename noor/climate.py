"""Climate calculations: heat index, hazard indicators and explorer tables (NumPy + Pandas)."""
import math

import numpy as np
import pandas as pd

from . import settings


def heat_index(t_c, rh):
    """Heat index (feels-like temperature) in deg C from temperature (deg C) and humidity (%).

    Formula: US National Weather Service heat index equation (Rothfusz regression, in
    Fahrenheit) with the NWS low/high humidity adjustments. Below about 27 C (80 F) the
    simpler NWS formula is used. Returns None if either input is missing.

    Limitation: NOOR has daily maximum temperature and daily MEAN humidity. Humidity at the
    hottest hour is usually lower, so this can overstate the afternoon heat index.
    """
    if t_c is None or rh is None or pd.isna(t_c) or pd.isna(rh):
        return None
    t = t_c * 9 / 5 + 32  # to Fahrenheit
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    if (simple + t) / 2 < 80:
        hi = simple
    else:
        hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh
              - 0.00683783 * t * t - 0.05481717 * rh * rh + 0.00122874 * t * t * rh
              + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
        if rh < 13 and 80 <= t <= 112:
            hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t - 95)) / 17)
        elif rh > 85 and 80 <= t <= 87:
            hi += ((rh - 85) / 10) * ((87 - t) / 5)
    return round((hi - 32) * 5 / 9, 1)  # back to Celsius


def longest_run(flags):
    """Length of the longest run of consecutive True values in a list/array of booleans."""
    best = 0
    current = 0
    for flag in flags:
        if flag:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def daily_window(df, as_of, delta_t=0.0):
    """One row per day from (as_of - WINDOW_DAYS + 1) to (as_of + FORECAST_DAYS).

    `df` holds one location's rows (columns date, is_forecast, t_max, t_min, humidity).
    Days with no row become NaN, so gaps are visible instead of silently skipped.
    `delta_t` adds degrees to t_max and t_min (used by the Scenario Lab).
    """
    as_of = pd.Timestamp(as_of)
    days = pd.date_range(as_of - pd.Timedelta(days=settings.WINDOW_DAYS - 1),
                         as_of + pd.Timedelta(days=settings.FORECAST_DAYS))
    data = df.copy()
    data["date"] = pd.to_datetime(data["date"])
    # observed rows only up to as_of; forecast rows only after it
    keep = ((data["is_forecast"] == 0) & (data["date"] <= as_of)) | ((data["is_forecast"] == 1) & (data["date"] > as_of))
    data = data[keep].drop_duplicates("date", keep="last").set_index("date")
    table = data.reindex(days)[["t_max", "t_min", "humidity", "is_forecast"]].astype(float)
    table["t_max"] = table["t_max"] + delta_t
    table["t_min"] = table["t_min"] + delta_t
    table["heat_index"] = [heat_index(t, h) for t, h in zip(table["t_max"], table["humidity"])]
    table["heat_index"] = table["heat_index"].astype(float)
    table["is_forecast"] = (table.index > as_of).astype(int)
    table.index.name = "date"
    return table


def hazard_inputs(df, as_of, delta_t=0.0, extra_hot_days=0):
    """Raw hazard numbers for one location: peak heat index, peak Tmax, hot-day run, warm nights.

    Returns a dict. If fewer than MIN_OBSERVED_DAYS observed days exist in the window, the
    four values are None ("insufficient data"); a missing day is never filled in.
    """
    table = daily_window(df, as_of, delta_t)
    observed = table[table["is_forecast"] == 0]
    observed_days = int(observed["t_max"].notna().sum())
    missing_days = [d.strftime("%Y-%m-%d") for d in observed.index[observed["t_max"].isna()]]
    result = {"observed_days": observed_days, "missing_days": missing_days, "table": table,
              "peak_heat_index": None, "peak_tmax": None, "hot_days": None, "warm_nights": None}
    if observed_days < settings.MIN_OBSERVED_DAYS:
        return result
    tmax = table["t_max"].to_numpy()
    tmin = table["t_min"].to_numpy()
    hi = table["heat_index"].to_numpy()
    if not np.all(np.isnan(hi)):
        result["peak_heat_index"] = float(np.nanmax(hi))
    result["peak_tmax"] = float(np.nanmax(tmax))
    run = longest_run(tmax >= settings.HOT_DAY_C)  # NaN >= 40 is False, so a gap breaks the run
    result["hot_days"] = float(run + extra_hot_days) if run > 0 else 0.0
    if not np.all(np.isnan(tmin)):
        result["warm_nights"] = float(np.sum(tmin >= settings.WARM_NIGHT_C))
    return result


def latest_observed_date(df):
    """Latest date with an observed (not forecast) temperature, or None."""
    observed = df[(df["is_forecast"] == 0) & df["t_max"].notna()]
    if observed.empty:
        return None
    return str(observed["date"].max())


# ----------------------------------------------------------------------------- explorer
def explorer_table(df, start, end):
    """Daily table for one location between start and end, with a row for every missing day."""
    days = pd.date_range(start, end)
    data = df[df["is_forecast"] == 0].copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.drop_duplicates("date", keep="last").set_index("date").reindex(days)
    data.index.name = "date"
    data["heat_index"] = [heat_index(t, h) for t, h in zip(data["t_max"], data["humidity"])]
    data["missing"] = data["t_max"].isna()
    data["source_kind"] = data["source_kind"].fillna("missing")  # label days with no row
    return data[["t_max", "t_min", "humidity", "heat_index", "source_kind", "missing"]]


def summary_stats(values):
    """Mean, minimum, maximum and standard deviation of a series, ignoring missing days (NumPy)."""
    array = np.asarray(values, dtype=float)
    array = array[~np.isnan(array)]  # boolean mask keeps only real numbers
    if array.size == 0:
        return {"count": 0, "mean": None, "min": None, "max": None, "std": None}
    return {"count": int(array.size), "mean": float(np.mean(array)), "min": float(np.min(array)),
            "max": float(np.max(array)), "std": float(np.std(array))}


def location_comparison(df):
    """Per-location summary: mean/max Tmax, mean humidity, days observed, days missing (groupby)."""
    observed = df[df["is_forecast"] == 0].copy()
    observed["date"] = pd.to_datetime(observed["date"])
    summary = observed.groupby("location").agg(
        name=("name", "first"),
        mean_tmax=("t_max", "mean"),
        max_tmax=("t_max", "max"),
        mean_tmin=("t_min", "mean"),
        mean_humidity=("humidity", "mean"),
        days_observed=("t_max", "count"),
        first_day=("date", "min"),
        last_day=("date", "max"),
    )
    span = (summary["last_day"] - summary["first_day"]).dt.days + 1
    summary["days_missing"] = span - summary["days_observed"]
    numbers = ["mean_tmax", "max_tmax", "mean_tmin", "mean_humidity"]
    summary[numbers] = summary[numbers].round(1)
    return summary.reset_index()


def monthly_means(df):
    """Mean Tmax and humidity per month across the given rows (groupby on month)."""
    observed = df[df["is_forecast"] == 0].copy()
    observed["month"] = pd.to_datetime(observed["date"]).dt.strftime("%Y-%m")
    return observed.groupby("month")[["t_max", "t_min", "humidity"]].mean().round(1).reset_index()
