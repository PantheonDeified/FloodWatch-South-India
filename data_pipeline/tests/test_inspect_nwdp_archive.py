from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect_nwdp_archive.py"


class InspectNwdpArchiveTests(unittest.TestCase):
    def test_reports_headers_and_sample_without_transforming_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "discharge.csv"
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Station ID", "Date", "Discharge (cumec)"])
                writer.writerow(["G-01", "01/01/2000", "45.6"])
            run = subprocess.run([
                sys.executable, str(SCRIPT), "--directory", str(root),
                "--out", str(root / "report.json"),
            ], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
            item = report["files"][0]
            self.assertEqual(item["headers"], ["Station ID", "Date", "Discharge (cumec)"])
            self.assertEqual(item["sample_rows"][0]["Discharge (cumec)"], "45.6")
            self.assertIn("No conversion was performed", item["normalization_warning"])

    def test_empty_archive_directory_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = subprocess.run([
                sys.executable, str(SCRIPT), "--directory", tmp,
            ], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)


if __name__ == "__main__":
    unittest.main()
