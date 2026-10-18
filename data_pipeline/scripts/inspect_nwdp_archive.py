#!/usr/bin/env python3
"""Summarize downloaded NWDP CSV headers and a few rows without normalizing them."""
from __future__ import annotations

import argparse
import csv
import json
import pathlib


def inspect_file(path: pathlib.Path, sample_rows: int) -> dict:
    result = {"file": path.name, "bytes": path.stat().st_size}
    try:
        with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as handle:
            reader = csv.DictReader(handle)
            result["headers"] = reader.fieldnames or []
            result["sample_rows"] = []
            for _, row in zip(range(sample_rows), reader):
                result["sample_rows"].append(row)
            result["inspection_status"] = "ok" if result["headers"] else "no_headers"
    except (OSError, csv.Error) as exc:
        result.update({"inspection_status": "error", "error": str(exc)})
    result["normalization_warning"] = (
        "Samples only: confirm date column, station identifier, variable, units, source timezone, "
        "and geographic metadata before using the file for modelling. No conversion was performed."
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path)
    parser.add_argument("--sample-rows", type=int, default=5)
    args = parser.parse_args()
    if args.sample_rows < 1 or args.sample_rows > 20:
        raise SystemExit("sample-rows must be between 1 and 20.")
    if not args.directory.is_dir():
        raise SystemExit(f"Archive directory does not exist: {args.directory}")
    files = sorted(path for path in args.directory.glob("*.csv") if path.is_file())
    report = {
        "directory": str(args.directory),
        "csv_files_found": len(files),
        "files": [inspect_file(path, args.sample_rows) for path in files],
        "warning": "This is schema discovery, not data cleaning or model validation.",
    }
    output = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output)
    return 0 if files else 1


if __name__ == "__main__":
    raise SystemExit(main())
