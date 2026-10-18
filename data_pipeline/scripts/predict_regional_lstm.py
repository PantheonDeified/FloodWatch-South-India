#!/usr/bin/env python3
"""Run an experimental regional discharge LSTM on the latest eligible station history.

This emits a reproducible research forecast and a persistence comparison. It is
not a flood-probability model, and its output must not drive public warnings.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import torch

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from train_regional_lstm import RegionalLSTM, STATES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", required=True, type=pathlib.Path)
    parser.add_argument("--model-file", required=True, type=pathlib.Path)
    parser.add_argument("--scalers-file", required=True, type=pathlib.Path)
    parser.add_argument("--report-file", required=True, type=pathlib.Path)
    parser.add_argument("--output-file", required=True, type=pathlib.Path)
    parser.add_argument("--station-id", default="", help="Exact station ID; if omitted, choose the eligible station with the latest history.")
    parser.add_argument("--lookback-days", type=int, default=90)
    args = parser.parse_args()

    if args.lookback_days < 14:
        raise SystemExit("--lookback-days must be at least 14.")
    for path in (args.observations, args.model_file, args.scalers_file, args.report_file):
        if not path.is_file():
            raise SystemExit(f"Required input file not found: {path}")

    report = json.loads(args.report_file.read_text(encoding="utf-8"))
    scalers = json.loads(args.scalers_file.read_text(encoding="utf-8"))
    horizon = int(report.get("lead_days", 7))
    lookback = int(report.get("lookback_days", args.lookback_days))
    if args.lookback_days != lookback:
        raise SystemExit(f"Model requires --lookback-days {lookback}; received {args.lookback_days}.")
    mu = float(scalers["discharge_log1p_mean"])
    sd = float(scalers["discharge_log1p_std"])
    if not np.isfinite(mu) or not np.isfinite(sd) or sd <= 0:
        raise SystemExit("Invalid or missing training normalization values.")

    required = ["station_id", "state", "latitude", "longitude", "observed_at", "discharge_m3_s"]
    frame = pd.read_csv(args.observations, dtype={"station_id": str, "state": str})
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise SystemExit(f"Observation table is missing required columns: {missing}")
    frame = frame[frame["state"].astype(str).str.casefold().isin({s.casefold() for s in STATES})].copy()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], errors="coerce")
    frame["discharge_m3_s"] = pd.to_numeric(frame["discharge_m3_s"], errors="coerce")
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    frame = frame.dropna(subset=["station_id", "observed_at", "discharge_m3_s"])
    frame = frame[frame["discharge_m3_s"] >= 0].copy()
    if frame.empty:
        raise SystemExit("No valid regional discharge observations.")

    frame["date"] = frame["observed_at"].dt.normalize()
    frame["latitude"] = frame["latitude"].fillna(0).clip(-90, 90) / float(scalers.get("latitude_divisor", 90))
    frame["longitude"] = frame["longitude"].fillna(0).clip(-180, 180) / float(scalers.get("longitude_divisor", 180))
    candidates = []
    for station_id, group in frame.groupby("station_id", sort=True):
        if args.station_id and str(station_id) != str(args.station_id):
            continue
        series = group.groupby("date")["discharge_m3_s"].max().sort_index()
        if series.empty:
            continue
        end = pd.Timestamp(series.index.max()).normalize()
        start = end - pd.Timedelta(days=lookback - 1)
        dates = pd.date_range(start, end, freq="D")
        values = series.reindex(dates).to_numpy(dtype=float)
        mask = np.isfinite(values)
        if mask.mean() < 0.8:
            continue
        eligible = group[group["station_id"].astype(str) == str(station_id)]
        lat = float(eligible["latitude"].median()) if eligible["latitude"].notna().any() else 0.0
        lon = float(eligible["longitude"].median()) if eligible["longitude"].notna().any() else 0.0
        candidates.append((end, str(station_id), str(group["state"].iloc[0]), dates, values, mask, lat, lon, int(mask.sum())))
    if not candidates:
        note = f" for station {args.station_id}" if args.station_id else ""
        raise SystemExit(f"No station has at least 80% valid discharge days in the last {lookback} calendar days{note}.")

    # If not explicitly selected, prefer the newest complete-enough daily history.
    end, station_id, state, dates, values, mask, lat, lon, valid_days = max(candidates, key=lambda row: (row[0], row[8]))
    log_values = np.full(lookback, np.nan, dtype=np.float32)
    log_values[mask] = np.log1p(values[mask]).astype(np.float32)
    scaled = (log_values - mu) / sd
    scaled[~mask] = 0.0
    doy = dates.dayofyear.to_numpy(dtype=float)
    angle = 2 * np.pi * doy / 365.25
    x = np.column_stack([
        scaled,
        mask.astype(float),
        np.sin(angle),
        np.cos(angle),
        np.full(lookback, lat, dtype=float),
        np.full(lookback, lon, dtype=float),
    ]).astype(np.float32)
    if x.shape != (lookback, 6) or not np.isfinite(x).all():
        raise SystemExit(f"Invalid input tensor: shape={x.shape}; non-finite values={int((~np.isfinite(x)).sum())}.")

    torch.manual_seed(42)
    model = RegionalLSTM(horizon)
    try:
        state_dict = torch.load(args.model_file, map_location="cpu", weights_only=True)
    except TypeError:  # PyTorch versions predating weights_only
        state_dict = torch.load(args.model_file, map_location="cpu")
    model.load_state_dict(state_dict, strict=True)
    model.eval()
    with torch.inference_mode():
        scaled_prediction = model(torch.from_numpy(x[None, :, :])).cpu().numpy().reshape(-1)
    predicted = np.expm1(np.maximum(scaled_prediction * sd + mu, 0.0))
    observed_last = float(values[mask][-1])
    forecast_dates = [(end + pd.Timedelta(days=i)).date().isoformat() for i in range(1, horizon + 1)]
    output = {
        "model_type": report.get("model_type", "regional discharge LSTM"),
        "status": "experimental_research_only",
        "operational_status": "not_validated_for_public_warnings",
        "station_id": station_id,
        "state": state,
        "forecast_origin_date": end.date().isoformat(),
        "history_window_start": dates[0].date().isoformat(),
        "history_window_end": dates[-1].date().isoformat(),
        "valid_history_days": valid_days,
        "history_days_required": lookback,
        "last_observed_discharge_m3_s": observed_last,
        "forecast": [
            {"date": date, "predicted_discharge_m3_s": float(value),
             "persistence_baseline_discharge_m3_s": observed_last}
            for date, value in zip(forecast_dates, predicted.tolist())
        ],
        "model_artifact": str(args.model_file),
        "scalers_artifact": str(args.scalers_file),
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "limitations": [
            "Input is historical daily discharge only; no future weather/rainfall forcing.",
            "Predicted discharge is not water level, flood probability, inundation depth, or an official alert.",
            "Station history is chosen from source observation dates and may be delayed; inspect data provenance and freshness.",
            "Use a separately validated model and human review before any public-warning integration.",
        ],
    }
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({**output, "forecast": output["forecast"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
