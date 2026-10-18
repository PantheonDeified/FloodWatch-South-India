#!/usr/bin/env python3
"""Normalize CWC manual daily discharge CSVs and produce a conservative QA report.

Raw source files are never modified. Negative discharge values are rejected;
large positive values are retained but flagged for station-level review rather
than removed using an arbitrary universal threshold. Timestamps stay timezone-naive
because the source archive does not declare a timezone.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import pathlib
import statistics
from collections import Counter, defaultdict

TIME_FORMATS = ("%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M",
                "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d")
VALUE_COLUMN = "Manual Daily River Water Discharge (m3/sec)"
TIME_COLUMN = "Data Acquisition Time"


def parse_time(raw: str) -> str:
    raw = (raw or "").strip()
    for fmt in TIME_FORMATS:
        try:
            return dt.datetime.strptime(raw, fmt).isoformat(timespec="minutes")
        except ValueError:
            pass
    return ""


def normalize(inputs: list[pathlib.Path], output: pathlib.Path, report_path: pathlib.Path,
              source_url: str) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["station_id", "station_name", "state", "district", "river", "basin",
               "latitude", "longitude", "observed_at", "discharge_m3_s", "source_url",
               "source_file", "source_timezone", "quality_flag"]
    stats = { "input_files": [], "rows_seen": 0, "rows_written": 0,
              "rows_rejected": 0, "reject_reasons": {}, "negative_values_rejected": 0,
              "missing_values_rejected": 0, "bad_timestamps_rejected": 0,
              "duplicate_station_timestamp_rows": 0, "stations": 0,
              "states": {}, "date_min": None, "date_max": None,
              "large_value_review_threshold_by_station": {},
              "notes": [
                "Source timestamps are preserved as timezone-naive; archive timezone is unspecified.",
                "Negative discharge values are rejected, not silently corrected.",
                "High values are retained and flagged for review, not automatically discarded.",
                "This is a normalized research dataset, not a validated flood forecast dataset."
              ]}
    seen = set()
    station_values = defaultdict(list)
    station_counts = Counter()
    states = Counter()
    dates = []
    reasons = Counter()
    with output.open("w", newline="", encoding="utf-8") as dest:
        writer = csv.DictWriter(dest, fieldnames=columns)
        writer.writeheader()
        for path in inputs:
            file_rows = 0
            with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as src:
                reader = csv.DictReader(src)
                required = {"Station", "State", "District", "River", "Basin", "Latitude",
                            "Longitude", TIME_COLUMN, VALUE_COLUMN}
                missing = sorted(required - set(reader.fieldnames or []))
                if missing:
                    raise ValueError(f"{path}: required CWC columns missing: {missing}")
                for row in reader:
                    stats["rows_seen"] += 1
                    file_rows += 1
                    station_name = (row.get("Station") or "").strip()
                    state = (row.get("State") or "").strip()
                    lat = (row.get("Latitude") or "").strip()
                    lon = (row.get("Longitude") or "").strip()
                    observed = parse_time(row.get(TIME_COLUMN, ""))
                    raw_value = (row.get(VALUE_COLUMN) or "").strip().replace(",", "")
                    try:
                        value = float(raw_value)
                        if not math.isfinite(value):
                            raise ValueError
                    except ValueError:
                        stats["rows_rejected"] += 1
                        stats["missing_values_rejected"] += 1
                        reasons["missing_or_non_numeric_discharge"] += 1
                        continue
                    if not observed:
                        stats["rows_rejected"] += 1
                        stats["bad_timestamps_rejected"] += 1
                        reasons["unparseable_timestamp"] += 1
                        continue
                    if not station_name or not state:
                        stats["rows_rejected"] += 1
                        reasons["missing_station_or_state"] += 1
                        continue
                    if value < 0:
                        stats["rows_rejected"] += 1
                        stats["negative_values_rejected"] += 1
                        reasons["negative_discharge"] += 1
                        continue
                    station_id = "|".join([state.casefold(), station_name.casefold(), lat, lon])
                    duplicate_key = (station_id, observed)
                    if duplicate_key in seen:
                        stats["duplicate_station_timestamp_rows"] += 1
                    seen.add(duplicate_key)
                    station_values[station_id].append(value)
                    station_counts[station_id] += 1
                    states[state] += 1
                    dates.append(observed[:10])
                    writer.writerow({
                        "station_id": station_id, "station_name": station_name, "state": state,
                        "district": (row.get("District") or "").strip(),
                        "river": (row.get("River") or "").strip(),
                        "basin": (row.get("Basin") or "").strip(), "latitude": lat, "longitude": lon,
                        "observed_at": observed, "discharge_m3_s": f"{value:.8g}",
                        "source_url": source_url, "source_file": path.name,
                        "source_timezone": "unspecified; timestamp preserved without timezone conversion",
                        "quality_flag": "retained_for_review" if value > 100000 else "unreviewed"
                    })
                    stats["rows_written"] += 1
            stats["input_files"].append({"file": path.name, "rows_seen": file_rows})
    for sid, vals in station_values.items():
        # Use nearest-rank 99th percentile as a review threshold, not a deletion rule.
        ordered = sorted(vals)
        idx = max(0, math.ceil(0.99 * len(ordered)) - 1)
        stats["large_value_review_threshold_by_station"][sid] = {
            "rows": len(vals), "p99_discharge_m3_s": ordered[idx],
            "max_discharge_m3_s": ordered[-1],
            "values_over_100000_m3_s": sum(v > 100000 for v in vals)
        }
    stats["stations"] = len(station_values)
    stats["states"] = dict(states)
    stats["date_min"] = min(dates) if dates else None
    stats["date_max"] = max(dates) if dates else None
    stats["reject_reasons"] = dict(reasons)
    report_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--source-url", default="https://nwdp.nwic.gov.in/dataset/river-discharge-manual-dailly-central-water-commission-cwc")
    args = parser.parse_args()
    files = sorted(args.input_dir.glob("*.csv"))
    if not files:
        raise SystemExit(f"No CSV files found in {args.input_dir}")
    report = normalize(files, args.output, args.report, args.source_url)
    print(json.dumps({k: report[k] for k in ("rows_seen", "rows_written", "rows_rejected",
          "negative_values_rejected", "stations", "states", "date_min", "date_max")}, indent=2))
    return 0 if report["rows_written"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
