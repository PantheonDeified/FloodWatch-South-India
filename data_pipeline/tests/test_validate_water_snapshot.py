from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_water_snapshot import validate_snapshot  # noqa: E402


NOW = dt.datetime(2026, 10, 18, 2, 30, tzinfo=dt.timezone.utc)


def valid_record(**overrides):
    record = {
        "id": "river_level|sample|Telangana|1",
        "station_id": "1",
        "station_name": "Sample gauge",
        "state": "Telangana",
        "kind": "river_level",
        "value": 12.5,
        "unit": "m",
        "observed_at": "2026-10-18T01:00:00+00:00",
        "source_timezone": "UTC",
        "source_dataset_url": "https://example.org/dataset",
        "source_download_url": "https://example.org/data.csv",
        "latitude": 18.0,
        "longitude": 79.0,
    }
    record.update(overrides)
    return record


def valid_snapshot(*records):
    return {
        "schema_version": 1,
        "generated_at_utc": "2026-10-18T02:00:00+00:00",
        "resource_count_checked": 1,
        "observation_count": len(records),
        "observations": list(records),
    }


class ValidateWaterSnapshotTests(unittest.TestCase):
    def test_valid_record_passes(self):
        result = validate_snapshot(valid_snapshot(valid_record()), now=NOW)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["summary"]["observation_count"], 1)

    def test_empty_snapshot_fails(self):
        result = validate_snapshot(valid_snapshot(), now=NOW)
        self.assertTrue(any("zero observations" in e for e in result["errors"]))

    def test_duplicate_ids_fail(self):
        first = valid_record()
        second = valid_record(value=13.0)
        result = validate_snapshot(valid_snapshot(first, second), now=NOW)
        self.assertTrue(any("duplicated" in e for e in result["errors"]))

    def test_one_missing_coordinate_fails(self):
        result = validate_snapshot(valid_snapshot(valid_record(latitude=None)), now=NOW)
        self.assertTrue(any("both latitude and longitude" in e for e in result["errors"]))

    def test_missing_both_coordinates_is_warning(self):
        result = validate_snapshot(valid_snapshot(valid_record(latitude=None, longitude=None)), now=NOW)
        self.assertEqual(result["errors"], [])
        self.assertTrue(any("no coordinates" in warning for warning in result["warnings"]))

    def test_future_naive_timestamp_is_warning_not_fabricated_as_fresh(self):
        result = validate_snapshot(
            valid_snapshot(valid_record(observed_at="2026-10-18T12:10:00")),
            now=NOW,
        )
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["summary"]["future_timestamp_candidates"], 1)
        self.assertTrue(any("timezone is uncertain" in warning for warning in result["warnings"]))

    def test_non_numeric_value_fails(self):
        result = validate_snapshot(valid_snapshot(valid_record(value=None)), now=NOW)
        self.assertTrue(any(".value must be a finite numeric" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()
