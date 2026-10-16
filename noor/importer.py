"""Checking an uploaded observations CSV with Pandas before anything is saved.

Required columns: location_code, date, t_max, t_min, humidity
Optional column:  is_forecast (0 or 1, default 0)

A row is rejected (and reported with its line number) if:
* the location code is unknown, or the date is not YYYY-MM-DD,
* a number is not a number or is outside its range (t_max -40..60, t_min -50..50, humidity 0..100),
* all three values are empty, or t_max < t_min,
* an observed date is in the future, or a forecast date is more than 16 days ahead,
* it repeats an earlier row (same location, date and is_forecast).
Good rows are kept; bad rows are listed. Empty cells are allowed and stay missing (NaN).
"""
import io
from datetime import date, timedelta

import pandas as pd

from .exceptions import ValidationError

REQUIRED = ["location_code", "date", "t_max", "t_min", "humidity"]
RANGES = {"t_max": (-40, 60), "t_min": (-50, 50), "humidity": (0, 100)}
MAX_ROWS = 20000
MAX_BYTES = 2_000_000
MAX_ERRORS_SHOWN = 100


def read_upload(data):
    """Bytes -> DataFrame of strings. Raises ValidationError for unreadable files."""
    if len(data) > MAX_BYTES:
        raise ValidationError(f"File is larger than {MAX_BYTES // 1_000_000} MB")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("File must be UTF-8 text (save it as CSV UTF-8)") from None
    if not text.strip():
        raise ValidationError("File is empty")
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, skip_blank_lines=True)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValidationError(f"Could not read the CSV: {exc}") from None
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValidationError("Missing column(s): " + ", ".join(missing))
    if df.empty:
        raise ValidationError("The file has a header but no rows")
    if len(df) > MAX_ROWS:
        raise ValidationError(f"Too many rows ({len(df)}); the limit is {MAX_ROWS}")
    return df


def validate(df, known_codes, today=None):
    """Return (clean DataFrame, list of error dicts). Clean rows have proper types."""
    today = pd.Timestamp(today or date.today())
    df = df.copy()
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    if "is_forecast" not in df.columns:
        df["is_forecast"] = "0"
    df.loc[df["is_forecast"] == "", "is_forecast"] = "0"
    errors = []

    def flag(mask, column, message):
        """Record an error for every row where mask is True."""
        for idx in df.index[mask]:
            errors.append({"line": int(idx) + 2, "column": column, "message": message})

    flag(~df["location_code"].isin(known_codes), "location_code", "unknown location code")
    flag(~df["is_forecast"].isin(["0", "1"]), "is_forecast", "must be 0 or 1")
    dates = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
    flag(dates.isna(), "date", "not a YYYY-MM-DD date")
    observed_future = (df["is_forecast"] == "0") & (dates > today)
    flag(observed_future, "date", "observed date is in the future")
    flag((df["is_forecast"] == "1") & (dates > today + timedelta(days=16)), "date", "forecast more than 16 days ahead")

    numbers = {}
    for col, (low, high) in RANGES.items():
        values = pd.to_numeric(df[col], errors="coerce")
        flag((df[col] != "") & values.isna(), col, "not a number")
        flag(values.notna() & ((values < low) | (values > high)), col, f"outside {low}..{high}")
        numbers[col] = values
    flag(numbers["t_max"].isna() & numbers["t_min"].isna() & numbers["humidity"].isna(), "*", "no values in row")
    flag(numbers["t_max"] < numbers["t_min"], "t_min", "t_min is higher than t_max")
    flag(df.duplicated(subset=["location_code", "date", "is_forecast"], keep="first"), "*", "duplicate row")

    bad_lines = {e["line"] for e in errors}
    good = [i for i in df.index if int(i) + 2 not in bad_lines]
    clean = pd.DataFrame({
        "location_code": df.loc[good, "location_code"],
        "date": dates[good].dt.strftime("%Y-%m-%d"),
        "is_forecast": df.loc[good, "is_forecast"].astype(int),
        "t_max": numbers["t_max"][good],
        "t_min": numbers["t_min"][good],
        "humidity": numbers["humidity"][good],
    })
    errors.sort(key=lambda e: e["line"])
    return clean, errors
