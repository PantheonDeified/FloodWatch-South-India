#!/usr/bin/env python3
"""Normalize a downloaded CSV without confusing water level and discharge."""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import pathlib
import sys


def parse_time(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
        for fmt in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y/%m/%d %H:%M",
                    "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d"):
            try:
                parsed = dt.datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return ""
    return parsed.isoformat()


def convert(value: float, unit: str, kind: str) -> tuple[float, str]:
    unit = unit.lower()
    if kind in {"river_level", "reservoir_level"}:
        factors = {"m": 1.0, "metre": 1.0, "meter": 1.0, "cm": 0.01, "mm": 0.001, "ft": 0.3048}
        if unit not in factors:
            raise ValueError(f"Unsupported level unit: {unit}")
        return value * factors[unit], "m"
    if kind == "discharge":
        factors = {"m3/s": 1.0, "m³/s": 1.0, "cumec": 1.0, "l/s": 0.001}
        if unit not in factors:
            raise ValueError(f"Unsupported discharge unit: {unit}")
        return value * factors[unit], "m3/s"
    if kind == "storage":
        factors = {"mcm": 1.0, "million m3": 1.0, "million cubic metres": 1.0, "m3": 1e-6}
        if unit not in factors:
            raise ValueError(f"Unsupported storage unit: {unit}")
        return value * factors[unit], "million_m3"
    raise ValueError(f"Unsupported kind: {kind}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, type=pathlib.Path)
    ap.add_argument("--output", required=True, type=pathlib.Path)
    ap.add_argument("--station-column", required=True)
    ap.add_argument("--time-column", required=True)
    ap.add_argument("--value-column", required=True)
    ap.add_argument("--kind", required=True, choices=["river_level", "reservoir_level", "discharge", "storage"])
    ap.add_argument("--unit", required=True, help="Exact declared source unit; no unit is inferred.")
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--station-name-column")
    ap.add_argument("--river-column")
    ap.add_argument("--state-column")
    ap.add_argument("--latitude-column")
    ap.add_argument("--longitude-column")
    ap.add_argument("--timezone", default="unspecified", help="Source timestamp timezone or semantics.")
    args = ap.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = rejected = 0
    errors = []
    fields = [
        "station_id", "station_name", "river", "state", "latitude", "longitude",
        "observed_at", "kind", "value", "unit", "source_url", "source_file",
        "normalization_time_utc", "source_timezone",
    ]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with args.input.open("r", newline="", encoding="utf-8-sig", errors="replace") as source:
        reader = csv.DictReader(source)
        required = [args.station_column, args.time_column, args.value_column]
        missing = [x for x in required if x not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"Required columns not found: {missing}. Actual headers: {reader.fieldnames}")
        with args.output.open("w", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=fields)
            writer.writeheader()
            for line, row in enumerate(reader, start=2):
                try:
                    station = (row.get(args.station_column) or "").strip()
                    when = parse_time(row.get(args.time_column, ""))
                    if not station or not when:
                        rejected += 1
                        continue
                    value_text = (row.get(args.value_column) or "").strip().replace(",", "")
                    if not value_text:
                        rejected += 1
                        continue
                    value, unit = convert(float(value_text), args.unit, args.kind)
                    if args.latitude_column and args.longitude_column:
                        lat, lon = row.get(args.latitude_column, ""), row.get(args.longitude_column, "")
                    else:
                        lat = lon = ""
                    writer.writerow({
                        "station_id": station,
                        "station_name": (row.get(args.station_name_column) or "").strip() if args.station_name_column else "",
                        "river": (row.get(args.river_column) or "").strip() if args.river_column else "",
                        "state": (row.get(args.state_column) or "").strip() if args.state_column else "",
                        "latitude": lat,
                        "longitude": lon,
                        "observed_at": when,
                        "kind": args.kind,
                        "value": f"{value:.8g}",
                        "unit": unit,
                        "source_url": args.source_url,
                        "source_file": str(args.input),
                        "normalization_time_utc": now,
                        "source_timezone": args.timezone,
                    })
                    written += 1
                except (ValueError, TypeError) as exc:
                    rejected += 1
                    if len(errors) < 20:
                        errors.append({"line": line, "error": str(exc)})
    print(json.dumps({"output": str(args.output), "written": written, "rejected": rejected, "sample_errors": errors}, indent=2))
    return 1 if written == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
