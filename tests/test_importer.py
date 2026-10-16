"""Tests for CSV upload validation."""
import unittest

from noor.exceptions import ValidationError
from noor.importer import MAX_BYTES, read_upload, validate

HEADER = "location_code,date,t_max,t_min,humidity\n"
KNOWN = {"SPR-01", "SPR-02"}
TODAY = "2026-06-10"


def check(body, header=HEADER):
    """Read and validate a CSV string; return (clean rows, errors)."""
    return validate(read_upload((header + body).encode("utf-8")), KNOWN, TODAY)


class FileLevelTests(unittest.TestCase):
    """Problems that reject the whole file."""

    def test_missing_column(self):
        with self.assertRaises(ValidationError):
            read_upload(b"location_code,date,t_max\nSPR-01,2026-06-01,40\n")

    def test_empty_file(self):
        with self.assertRaises(ValidationError):
            read_upload(b"")

    def test_header_only(self):
        with self.assertRaises(ValidationError):
            read_upload(HEADER.encode())

    def test_not_utf8(self):
        with self.assertRaises(ValidationError):
            read_upload("location_code,date\n\xff\xfe".encode("latin-1") + b"\xff")

    def test_too_large(self):
        with self.assertRaises(ValidationError):
            read_upload(b"x" * (MAX_BYTES + 1))

    def test_bom_and_case_accepted(self):
        df = read_upload("﻿LOCATION_CODE,Date,T_MAX,T_MIN,HUMIDITY\nSPR-01,2026-06-01,40,28,30\n".encode("utf-8"))
        self.assertIn("location_code", df.columns)


class RowLevelTests(unittest.TestCase):
    """Problems that reject single rows, with line numbers."""

    def test_good_rows(self):
        clean, errors = check("SPR-01,2026-06-01,40.5,28,30\nSPR-02,2026-06-01,41,29,35\n")
        self.assertEqual((len(clean), errors), (2, []))
        self.assertEqual(clean.iloc[0]["t_max"], 40.5)

    def test_blank_cells_are_missing_not_errors(self):
        clean, errors = check("SPR-01,2026-06-01,40,,\n")
        self.assertEqual(errors, [])
        self.assertTrue(clean.iloc[0]["humidity"] != clean.iloc[0]["humidity"])  # NaN

    def test_each_problem_reported(self):
        body = ("SPR-99,2026-06-01,40,28,30\n"      # line 2 unknown location
                "SPR-01,01/06/2026,40,28,30\n"      # line 3 bad date
                "SPR-01,2026-06-02,hot,28,30\n"     # line 4 not a number
                "SPR-01,2026-06-03,75,28,30\n"      # line 5 out of range
                "SPR-01,2026-06-04,30,35,30\n"      # line 6 t_min > t_max
                "SPR-01,2026-06-05,,,\n"            # line 7 no values
                "SPR-01,2026-07-01,40,28,30\n"      # line 8 observed date in the future
                "SPR-02,2026-06-01,40,28,130\n"     # line 9 humidity out of range
                "SPR-02,2026-06-02,40,28,30\n"      # line 10 fine
                "SPR-02,2026-06-02,41,28,30\n")     # line 11 duplicate of line 10
        clean, errors = check(body)
        lines = sorted({e["line"] for e in errors})
        self.assertEqual(lines, [2, 3, 4, 5, 6, 7, 8, 9, 11])
        self.assertEqual(len(clean), 1)

    def test_forecast_rows(self):
        header = "location_code,date,t_max,t_min,humidity,is_forecast\n"
        clean, errors = check("SPR-01,2026-06-12,42,30,25,1\nSPR-01,2026-07-30,42,30,25,1\nSPR-01,2026-06-12,42,30,25,2\n",
                              header)
        self.assertEqual(len(clean), 1)
        self.assertEqual(sorted({e["line"] for e in errors}), [3, 4])

    def test_injection_text_is_just_an_unknown_code(self):
        clean, errors = check("x'; DROP TABLE locations; --,2026-06-01,40,28,30\n")
        self.assertEqual(len(clean), 0)
        self.assertEqual(errors[0]["column"], "location_code")


if __name__ == "__main__":
    unittest.main()
