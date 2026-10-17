#!/usr/bin/env python3
"""Inspect a downloaded official water CSV before writing a data normalizer."""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import pathlib
import re
from collections import Counter


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, type=pathlib.Path)
    ap.add_argument("--sample-rows", type=int, default=5)
    ap.add_argument("--date-column", help="Optional exact date/time header.")
    args = ap.parse_args()

    with args.input.open("r", newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        samples = []
        counts = Counter()
        min_date = max_date = None
        parseable = 0
        for row in reader:
            counts["rows"] += 1
            if len(samples) < args.sample_rows:
                samples.append(row)
            if args.date_column and row.get(args.date_column):
                value = row[args.date_column].strip()
                try:
                    d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    try:
                        d = dt.datetime.strptime(value[:10], "%d/%m/%Y")
                    except ValueError:
                        try:
                            d = dt.datetime.strptime(value[:10], "%Y/%m/%d")
                        except ValueError:
                            continue
                parseable += 1
                min_date = value if min_date is None or value < min_date else min_date
                max_date = value if max_date is None or value > max_date else max_date
    report = {
        "file": str(args.input),
        "bytes": args.input.stat().st_size,
        "headers": headers,
        "row_count_scanned": counts["rows"],
        "date_column": args.date_column,
        "date_values_parseable": parseable,
        "minimum_date_lexical": min_date,
        "maximum_date_lexical": max_date,
        "sample_rows": samples,
        "next_step": "Confirm station ID, timestamp, variable, units, timezone, and source provenance before normalization.",
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
