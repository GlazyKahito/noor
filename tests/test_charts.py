"""Every chart returns a Matplotlib Figure (also for empty data) and can be saved as PNG."""
import os
import tempfile
import unittest

import pandas as pd
from matplotlib.figure import Figure

from noor import charts
from noor.climate import explorer_table, monthly_means
from noor.database import Database
from noor.service import NoorService


class ChartTests(unittest.TestCase):
    """Charts are drawn from the real demo database."""

    @classmethod
    def setUpClass(cls):
        cls.db = Database(":memory:")
        cls.svc = NoorService(cls.db)
        cls.svc.setup()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def figures(self):
        latest = self.db.latest_assessments()
        frame = self.db.observations_frame()
        one = self.db.observations_frame(["SPR-01"])
        return {
            "distribution": charts.risk_distribution(latest),
            "bars": charts.risk_bars(latest),
            "histogram": charts.score_histogram(latest),
            "map": charts.risk_map(latest),
            "map_hazard": charts.risk_map(self.svc.assess(), "hazard"),
            "heatmap": charts.temperature_heatmap(frame),
            "monthly": charts.monthly_chart(monthly_means(frame)),
            "trend": charts.trend_chart(explorer_table(one, "2026-05-01", "2026-06-04"), "SPR-01"),
            "allocation": charts.allocation_chart(self.svc.plan("risk_first")),
            "scenario": charts.scenario_chart(self.svc.scenario({"temperature_increase": 2})["comparison"]),
            "dimensions": charts.dimension_chart(self.svc.assessment("SPR-01")),
        }

    def test_every_chart_is_a_figure_with_axes(self):
        for name, fig in self.figures().items():
            with self.subTest(chart=name):
                self.assertIsInstance(fig, Figure)
                self.assertTrue(fig.axes)

    def test_empty_inputs_give_a_message_not_an_error(self):
        empty = pd.DataFrame(columns=["location", "name", "date", "is_forecast", "t_max", "t_min", "humidity"])
        for fig in (charts.risk_distribution([]), charts.risk_bars([]), charts.score_histogram([]),
                    charts.risk_map([]), charts.temperature_heatmap(empty)):
            self.assertIsInstance(fig, Figure)
            self.assertIn("No", fig.axes[0].texts[0].get_text())

    def test_distribution_counts_match_assessments(self):
        latest = self.db.latest_assessments()
        fig = charts.risk_distribution(latest)
        shown = sum(int(round(p.get_height())) for p in fig.axes[0].patches)
        self.assertEqual(shown, len(latest))

    def test_save_png(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "chart.png")
            charts.save_png(charts.risk_bars(self.db.latest_assessments()), path)
            with open(path, "rb") as f:
                self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
