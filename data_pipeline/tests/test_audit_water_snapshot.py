import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data_pipeline" / "scripts"))
from audit_water_snapshot import render_report


class AuditWaterSnapshotTests(unittest.TestCase):
    def test_report_counts_records_and_flags_unknown_metadata(self):
        data = {
            "generated_at_utc": "2026-10-18T02:00:00+00:00",
            "resource_count_checked": 2,
            "observations": [
                {
                    "kind": "river_level", "value": 3.2, "unit": "m",
                    "station_name": "Gauge A", "station_id": "A",
                    "state": "Telangana", "district": "District A",
                    "latitude": None, "longitude": None,
                    "observed_at": "2026-10-17T10:00:00",
                    "source_timezone": "not specified",
                    "source_name": "Example source", "source_resource_title": "Daily levels",
                },
                {
                    "kind": "river_discharge", "value": 10.0, "unit": "m3/s",
                    "station_name": "Gauge B", "station_id": "B",
                    "state": "Maharashtra", "district": None,
                    "latitude": 19.0, "longitude": 73.0,
                    "observed_at": "2026-10-17T10:00:00",
                    "source_timezone": "Asia/Kolkata",
                    "source_name": "Example source", "source_resource_title": "Daily discharge",
                },
            ],
        }
        report = render_report(data)
        self.assertIn("Records in snapshot: **2**", report)
        self.assertIn("Missing both coordinates | 1", report)
        self.assertIn("Labelled outside five core states | 1", report)
        self.assertIn("Source timezone unspecified | 1", report)
        self.assertIn("River level | 1", report)
        self.assertIn("Maharashtra | 1", report)

    def test_provider_text_is_escaped_for_markdown_tables(self):
        data = {
            "generated_at_utc": "unknown",
            "resource_count_checked": 0,
            "observations": [{
                "kind": "river_level", "station_name": "A|B", "state": "Telangana",
                "source_name": "Source|Name", "source_resource_title": "Resource|Page",
                "observed_at": "2026-10-17T10:00:00",
                "source_timezone": "unknown", "latitude": 10.0, "longitude": 78.0,
                "value": 1.0, "unit": "m", "station_id": "x", "district": "D"
            }],
        }
        report = render_report(data)
        self.assertIn("Source\\|Name", report)


    report = render_report({
        "generated_at_utc": "2026-10-18T00:00:00+00:00",
        "resource_count_checked": 2,
        "observations": [
            {"kind": "river_level", "unit": "m", "state": "Kerala"},
            {"kind": "river_discharge", "unit": "source-defined", "state": "Kerala"},
        ],
        "sources": [
            {
                "source_name": "Example river source",
                "status": "checked",
                "resources_discovered": 2,
                "resource_reports": [{"resource_title": "Good CSV", "status": "ok"}],
                "resource_errors": [{"resource_title": "Broken CSV", "error": "HTTP 503"}],
            },
            {
                "source_name": "Unavailable page",
                "status": "source_page_error",
                "error": "Connection timed out",
            },
        ],
    })
    self.assertIn("## Collection outcomes", report)
    self.assertIn("HTTP 503", report)
    self.assertIn("Connection timed out", report)
    self.assertIn("## Units reported by the collector", report)
    self.assertIn("source-defined", report)
    self.assertIn("Verify them against the original resource metadata", report)


if __name__ == "__main__":
    unittest.main()
