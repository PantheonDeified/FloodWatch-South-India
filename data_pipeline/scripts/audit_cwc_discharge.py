#!/usr/bin/env python3
"""Create a conservative per-station QA report for normalized CWC discharge."""
from __future__ import annotations
import argparse, csv, json, math, pathlib
from collections import defaultdict
from datetime import datetime

TIME_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")

def parse_date(raw):
    raw = (raw or "").strip()
    for fmt in TIME_FORMATS:
        try: return datetime.strptime(raw, fmt).date()
        except ValueError: pass
    return None

def percentile(values, p):
    if not values: return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]

def audit(input_path):
    groups = defaultdict(list)
    required = {"station_id", "station_name", "state", "observed_at", "discharge_m3_s", "source_url"}
    with input_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = sorted(required - set(reader.fieldnames or []))
        if missing: raise ValueError(f"Missing normalized columns: {missing}")
        for row in reader:
            sid = (row.get("station_id") or "").strip()
            if sid: groups[sid].append(row)
    reports = []
    for sid, rows in sorted(groups.items()):
        dates, values, bad_dates, bad_values = [], [], 0, 0
        source_urls, station_names, rivers, basins = set(), set(), set(), set()
        for row in rows:
            d = parse_date(row.get("observed_at", ""))
            if d is None: bad_dates += 1
            else: dates.append(d)
            try:
                v = float(row.get("discharge_m3_s", ""))
                if not math.isfinite(v) or v < 0: raise ValueError
                values.append(v)
            except (ValueError, TypeError): bad_values += 1
            for key, bucket in [("source_url",source_urls),("station_name",station_names),("river",rivers),("basin",basins)]:
                if (row.get(key) or "").strip(): bucket.add(row[key].strip())
        counts = defaultdict(int)
        for d in dates: counts[d] += 1
        unique_dates = sorted(counts)
        gaps = max(0, (unique_dates[-1] - unique_dates[0]).days + 1 - len(unique_dates)) if unique_dates else None
        duplicates = sum(n - 1 for n in counts.values() if n > 1)
        span = (unique_dates[-1] - unique_dates[0]).days + 1 if len(unique_dates) >= 2 else (1 if unique_dates else 0)
        reports.append({
            "station_id": sid,
            "station_name": sorted(station_names),
            "states": sorted({(r.get("state") or "").strip() for r in rows if (r.get("state") or "").strip()}),
            "rivers": sorted(rivers), "basins": sorted(basins),
            "row_count": len(rows), "valid_timestamp_rows": len(dates),
            "invalid_timestamp_rows": bad_dates, "invalid_discharge_rows": bad_values,
            "first_date": str(unique_dates[0]) if unique_dates else None,
            "last_date": str(unique_dates[-1]) if unique_dates else None,
            "calendar_span_days": span, "unique_observation_dates": len(unique_dates),
            "missing_calendar_days": gaps, "duplicate_rows_on_same_date": duplicates,
            "rows_per_observation_date_min": min(counts.values()) if counts else None,
            "rows_per_observation_date_max": max(counts.values()) if counts else None,
            "discharge_min_m3_s": min(values) if values else None,
            "discharge_p50_m3_s": percentile(values, .50),
            "discharge_p95_m3_s": percentile(values, .95),
            "discharge_p99_m3_s": percentile(values, .99),
            "discharge_max_m3_s": max(values) if values else None,
            "source_urls": sorted(source_urls),
            "review_flags": [
                flag for flag, condition in [
                    ("multiple_station_names", len(station_names) > 1),
                    ("multiple_rivers", len(rivers) > 1),
                    ("multiple_basins", len(basins) > 1),
                    ("multiple_source_urls", len(source_urls) > 1),
                    ("invalid_timestamps", bad_dates > 0),
                    ("invalid_discharge_values", bad_values > 0),
                    ("same_date_duplicates", duplicates > 0),
                    ("sparse_calendar_coverage", gaps is not None and span > 0 and gaps / span > .10),
                    ("large_values_require_domain_review", bool(values) and max(values) > 100000),
                ] if condition
            ],
        })
    summary = {
        "status": "station_level_quality_audit_not_forecast_validation",
        "input": str(input_path), "stations_audited": len(reports),
        "stations_with_review_flags": sum(bool(r["review_flags"]) for r in reports),
        "total_rows": sum(r["row_count"] for r in reports),
        "total_same_date_duplicates": sum(r["duplicate_rows_on_same_date"] for r in reports),
        "total_missing_calendar_days_across_station_spans": sum(r["missing_calendar_days"] or 0 for r in reports),
        "station_reports": reports,
        "warning": "Daily gap and duplicate counts are screening metrics. Multiple observations per day may be valid source measurements. Extreme values are flagged for human review, never auto-deleted.",
    }
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=pathlib.Path)
    p.add_argument("--output", required=True, type=pathlib.Path)
    a=p.parse_args()
    result=audit(a.input)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({k:result[k] for k in ["status","stations_audited","stations_with_review_flags","total_rows","total_same_date_duplicates","total_missing_calendar_days_across_station_spans"]},indent=2))
if __name__=="__main__": main()
