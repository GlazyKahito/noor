"""Save NOOR's main charts as PNG files (for reports and slides).

Usage (from the project folder):  python scripts/export_charts.py [OUTPUT_FOLDER]
Default folder: charts/ (git-ignored). Uses the same database as the desktop app.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from noor import charts  # noqa: E402
from noor.database import Database  # noqa: E402
from noor.service import NoorService  # noqa: E402


def main(folder):
    """Draw each chart and write it to `folder`."""
    os.makedirs(folder, exist_ok=True)
    db = Database()
    svc = NoorService(db)
    svc.setup()
    latest = db.latest_assessments()
    files = {
        "risk_map.png": charts.risk_map(latest),
        "risk_by_location.png": charts.risk_bars(latest),
        "score_histogram.png": charts.score_histogram(latest),
        "temperature_heatmap.png": charts.temperature_heatmap(db.observations_frame()),
        "allocation_risk_first.png": charts.allocation_chart(svc.plan("risk_first")),
        "scenario_plus2C_5centres.png": charts.scenario_chart(
            svc.scenario({"temperature_increase": 2, "new_cooling_centres": 5})["comparison"]),
    }
    for name, figure in files.items():
        charts.save_png(figure, os.path.join(folder, name))
        print("saved", os.path.join(folder, name))
    db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "charts")
