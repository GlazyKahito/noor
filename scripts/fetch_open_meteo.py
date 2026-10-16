"""Download real (model-derived) daily weather from Open-Meteo into a NOOR import CSV.

Open-Meteo (https://open-meteo.com) offers free weather data for non-commercial use under
CC BY 4.0. Past days come from its archive (reanalysis models), not from weather stations,
so import the file with data kind "model_derived", never "measured".

Usage (from the project folder):
    python scripts/fetch_open_meteo.py LOCATION_CODE LATITUDE LONGITUDE START END [OUT.csv]
    python scripts/fetch_open_meteo.py AHD-01 23.03 72.58 2026-05-01 2026-05-31 ahmedabad.csv

Then open Data & sources in NOOR and import the CSV (the location code must exist in NOOR).
Attribution: "Weather data by Open-Meteo.com" (CC BY 4.0).
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

import pandas as pd

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = "temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean"


def build_url(lat, lon, start, end):
    """Archive API URL for daily max/min temperature and mean humidity (Indian time zone)."""
    query = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
                                    "daily": DAILY, "timezone": "Asia/Kolkata"})
    return f"{ARCHIVE_URL}?{query}"


def fetch(lat, lon, start, end, timeout=20):
    """Call the API and return the decoded JSON. Raises RuntimeError with a readable message."""
    try:
        with urllib.request.urlopen(build_url(lat, lon, start, end), timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Open-Meteo returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not reach Open-Meteo: {exc}") from None
    except ValueError:
        raise RuntimeError("Open-Meteo sent something that is not JSON") from None


def to_frame(payload, location_code):
    """Turn the API's JSON into NOOR's import columns."""
    daily = payload.get("daily")
    if not daily or "time" not in daily:
        raise RuntimeError("Response has no daily data")
    return pd.DataFrame({
        "location_code": location_code,
        "date": daily["time"],
        "t_max": daily.get("temperature_2m_max"),
        "t_min": daily.get("temperature_2m_min"),
        "humidity": daily.get("relative_humidity_2m_mean"),
        "is_forecast": 0,
    })


def check_args(lat, lon, start, end):
    """Validate the command-line values before calling the network."""
    lat, lon = float(lat), float(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("latitude must be -90..90 and longitude -180..180")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first or (last - first).days > 366:
        raise ValueError("END must be after START and at most a year later")
    if last >= date.today():
        raise ValueError("the archive only covers past days")
    return lat, lon


def main(argv):
    """Command-line entry point."""
    if len(argv) not in (6, 7):
        print(__doc__)
        return 2
    code, lat, lon, start, end = argv[1:6]
    out = argv[6] if len(argv) == 7 else f"{code}-open-meteo.csv"
    try:
        lat, lon = check_args(lat, lon, start, end)
        frame = to_frame(fetch(lat, lon, start, end), code)
    except (ValueError, RuntimeError) as exc:
        print("Error:", exc)
        return 1
    frame.to_csv(out, index=False)
    missing = int(frame["t_max"].isna().sum())
    print(f"Wrote {len(frame)} days to {out} ({missing} without temperature). Import it as 'model_derived'.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
