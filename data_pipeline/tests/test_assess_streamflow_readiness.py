from __future__ import annotations

import csv
import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assess_streamflow_readiness.py"
FIELDS = [
    "station_id", "date", "precipitation_sum", "temperature_2m_mean",
    "temperature_2m_max", "temperature_2m_min", "wind_speed_10m_max",
    "rain_sum_3d_mm", "rain_sum_7d_mm", "rain_sum_14d_mm",
    "rain_sum_30d_mm", "river_discharge_last_m3s",
]


def make_features(path: Path, negative_discharge: bool = False) -> None:
    start = dt.date(2020, 1, 1)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for index in range(320):
            writer.writerow({
                "station_id": "GAUGE-1",
                "date": (start + dt.timedelta(days=index)).isoformat(),
                "precipitation_sum": index % 8,
                "temperature_2m_mean": 25,
                "temperature_2m_max": 31,
                "temperature_2m_min": 19,
                "wind_speed_10m_max": 10,
                "rain_sum_3d_mm": 4,
                "rain_sum_7d_mm": 10,
                "rain_sum_14d_mm": 20,
                "rain_sum_30d_mm": 45,
                "river_discharge_last_m3s": -1 if negative_discharge and index == 200 else 12 + index % 5,
            })


class StreamflowReadinessTests(unittest.TestCase):
    def run_audit(self, feature_path: Path) -> dict:
        run = subprocess.run([
            sys.executable, str(SCRIPT), "--features", str(feature_path),
            "--lookback-days", "14", "--lead-days", "7", "--min-complete-windows", "10",
        ], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        return json.loads(run.stdout)

    def test_continuous_nonnegative_series_can_pass_structural_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.csv"
            make_features(path)
            report = self.run_audit(path)
            self.assertEqual(report["stations_checked"], 1)
            self.assertEqual(report["stations_eligible_for_training_attempt"], 1)
            self.assertTrue(report["station_reports"][0]["eligible_for_training_attempt"])

    def test_negative_discharge_fails_structural_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.csv"
            make_features(path, negative_discharge=True)
            report = self.run_audit(path)
            station = report["station_reports"][0]
            self.assertFalse(station["eligible_for_training_attempt"])
            self.assertIn("negative discharge values", station["reasons"])


if __name__ == "__main__":
    unittest.main()
