"""Tests for the Open-Meteo script, using a saved-style response (no network needed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import fetch_open_meteo as om  # noqa: E402

from noor.importer import read_upload, validate  # noqa: E402

SAMPLE = {"daily": {"time": ["2026-05-01", "2026-05-02", "2026-05-03"],
                    "temperature_2m_max": [42.7, 43.8, None],
                    "temperature_2m_min": [28.0, 28.0, None],
                    "relative_humidity_2m_mean": [52, 54, 46]}}


class OpenMeteoTests(unittest.TestCase):
    """Parsing and argument checks."""

    def test_to_frame_matches_import_format(self):
        frame = om.to_frame(SAMPLE, "SPR-01")
        self.assertEqual(list(frame.columns), ["location_code", "date", "t_max", "t_min", "humidity", "is_forecast"])
        # same path as a real import: CSV text -> read_upload -> validate
        uploaded = read_upload(frame.to_csv(index=False).encode("utf-8"))
        clean, errors = validate(uploaded, {"SPR-01"}, "2026-06-01")
        self.assertEqual((len(clean), errors), (3, []))  # the empty day is kept as missing values

    def test_missing_daily_block(self):
        with self.assertRaises(RuntimeError):
            om.to_frame({"error": True}, "SPR-01")

    def test_url_has_parameters(self):
        url = om.build_url(23.03, 72.58, "2026-05-01", "2026-05-03")
        self.assertIn("start_date=2026-05-01", url)
        self.assertIn("relative_humidity_2m_mean", url)

    def test_argument_checks(self):
        with self.assertRaises(ValueError):
            om.check_args(123, 72, "2026-05-01", "2026-05-03")
        with self.assertRaises(ValueError):
            om.check_args(23, 72, "2026-05-03", "2026-05-01")
        with self.assertRaises(ValueError):
            om.check_args(23, 72, "2099-01-01", "2099-01-02")


if __name__ == "__main__":
    unittest.main()
