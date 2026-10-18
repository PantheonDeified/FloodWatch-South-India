#!/usr/bin/env python3
"""Combine station-catalog and discharge-audit outputs into a conservative review queue.

The score is a triage aid only. It never certifies station identity, coordinates,
hydrological suitability, or model readiness.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
from typing import Any

IDENTITY_FLAGS = {
    "multiple_station_names",
    "multiple_rivers",
    "multiple_basins",
    "multiple_source_urls",
}
DATA_FLAGS = {
    "invalid_timestamps",
    "invalid_discharge_values",
    "same_date_duplicates",
    "sparse_calendar_coverage",
    "large_values_require_domain_review",
}


def load_catalog(path: pathlib.Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"station_id", "coordinate_verified", "coordinate_source_url"}
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"Station catalogue is missing required columns: {missing}")
        result: dict[str, dict[str, str]] = {}
        for row in reader:
            station_id = (row.get("station_id") or "").strip()
            if station_id:
                if station_id in result:
                    raise ValueError(f"Duplicate station_id in catalogue: {station_id}")
                result[station_id] = row
        return result


def load_audit(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    reports = payload.get("station_reports")
    if not isinstance(reports, list):
        raise ValueError("Audit JSON must contain a station_reports array")
    result = {}
    for row in reports:
        if not isinstance(row, dict) or not str(row.get("station_id", "")).strip():
            continue
        station_id = str(row["station_id"]).strip()
        if station_id in result:
            raise ValueError(f"Duplicate station_id in audit: {station_id}")
        result[station_id] = row
    return result


def truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "verified"}


def build_queue(
    catalog: dict[str, dict[str, str]],
    audits: dict[str, dict[str, Any]],
    min_span_days: int = 365,
    min_unique_dates: int = 180,
    min_coverage: float = 0.75,
) -> dict[str, Any]:
    rows = []
    for station_id in sorted(set(catalog) | set(audits)):
        c = catalog.get(station_id, {})
        a = audits.get(station_id, {})
        flags = sorted(set(a.get("review_flags") or []))
        row_count = int(a.get("row_count") or c.get("record_count") or 0)
        unique_dates = int(a.get("unique_observation_dates") or 0)
        span_days = int(a.get("calendar_span_days") or 0)
        gaps_raw = a.get("missing_calendar_days")
        gaps = int(gaps_raw) if gaps_raw is not None else None
        coverage = (unique_dates / span_days) if span_days > 0 else 0.0
        coverage = min(1.0, max(0.0, coverage))
        coordinate_verified = truthy(c.get("coordinate_verified"))
        coordinate_source = (c.get("coordinate_source_url") or "").strip()
        coord_gate_pass = coordinate_verified and bool(coordinate_source)
        identity_flags = sorted(set(flags) & IDENTITY_FLAGS)
        data_flags = sorted(set(flags) & DATA_FLAGS)
        enough_history = span_days >= min_span_days and unique_dates >= min_unique_dates
        reasons = []
        if station_id not in catalog:
            reasons.append("missing_station_catalogue_entry")
        if station_id not in audits:
            reasons.append("missing_discharge_audit")
        if not enough_history:
            reasons.append("short_or_sparse_record_history")
        if coverage < min_coverage:
            reasons.append("calendar_coverage_below_threshold")
        if identity_flags:
            reasons.append("station_identity_or_metadata_conflict")
        if data_flags:
            reasons.append("discharge_data_quality_flags")
        if not coord_gate_pass:
            reasons.append("coordinates_not_independently_verified")
        if station_id not in catalog or station_id not in audits:
            status = "incomplete_inputs"
        elif not enough_history:
            status = "insufficient_history_for_priority_review"
        elif identity_flags or coverage < min_coverage:
            status = "manual_data_review_required"
        elif data_flags:
            status = "manual_quality_review_required"
        else:
            status = "priority_for_manual_station_review"
        rows.append({
            "station_id": station_id,
            "station_name": "; ".join(a.get("station_name") or [c.get("station_name", "")]),
            "state": "; ".join(a.get("states") or [c.get("state", "")]),
            "river": "; ".join(a.get("rivers") or [c.get("river", "")]),
            "basin": "; ".join(a.get("basins") or [c.get("basin", "")]),
            "row_count": row_count,
            "unique_observation_dates": unique_dates,
            "calendar_span_days": span_days,
            "missing_calendar_days": gaps,
            "calendar_coverage_rate": round(coverage, 4),
            "first_date": a.get("first_date") or c.get("first_observed_at", ""),
            "last_date": a.get("last_date") or c.get("last_observed_at", ""),
            "review_flags": ";".join(flags),
            "coordinate_verified": str(coord_gate_pass).lower(),
            "coordinate_source_url": coordinate_source,
            "downstream_weather_join_allowed": str(coord_gate_pass and enough_history and coverage >= min_coverage and not identity_flags).lower(),
            "model_training_gate": "structural_review_only" if coord_gate_pass and enough_history and coverage >= min_coverage and not identity_flags and not data_flags else "blocked",
            "review_status": status,
            "review_reasons": ";".join(reasons),
        })
    # Review candidates with longer spans and better coverage first; stable station ID tie-break.
    rows.sort(key=lambda r: (
        r["review_status"] != "priority_for_manual_station_review",
        -r["calendar_span_days"],
        -r["calendar_coverage_rate"],
        r["state"].casefold(),
        r["station_name"].casefold(),
        r["station_id"],
    ))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["review_status"]] = counts.get(row["review_status"], 0) + 1
    return {
        "status": "station_review_triage_not_model_validation",
        "criteria": {
            "min_span_days": min_span_days,
            "min_unique_observation_dates": min_unique_dates,
            "min_calendar_coverage_rate": min_coverage,
        },
        "stations_in_catalogue": len(catalog),
        "stations_in_audit": len(audits),
        "stations_in_review_queue": len(rows),
        "status_counts": counts,
        "stations_allowed_for_weather_join": sum(r["downstream_weather_join_allowed"] == "true" for r in rows),
        "stations_structurally_eligible_for_human_model_review": sum(r["model_training_gate"] == "structural_review_only" for r in rows),
        "stations": rows,
        "warning": (
            "This is a configurable structural triage report only. It does not validate station identity, "
            "coordinate truth, catchment linkage, measurement validity, or forecast skill. Coordinate-based "
            "weather joins remain blocked unless coordinate_verified is true AND coordinate_source_url is non-empty."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=pathlib.Path, required=True)
    parser.add_argument("--audit", type=pathlib.Path, required=True)
    parser.add_argument("--out-csv", type=pathlib.Path, required=True)
    parser.add_argument("--out-json", type=pathlib.Path, required=True)
    parser.add_argument("--min-span-days", type=int, default=365)
    parser.add_argument("--min-unique-dates", type=int, default=180)
    parser.add_argument("--min-coverage", type=float, default=0.75)
    args = parser.parse_args()
    if args.min_span_days < 1 or args.min_unique_dates < 1:
        raise SystemExit("minimum history thresholds must be positive")
    if not math.isfinite(args.min_coverage) or not 0 <= args.min_coverage <= 1:
        raise SystemExit("--min-coverage must be between 0 and 1")
    try:
        catalog = load_catalog(args.catalog)
        audits = load_audit(args.audit)
        result = build_queue(catalog, audits, args.min_span_days, args.min_unique_dates, args.min_coverage)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    fields = list(result["stations"][0]) if result["stations"] else [
        "station_id", "station_name", "state", "river", "basin", "row_count",
        "unique_observation_dates", "calendar_span_days", "missing_calendar_days",
        "calendar_coverage_rate", "first_date", "last_date", "review_flags",
        "coordinate_verified", "coordinate_source_url", "downstream_weather_join_allowed",
        "model_training_gate", "review_status", "review_reasons"
    ]
    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(result["stations"])
    args.out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "status", "stations_in_catalogue", "stations_in_audit",
        "stations_in_review_queue", "status_counts", "stations_allowed_for_weather_join",
        "stations_structurally_eligible_for_human_model_review"
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
