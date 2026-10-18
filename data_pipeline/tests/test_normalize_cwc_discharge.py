from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "normalize_cwc_discharge.py"
HEADERS = ["Station", "State", "District", "River", "Basin", "Latitude", "Longitude",
           "Data Acquisition Time", "Manual Daily River Water Discharge (m3/sec)"]


class NormalizeCwcDischargeTests(unittest.TestCase):
    def test_normalizes_values_rejects_negative_and_flags_extreme(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "raw"
            source_dir.mkdir()
            source = source_dir / "sample.csv"
            with source.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(HEADERS)
                w.writerow(["Station A", "Kerala", "District", "River A", "Basin A", "10.1", "76.2", "01-01-2020 08:00", "10.5"])
                w.writerow(["Station A", "Kerala", "District", "River A", "Basin A", "10.1", "76.2", "02-01-2020 08:00", "-999"])
                w.writerow(["Station A", "Kerala", "District", "River A", "Basin A", "10.1", "76.2", "03-01-2020 08:00", "120001"])
            out, report = root / "normalized.csv", root / "report.json"
            run = subprocess.run([sys.executable, str(SCRIPT), "--input-dir", str(source_dir),
                                  "--output", str(out), "--report", str(report)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            with out.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 2)
            self.assertEqual(data["negative_values_rejected"], 1)
            self.assertEqual(rows[1]["quality_flag"], "retained_for_review")
            self.assertEqual(rows[0]["source_timezone"], "unspecified; timestamp preserved without timezone conversion")

    def test_fails_on_missing_required_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.csv").write_text("Station,State\nA,Kerala\n", encoding="utf-8")
            run = subprocess.run([sys.executable, str(SCRIPT), "--input-dir", str(root),
                                  "--output", str(root / "out.csv"), "--report", str(root / "report.json")],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)


if __name__ == "__main__":
    unittest.main()
