from __future__ import annotations
import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_cwc_station_catalog.py"

class StationCatalogTests(unittest.TestCase):
    def test_builds_review_catalog_without_marking_coordinates_verified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "input.csv"
            fields = ["station_id","station_name","state","district","river","basin","latitude","longitude","observed_at","source_url","source_file","discharge_m3_s"]
            with source.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
                base = {"station_id":"kerala|river a|10|76","station_name":"River A","state":"Kerala","district":"D1","river":"River A","basin":"West Coast","latitude":"10","longitude":"76","source_url":"https://example.gov/data","source_file":"a.csv","discharge_m3_s":"12"}
                w.writerow({**base,"observed_at":"2020-01-02T08:00"})
                w.writerow({**base,"observed_at":"2020-01-01T08:00"})
            output, report = root / "catalog.csv", root / "report.json"
            run = subprocess.run([sys.executable, str(SCRIPT), "--input", str(source), "--output", str(output), "--report", str(report)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            with output.open(newline="", encoding="utf-8") as f: rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["record_count"], "2")
            self.assertEqual(rows[0]["first_observed_at"], "2020-01-01T08:00")
            self.assertEqual(rows[0]["last_observed_at"], "2020-01-02T08:00")
            self.assertEqual(rows[0]["coordinate_verified"], "false")
            self.assertEqual(rows[0]["coordinate_source_url"], "")
            self.assertEqual(json.loads(report.read_text())["manual_verification_required"], 1)

    def test_rejects_missing_schema(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / "bad.csv"; source.write_text("station_id,state\na,Kerala\n")
            run = subprocess.run([sys.executable, str(SCRIPT), "--input", str(source), "--output", str(root/"out.csv"), "--report", str(root/"report.json")], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)

if __name__ == "__main__":
    unittest.main()
