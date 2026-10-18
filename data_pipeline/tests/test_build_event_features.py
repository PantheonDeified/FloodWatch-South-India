from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_event_features.py"


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class BuildEventFeaturesUnitTests(unittest.TestCase):
    def test_level_data_remains_level_not_discharge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weather = root / "weather.csv"
            observations = root / "observations.csv"
            output = root / "features.csv"
            write_csv(weather, [
                {"station_id": "G1", "date": "2024-01-01", "precipitation_sum": 2.0},
                {"station_id": "G1", "date": "2024-01-02", "precipitation_sum": 3.0},
            ], ["station_id", "date", "precipitation_sum"])
            write_csv(observations, [
                {"station_id": "G1", "observed_at": "2024-01-01T12:00:00+00:00", "kind": "river_level", "value": 2.5, "unit": "m"},
                {"station_id": "G1", "observed_at": "2024-01-02T12:00:00+00:00", "kind": "river_level", "value": 2.7, "unit": "m"},
            ], ["station_id", "observed_at", "kind", "value", "unit"])
            run = subprocess.run([
                sys.executable, str(SCRIPT), "--weather", str(weather),
                "--observations", str(observations), "--out", str(output),
            ], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertIn("river_level_last_m", rows[0])
            self.assertNotIn("river_discharge_last_m3s", rows[0])

    def test_rejects_discharge_label_with_level_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weather = root / "weather.csv"
            observations = root / "observations.csv"
            output = root / "features.csv"
            write_csv(weather, [{"station_id": "G1", "date": "2024-01-01", "precipitation_sum": 2.0}],
                      ["station_id", "date", "precipitation_sum"])
            write_csv(observations, [
                {"station_id": "G1", "observed_at": "2024-01-01T12:00:00+00:00", "kind": "discharge", "value": 2.5, "unit": "m"}
            ], ["station_id", "observed_at", "kind", "value", "unit"])
            run = subprocess.run([
                sys.executable, str(SCRIPT), "--weather", str(weather),
                "--observations", str(observations), "--out", str(output),
            ], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("Unsupported or unnormalized units", run.stderr + run.stdout)


if __name__ == "__main__":
    unittest.main()
