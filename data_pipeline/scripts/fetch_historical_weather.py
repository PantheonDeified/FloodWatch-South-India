#!/usr/bin/env python3
"""Fetch ERA5-Land daily reanalysis at verified gauge coordinates.

Reanalysis is gridded model output, not a rain-gauge observation. Requests are
chunked into five-year windows and the end date defaults to seven days ago.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import pathlib
import sys
import time
from typing import Any

import requests

API = "https://archive-api.open-meteo.com/v1/archive"
DAILY_FIELDS = [
    "precipitation_sum",
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "wind_speed_10m_max",
]


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def chunks(start: dt.date, end: dt.date):
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + dt.timedelta(days=365 * 5 - 1))
        yield cursor, chunk_end
        cursor = chunk_end + dt.timedelta(days=1)


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "verified"}


def load_gauges(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    selected = []
    for row in rows:
        station = (row.get("station_id") or "").strip()
        if not station:
            continue
        if not truthy(row.get("coordinate_verified")):
            continue
        if not (row.get("coordinate_source_url") or "").strip():
            continue
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        selected.append({**row, "station_id": station, "latitude": str(lat), "longitude": str(lon)})
    if not selected:
        raise ValueError(
            "No verified gauge coordinates found. Add stations to the catalog only "
            "after validating their coordinates and coordinate_source_url."
        )
    return selected


def fetch_chunk(session: requests.Session, gauge: dict[str, str],
                start: dt.date, end: dt.date, model: str) -> dict[str, Any]:
    params = {
        "latitude": gauge["latitude"],
        "longitude": gauge["longitude"],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": ",".join(DAILY_FIELDS),
        "timezone": "UTC",
        "models": model,
    }
    last_error = None
    for attempt in range(4):
        try:
            response = session.get(API, params=params, timeout=90)
            response.raise_for_status()
            body = response.json()
            if "error" in body:
                raise RuntimeError(str(body.get("reason", body["error"])))
            if not isinstance(body.get("daily", {}).get("time"), list):
                raise RuntimeError("API response has no daily time series")
            return body
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed after retries: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gauges", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--start", default="1950-01-01")
    parser.add_argument("--end", help="End date; defaults to seven days before today.")
    parser.add_argument("--model", default="era5_land", choices=["era5_land", "era5"])
    args = parser.parse_args()

    start = parse_date(args.start)
    end = parse_date(args.end) if args.end else (dt.date.today() - dt.timedelta(days=7))
    if end < start:
        raise SystemExit("--end must be on or after --start")
    if args.model == "era5_land" and start < dt.date(1950, 1, 1):
        raise SystemExit("ERA5-Land starts in 1950; use --model era5 for earlier dates where available.")

    gauges = load_gauges(args.gauges)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "station_id", "station_name", "river", "basin", "state",
        "latitude", "longitude", "date", *DAILY_FIELDS,
        "dataset", "model", "retrieved_at_utc", "coordinate_source_url",
    ]
    manifest = {
        "source": API,
        "dataset": args.model,
        "start_date_requested": start.isoformat(),
        "end_date_requested": end.isoformat(),
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stations_requested": len(gauges),
        "records_written": 0,
        "errors": [],
        "important": "ERA5/ERA5-Land values are gridded reanalysis estimates, not station observations.",
    }
    session = requests.Session()
    session.headers["User-Agent"] = "FloodWatch-South-India/0.1 (historical hydrology research)"
    with args.out.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for gauge in gauges:
            try:
                for part_start, part_end in chunks(start, end):
                    data = fetch_chunk(session, gauge, part_start, part_end, args.model)
                    daily = data["daily"]
                    retrieved = dt.datetime.now(dt.timezone.utc).isoformat()
                    for i, day in enumerate(daily["time"]):
                        row = {
                            "station_id": gauge["station_id"],
                            "station_name": gauge.get("station_name", ""),
                            "river": gauge.get("river", ""),
                            "basin": gauge.get("basin", ""),
                            "state": gauge.get("state", ""),
                            "latitude": gauge["latitude"],
                            "longitude": gauge["longitude"],
                            "date": day,
                            "dataset": "Open-Meteo Historical Weather API",
                            "model": args.model,
                            "retrieved_at_utc": retrieved,
                            "coordinate_source_url": gauge.get("coordinate_source_url", ""),
                        }
                        for field in DAILY_FIELDS:
                            values = daily.get(field) or []
                            row[field] = values[i] if i < len(values) else ""
                        writer.writerow(row)
                        manifest["records_written"] += 1
            except Exception as exc:
                manifest["errors"].append({"station_id": gauge["station_id"], "error": str(exc)})
                print(f"ERROR {gauge['station_id']}: {exc}", file=sys.stderr)
    manifest_path = args.out.with_suffix(args.out.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 1 if manifest["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
