#!/usr/bin/env python3
"""Validate the structure and provenance of a FloodWatch water snapshot.

Missing coordinates and ambiguous/future timestamps are warnings, not grounds
for inventing or deleting records. Structural inconsistencies fail validation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_KINDS = {
    "river_level",
    "river_discharge",
    "reservoir_level",
    "reservoir_storage",
    "reservoir_discharge",
}
CORE_STATES = {"Andhra Pradesh", "Karnataka", "Kerala", "Tamil Nadu", "Telangana"}


def parse_timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None


def is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def validate_snapshot(data: object, *, now: dt.datetime | None = None) -> dict:
    """Return errors, warnings, and a small record-count summary."""
    errors: list[str] = []
    warnings: list[str] = []
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    if not isinstance(data, dict):
        return {
            "errors": ["Snapshot root must be a JSON object"],
            "warnings": [],
            "summary": {},
        }

    observations = data.get("observations")
    if data.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    if not isinstance(observations, list):
        errors.append("observations must be a list")
        observations = []
    if not observations:
        errors.append("Snapshot contains zero observations; do not publish an empty snapshot")
    if data.get("observation_count") != len(observations):
        errors.append("observation_count does not match the observations list length")
    if not parse_timestamp(data.get("generated_at_utc")):
        errors.append("generated_at_utc is missing or is not a parseable timestamp")
    if not isinstance(data.get("resource_count_checked"), int) or data.get("resource_count_checked", 0) < 0:
        errors.append("resource_count_checked must be a non-negative integer")

    seen_ids: set[str] = set()
    missing_coordinates = 0
    missing_state = 0
    non_core_states = 0
    future_timestamp_candidates = 0
    core_state_count = 0

    for index, row in enumerate(observations):
        label = f"observations[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{label} must be an object")
            continue

        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id.strip():
            errors.append(f"{label}.id is missing")
        elif row_id in seen_ids:
            errors.append(f"{label}.id is duplicated: {row_id}")
        else:
            seen_ids.add(row_id)

        if row.get("kind") not in ALLOWED_KINDS:
            errors.append(f"{label}.kind is not a supported water measurement type")
        if not (row.get("station_name") or row.get("station_id")):
            errors.append(f"{label} has no station_name or station_id")

        value = row.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append(f"{label}.value must be a finite numeric source value")
        if not isinstance(row.get("unit"), str) or not row.get("unit", "").strip():
            errors.append(f"{label}.unit is missing")

        observed_at = row.get("observed_at")
        parsed = parse_timestamp(observed_at)
        if parsed is None:
            errors.append(f"{label}.observed_at is missing or unparseable")
        else:
            if parsed.tzinfo is None:
                # Source timestamps without a timezone cannot be compared precisely.
                # Warn only when the naive value is ahead of the collector clock.
                compare_now = now.astimezone(dt.timezone.utc).replace(tzinfo=None)
                if parsed > compare_now + dt.timedelta(hours=1):
                    future_timestamp_candidates += 1
            else:
                if parsed > now.astimezone(dt.timezone.utc) + dt.timedelta(hours=1):
                    future_timestamp_candidates += 1

        if not is_https_url(row.get("source_dataset_url")):
            errors.append(f"{label}.source_dataset_url must be an HTTPS URL")
        if not is_https_url(row.get("source_download_url")):
            errors.append(f"{label}.source_download_url must be an HTTPS URL")

        lat, lon = row.get("latitude"), row.get("longitude")
        if lat is None and lon is None:
            missing_coordinates += 1
        elif lat is None or lon is None:
            errors.append(f"{label} must provide both latitude and longitude or neither")
        else:
            if (
                isinstance(lat, bool)
                or isinstance(lon, bool)
                or not isinstance(lat, (int, float))
                or not isinstance(lon, (int, float))
                or not math.isfinite(lat)
                or not math.isfinite(lon)
                or not -90 <= lat <= 90
                or not -180 <= lon <= 180
            ):
                errors.append(f"{label} has invalid coordinates")

        state = row.get("state")
        if not isinstance(state, str) or not state.strip():
            missing_state += 1
        elif state in CORE_STATES:
            core_state_count += 1
        else:
            non_core_states += 1

        source_timezone = row.get("source_timezone")
        if not isinstance(source_timezone, str) or not source_timezone.strip():
            warnings.append(f"{label}.source_timezone is not documented")

    if missing_coordinates:
        warnings.append(f"{missing_coordinates} records have no coordinates and cannot be plotted as points")
    if missing_state:
        warnings.append(f"{missing_state} records do not identify a state")
    if non_core_states:
        warnings.append(f"{non_core_states} records are labelled outside the five core states; review basin relevance")
    if future_timestamp_candidates:
        warnings.append(
            f"{future_timestamp_candidates} timestamp(s) appear later than the collection clock; "
            "source timezone is uncertain, so check them instead of treating them as fresh"
        )

    return {
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "observation_count": len(observations),
            "resource_count_checked": data.get("resource_count_checked"),
            "core_state_records": core_state_count,
            "missing_coordinates": missing_coordinates,
            "missing_state": missing_state,
            "non_core_state_records": non_core_states,
            "future_timestamp_candidates": future_timestamp_candidates,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/water-observations.json"))
    args = parser.parse_args()

    try:
        data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "errors": [f"Cannot read valid JSON: {exc}"]}, indent=2))
        return 1

    report = validate_snapshot(data)
    report["snapshot"] = str(args.snapshot)
    report["status"] = "passed" if not report["errors"] else "failed"
    print(json.dumps(report, indent=2))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
