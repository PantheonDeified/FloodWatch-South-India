#!/usr/bin/env python3
"""Run the rainfall-forced discharge research model with a supplied weather forecast."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

import numpy as np
import pandas as pd
import torch

from train_rainfall_forced_lstm import FEATURES, RainfallForcedLSTM


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", required=True, type=pathlib.Path, help="Daily feature table used by build_event_features.py.")
    ap.add_argument("--station-id", required=True)
    ap.add_argument("--rainfall-forecast", required=True, type=pathlib.Path,
                    help="CSV with date, precipitation_sum in mm, and optional station_id columns.")
    ap.add_argument("--model-file", required=True, type=pathlib.Path)
    ap.add_argument("--scalers-file", required=True, type=pathlib.Path)
    ap.add_argument("--report-file", required=True, type=pathlib.Path)
    ap.add_argument("--output", required=True, type=pathlib.Path)
    ap.add_argument("--max-history-age-days", type=int, default=3)
    args = ap.parse_args()
    for path in (args.features, args.rainfall_forecast, args.model_file, args.scalers_file, args.report_file):
        if not path.is_file(): raise SystemExit(f"Required input file does not exist: {path}")

    report = json.loads(args.report_file.read_text(encoding="utf-8"))
    scalers = json.loads(args.scalers_file.read_text(encoding="utf-8"))
    if scalers.get("features") != FEATURES: raise SystemExit("Model feature schema does not match this predictor.")
    lookback, lead = int(scalers["lookback_days"]), int(scalers["lead_days"])
    frame = pd.read_csv(args.features, dtype={"station_id": str})
    required = ["station_id", "date", *FEATURES]
    if missing := [c for c in required if c not in frame.columns]: raise SystemExit(f"Feature table is missing columns: {missing}.")
    frame = frame[frame["station_id"].astype(str).eq(str(args.station_id))].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for col in FEATURES: frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    if frame.empty: raise SystemExit("No feature rows for this station.")
    full = frame.set_index("date").asfreq("D")
    if len(full) < lookback: raise SystemExit(f"Need {lookback} calendar days of input history.")
    history = full[FEATURES].to_numpy(dtype=np.float64)[-lookback:]
    if not np.isfinite(history).all(): raise SystemExit("Recent station history has missing weather/discharge inputs; no gap filling is performed.")
    origin = pd.Timestamp(full.index[-1]).normalize()
    age_days = (pd.Timestamp.now(tz="UTC").date() - origin.date()).days
    if age_days < 0 or age_days > args.max_history_age_days:
        raise SystemExit(f"Latest feature date is {origin.date()} ({age_days} days old); max allowed is {args.max_history_age_days}.")
    expected_dates = pd.date_range(origin + pd.Timedelta(days=1), periods=lead, freq="D")

    rain = pd.read_csv(args.rainfall_forecast, dtype={"station_id": str})
    if not {"date", "precipitation_sum"}.issubset(rain.columns):
        raise SystemExit("Rainfall forecast CSV needs date and precipitation_sum columns.")
    if "station_id" in rain.columns:
        rain = rain[rain["station_id"].astype(str).eq(str(args.station_id))].copy()
    rain["date"] = pd.to_datetime(rain["date"], errors="coerce").dt.normalize()
    rain["precipitation_sum"] = pd.to_numeric(rain["precipitation_sum"], errors="coerce")
    rain = rain.dropna(subset=["date"]).drop_duplicates("date", keep="last").set_index("date")
    if not rain.index.is_unique: raise SystemExit("Rainfall forecast contains duplicate dates.")
    if not set(expected_dates).issubset(set(rain.index)):
        missing_days = sorted(d.date().isoformat() for d in set(expected_dates) - set(rain.index))
        raise SystemExit(f"Weather forecast is missing required lead dates: {missing_days}.")
    future_rain = rain.loc[expected_dates, "precipitation_sum"].to_numpy(dtype=np.float64)
    if not np.isfinite(future_rain).all() or np.any(future_rain < 0):
        raise SystemExit("Every forecast day needs a finite nonnegative precipitation_sum in millimetres.")

    x_mean = np.asarray(scalers["x_mean"], dtype=np.float32)
    x_std = np.asarray(scalers["x_std"], dtype=np.float32)
    x = ((history.astype(np.float32) - x_mean) / x_std)[None, :, :]
    rain_log = np.log1p(future_rain).astype(np.float32)
    forcing = ((rain_log - float(scalers["rain_mean"])) / float(scalers["rain_std"]))[None, :]
    model = RainfallForcedLSTM(len(FEATURES), 64, lead)
    try: weights = torch.load(args.model_file, map_location="cpu", weights_only=True)
    except TypeError: weights = torch.load(args.model_file, map_location="cpu")
    model.load_state_dict(weights, strict=True); model.eval()
    with torch.inference_mode():
        scaled = model(torch.from_numpy(x), torch.from_numpy(forcing)).numpy().reshape(-1)
    forecast = np.expm1(np.maximum(scaled * float(scalers["y_std"]) + float(scalers["y_mean"]), 0.0))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame({
        "station_id": str(args.station_id), "forecast_origin_date": origin.date().isoformat(),
        "date": expected_dates.strftime("%Y-%m-%d"),
        "forecast_rain_mm": future_rain,
        "predicted_discharge_m3_s": forecast,
    })
    out.to_csv(args.output, index=False)
    metadata = {
        "model_type": report.get("model_type"), "model_report": str(args.report_file),
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "station_id": str(args.station_id), "forecast_origin_date": origin.date().isoformat(),
        "history_age_days": int(age_days), "rainfall_forecast_file": str(args.rainfall_forecast),
        "output": str(args.output),
        "interpretation": "Experimental discharge forecast conditioned on the supplied daily precipitation forecast. Not a flood probability, stage forecast, inundation map, or official warning.",
        "warning": "Check the model report, station provenance and rainfall provider metadata. The training report used historical reanalysis as perfect future forcing, so validation may be optimistic compared with operational weather forecasts.",
    }
    args.output.with_suffix(args.output.suffix + ".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
