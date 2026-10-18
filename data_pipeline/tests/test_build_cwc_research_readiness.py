from __future__ import annotations
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_cwc_research_readiness.py"


class ResearchReadinessTests(unittest.TestCase):
    def run_builder(self, root, catalog, audit):
        catalog_path = root / "catalog.csv"
        audit_path = root / "audit.json"
        out_csv = root / "queue.csv"
        out_json = root / "queue.json"
        with catalog_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["station_id", "station_name", "state", "river", "basin",
                                               "record_count", "first_observed_at", "last_observed_at",
                                               "coordinate_verified", "coordinate_source_url"])
            w.writeheader()
            w.writerows(catalog)
        audit_path.write_text(json.dumps({"station_reports": audit}), encoding="utf-8")
        run = subprocess.run([sys.executable, str(SCRIPT), "--catalog", str(catalog_path),
                              "--audit", str(audit_path), "--out-csv", str(out_csv),
                              "--out-json", str(out_json)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        with out_csv.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f)), json.loads(out_json.read_text(encoding="utf-8"))

    def test_long_complete_history_is_priority_but_coordinates_stay_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            catalog = [{"station_id": "s1", "station_name": "Gauge A", "state": "Kerala",
                        "river": "River A", "basin": "West Coast", "record_count": "1000",
                        "first_observed_at": "2000-01-01", "last_observed_at": "2003-01-01",
                        "coordinate_verified": "false", "coordinate_source_url": ""}]
            audit = [{"station_id": "s1", "station_name": ["Gauge A"], "states": ["Kerala"],
                      "rivers": ["River A"], "basins": ["West Coast"], "row_count": 1000,
                      "unique_observation_dates": 1000, "calendar_span_days": 1096,
                      "missing_calendar_days": 96, "first_date": "2000-01-01", "last_date": "2003-01-01",
                      "review_flags": []}]
            rows, report = self.run_builder(root, catalog, audit)
            self.assertEqual(rows[0]["review_status"], "priority_for_manual_station_review")
            self.assertEqual(rows[0]["downstream_weather_join_allowed"], "false")
            self.assertEqual(rows[0]["model_training_gate"], "blocked")
            self.assertEqual(report["stations_allowed_for_weather_join"], 0)

    def test_multiple_archive_resource_urls_do_not_create_identity_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            catalog = [{"station_id": "s1", "station_name": "Gauge A", "state": "Kerala",
                        "river": "River A", "basin": "West Coast", "record_count": "1000",
                        "first_observed_at": "2000-01-01", "last_observed_at": "2003-01-01",
                        "coordinate_verified": "false", "coordinate_source_url": ""}]
            audit = [{"station_id": "s1", "station_name": ["Gauge A"], "states": ["Kerala"],
                      "rivers": ["River A"], "basins": ["West Coast"], "row_count": 1000,
                      "unique_observation_dates": 1000, "calendar_span_days": 1096,
                      "missing_calendar_days": 96, "source_urls": [
                          "https://nwdp.gov/resource/older", "https://nwdp.gov/resource/newer"],
                      "review_flags": ["multiple_source_urls"]}]
            rows, _ = self.run_builder(root, catalog, audit)
            self.assertEqual(rows[0]["review_status"], "priority_for_manual_station_review")
            self.assertEqual(rows[0]["source_resource_count"], "2")
            self.assertNotIn("station_identity_or_metadata_conflict", rows[0]["review_reasons"])

    def test_conflicts_are_not_marked_as_priority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            catalog = [{"station_id": "s1", "station_name": "Gauge A", "state": "Kerala",
                        "river": "River A", "basin": "West Coast", "record_count": "1000",
                        "first_observed_at": "2000-01-01", "last_observed_at": "2003-01-01",
                        "coordinate_verified": "false", "coordinate_source_url": ""}]
            audit = [{"station_id": "s1", "station_name": ["Gauge A"], "states": ["Kerala"],
                      "rivers": ["River A", "River B"], "basins": ["West Coast"], "row_count": 1000,
                      "unique_observation_dates": 1000, "calendar_span_days": 1096,
                      "missing_calendar_days": 96, "review_flags": ["multiple_rivers"]}]
            rows, _ = self.run_builder(root, catalog, audit)
            self.assertEqual(rows[0]["review_status"], "manual_data_review_required")
            self.assertIn("station_identity_or_metadata_conflict", rows[0]["review_reasons"])


if __name__ == "__main__":
    unittest.main()
