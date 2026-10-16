"""Shared test helpers: tiny hand-made datasets so each test's numbers are easy to follow."""
import pandas as pd

from noor.models import Location, make_resource


def daily_frame(as_of, t_max, t_min=None, humidity=None, forecast=0):
    """Observation rows ending on `as_of`: len(t_max) observed days, then `forecast` forecast days.

    t_max may contain None for a missing day. Forecast days repeat the last values.
    """
    days = pd.date_range(end=pd.Timestamp(as_of), periods=len(t_max))
    t_min = t_min or [t - 12 if t is not None else None for t in t_max]
    humidity = humidity or [30.0] * len(t_max)
    rows = []
    for day, tx, tn, h in zip(days, t_max, t_min, humidity):
        if tx is None:
            continue
        rows.append({"date": day.strftime("%Y-%m-%d"), "is_forecast": 0, "t_max": tx, "t_min": tn, "humidity": h})
    for i in range(1, forecast + 1):
        day = pd.Timestamp(as_of) + pd.Timedelta(days=i)
        rows.append({"date": day.strftime("%Y-%m-%d"), "is_forecast": 1, "t_max": t_max[-1], "t_min": t_min[-1],
                     "humidity": humidity[-1]})
    return pd.DataFrame(rows, columns=["date", "is_forecast", "t_max", "t_min", "humidity"])


def location(code="T-01", population=50000, area=5.0, x=0.0, y=0.0, **shares):
    """A test Location with sensible default shares (override any of them)."""
    defaults = {"elderly_share": 0.09, "children_share": 0.09, "outdoor_worker_share": 0.2,
                "poor_housing_share": 0.3, "low_income_share": 0.3, "piped_water_share": 0.7}
    defaults.update(shares)
    return Location(code, f"Test {code}", population, area, x, y, **defaults)


def resource(rtype="cooling_centre", code="R-01", where="T-01", amount=100, status="available", radius=3.0):
    """A test Resource of any type."""
    return make_resource(rtype, code=code, name=f"Test {code}", location_code=where, amount=amount,
                         status=status, radius_km=radius)
