#!/usr/bin/env python3
"""Audit which stations have enough aligned daily data to attempt an LSTM pilot."""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np
import pandas as pd

FEATURES = [
    "precipitation_sum", "temperature_2m_mean", "temperature_2m_max",
    "temperature_2m_min", "wind_speed_10m_max", "rain_sum_3d_mm",
    "rain_sum_7d_mm", "rain_sum_14d_mm", "rain_sum_30d_mm",
    "river_discharge_last_m3s",
]
TARGET = "river_discharge_last_m3s"


def audit_station(group: pd.DataFrame, lookback: int, lead: int, min_windows: int) -> dict:
    station_id = str(group["station_id"].iloc[0])
    group = group.copy()
    group["date"] = pd.to_datetime(group["date"], errors="coerce")
    group = group.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    for col in FEATURES:
        group[col] = pd.to_numeric(group[col], errors="coerce")
    if group.empty:
        return {"station_id": station_id, "eligible_for_training_attempt": False, "reason": "no valid dates"}
    full = group.set_index("date").asfreq("D")
    n_days = len(full)
    values = full[FEATURES].to_numpy(dtype=np.float64)
    targets = full[TARGET].to_numpy(dtype=np.float64)
    complete_windows = 0
    valid_origins = []
    for origin in range(lookback - 1, n_days - lead):
        x = values[origin - lookback + 1:origin + 1]
        y = targets[origin + 1:origin + lead + 1]
        if np.isfinite(x).all() and np.isfinite(y).all() and (y >= 0).all():
            complete_windows += 1
            valid_origins.append(origin)
    train_cut, val_cut = int(n_days * .70), int(n_days * .85)
    train_windows = sum(origin + lead < train_cut for origin in valid_origins)
    val_windows = sum(origin >= train_cut and origin + lead < val_cut for origin in valid_origins)
    test_windows = sum(origin >= val_cut for origin in valid_origins)
    reasons = []
    if n_days < lookback + lead + 120:
        reasons.append("insufficient calendar span")
    if complete_windows < min_windows:
        reasons.append("too few complete input/target windows")
    if train_windows < 50 or val_windows < 10 or test_windows < 10:
        reasons.append("chronological split too small")
    finite_target = targets[np.isfinite(targets)]
    if finite_target.size and (finite_target < 0).any():
        reasons.append("negative discharge values")
    if finite_target.size == 0:
        reasons.append("no numeric discharge targets")
    return {
        "station_id": station_id,
        "first_date": str(full.index.min().date()),
        "last_date": str(full.index.max().date()),
        "calendar_days": int(n_days),
        "discharge_days": int(np.isfinite(targets).sum()),
        "missing_discharge_days": int((~np.isfinite(targets)).sum()),
        "complete_windows": int(complete_windows),
        "train_windows": int(train_windows),
        "validation_windows": int(val_windows),
        "test_windows": int(test_windows),
        "eligible_for_training_attempt": not reasons,
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", required=True, type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path)
    parser.add_argument("--lookback-days", type=int, default=90)
    parser.add_argument("--lead-days", type=int, default=7)
    parser.add_argument("--min-complete-windows", type=int, default=100)
    args = parser.parse_args()
    if args.lookback_days < 14 or args.lead_days < 1 or args.min_complete_windows < 1:
        raise SystemExit("Lookback must be >=14; lead and minimum windows must be positive.")
    frame = pd.read_csv(args.features, dtype={"station_id": str})
    required = {"station_id", "date", *FEATURES}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(f"Feature file is missing required columns: {missing}")
    frame = frame.dropna(subset=["station_id"])
    reports = [
        audit_station(group, args.lookback_days, args.lead_days, args.min_complete_windows)
        for _, group in frame.groupby("station_id", sort=True)
    ]
    result = {
        "status": "readiness_audit_only_not_model_evaluation",
        "feature_file": str(args.features),
        "lookback_days": args.lookback_days,
        "lead_days": args.lead_days,
        "stations_checked": len(reports),
        "stations_eligible_for_training_attempt": sum(r["eligible_for_training_attempt"] for r in reports),
        "station_reports": reports,
        "warning": "Eligibility only means the file passes minimum structural checks. It does not prove unit correctness, source provenance, basin connectivity, model skill, or forecast validity.",
    }
    output = json.dumps(result, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
