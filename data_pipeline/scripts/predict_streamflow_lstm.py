#!/usr/bin/env python3
"""Run a trained research-only single-gauge streamflow LSTM.

This produces model output, not an official warning. The model has no future
weather forecast inputs, so output should not be presented as a calibrated
operational forecast or flood probability.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

import numpy as np
import pandas as pd
import torch

from train_streamflow_lstm import FEATURES, TARGET, StreamflowLSTM


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", required=True, type=pathlib.Path)
    parser.add_argument("--station-id", required=True)
    parser.add_argument("--model", required=True, type=pathlib.Path)
    parser.add_argument("--scalers", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--lookback-days", type=int, default=90)
    parser.add_argument("--lead-days", type=int, default=7)
    args = parser.parse_args()

    if args.lookback_days < 14 or args.lead_days < 1:
        raise SystemExit("Use at least 14 lookback days and a positive forecast horizon.")
    if not args.model.is_file() or not args.scalers.is_file():
        raise SystemExit("Model weights or scaler file not found. Train the model first.")

    frame = pd.read_csv(args.features, dtype={"station_id": str})
    required = {"station_id", "date", *FEATURES}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(f"Feature file is missing required columns: {missing}")
    frame = frame[frame["station_id"].astype(str) == str(args.station_id)].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    for column in FEATURES:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame.empty:
        raise SystemExit("No feature rows found for this station.")

    frame = frame.set_index("date").asfreq("D")
    history = frame.tail(args.lookback_days)
    if len(history) != args.lookback_days:
        raise SystemExit(f"Need {args.lookback_days} consecutive calendar days of feature history.")
    values = history[FEATURES].to_numpy(dtype=np.float32)
    if not np.isfinite(values).all():
        raise SystemExit("The most recent lookback window has missing/non-finite values; do not silently impute it.")
    if history[TARGET].isna().any() or (history[TARGET] < 0).any():
        raise SystemExit("Recent discharge history is missing or negative; cannot produce a valid pilot forecast.")

    with np.load(args.scalers, allow_pickle=False) as scalers:
        x_mean = scalers["x_mean"].astype(np.float32)
        x_std = scalers["x_std"].astype(np.float32)
        y_mean = float(scalers["y_mean"])
        y_std = float(scalers["y_std"])
    if len(x_mean) != len(FEATURES) or len(x_std) != len(FEATURES) or np.any(x_std <= 0) or y_std <= 0:
        raise SystemExit("Scaler dimensions/values do not match this model's feature definition.")

    scaled = ((values - x_mean) / x_std)[None, :, :]
    model = StreamflowLSTM(n_features=len(FEATURES), hidden=64, lead_days=args.lead_days)
    state = torch.load(args.model, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        predicted_scaled = model(torch.from_numpy(scaled)).cpu().numpy().reshape(-1)
    predicted = np.maximum(predicted_scaled * y_std + y_mean, 0.0)

    last_observed_date = history.index[-1]
    dates = pd.date_range(last_observed_date + pd.Timedelta(days=1), periods=args.lead_days, freq="D")
    result = pd.DataFrame({
        "station_id": str(args.station_id),
        "forecast_date": dates.strftime("%Y-%m-%d"),
        "predicted_discharge_m3s": predicted,
        "model_type": "research-only single-gauge LSTM",
        "forecast_origin_date": last_observed_date.strftime("%Y-%m-%d"),
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    metadata = {
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "station_id": str(args.station_id),
        "last_observed_date": last_observed_date.strftime("%Y-%m-%d"),
        "forecast_horizon_days": args.lead_days,
        "model_file": str(args.model),
        "data_file": str(args.features),
        "output_file": str(args.output),
        "operational_status": "research_only_not_validated_for_public_warnings",
        "future_weather_inputs": False,
        "flood_probability": None,
        "warnings": [
            "This model does not use future weather forecasts.",
            "Do not interpret discharge predictions as water level, inundation extent, or flood probability.",
            "Check the training report and persistence-baseline skill before using the output for any research comparison.",
        ],
    }
    args.output.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
