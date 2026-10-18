#!/usr/bin/env python3
"""Generate a research-only forecast from a trained discharge-only LSTM."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

import numpy as np
import pandas as pd
import torch
from torch import nn


class DischargeLSTM(nn.Module):
    def __init__(self, hidden: int, horizon: int):
        super().__init__()
        self.encoder = nn.LSTM(input_size=1, hidden_size=hidden, num_layers=1, batch_first=True)
        self.head = nn.Sequential(
            nn.Dropout(0.15),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, horizon),
        )

    def forward(self, x):
        sequence, _ = self.encoder(x)
        return self.head(sequence[:, -1, :])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--observations", required=True, type=pathlib.Path)
    ap.add_argument("--station-id", required=True)
    ap.add_argument("--model", required=True, type=pathlib.Path)
    ap.add_argument("--scalers", required=True, type=pathlib.Path)
    ap.add_argument("--output", required=True, type=pathlib.Path)
    ap.add_argument("--lookback-days", type=int, default=90)
    ap.add_argument("--lead-days", type=int, default=7)
    args = ap.parse_args()
    if args.lookback_days < 14 or args.lead_days < 1:
        raise SystemExit("Use at least 14 lookback days and a positive forecast horizon.")
    if not args.model.is_file() or not args.scalers.is_file():
        raise SystemExit("Trained model weights or scaler file not found.")

    frame = pd.read_csv(
        args.observations,
        usecols=["station_id", "observed_at", "discharge_m3_s"],
        dtype={"station_id": str},
    )
    frame = frame[frame["station_id"].astype(str) == str(args.station_id)].copy()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], errors="coerce")
    frame["discharge_m3_s"] = pd.to_numeric(frame["discharge_m3_s"], errors="coerce")
    frame = frame.dropna(subset=["observed_at", "discharge_m3_s"])
    frame = frame[frame["discharge_m3_s"] >= 0]
    if frame.empty:
        raise SystemExit(f"No valid discharge history for station {args.station_id!r}.")
    frame["date"] = frame["observed_at"].dt.normalize()
    daily = frame.groupby("date")["discharge_m3_s"].max().sort_index()
    full_index = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    series = daily.reindex(full_index).astype("float64")
    history = series.tail(args.lookback_days)
    if len(history) != args.lookback_days or not np.isfinite(history.to_numpy()).all():
        raise SystemExit(
            f"The latest {args.lookback_days} calendar days contain missing observations. "
            "Do not silently fill gaps; select a station with current contiguous data."
        )

    with np.load(args.scalers, allow_pickle=False) as scaler:
        x_mean = float(scaler["x_mean"])
        x_std = float(scaler["x_std"])
        y_mean = float(scaler["y_mean"])
        y_std = float(scaler["y_std"])
    if x_std <= 0 or y_std <= 0:
        raise SystemExit("Invalid model scaler values.")
    x = ((history.to_numpy(dtype=np.float32)[:, None] - x_mean) / x_std)[None, :, :]
    model = DischargeLSTM(hidden=64, horizon=args.lead_days)
    state = torch.load(args.model, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        scaled_prediction = model(torch.from_numpy(x)).numpy().reshape(-1)
    prediction = np.maximum(scaled_prediction * y_std + y_mean, 0.0)

    last_date = history.index[-1]
    forecast_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=args.lead_days, freq="D")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = pd.DataFrame({
        "station_id": str(args.station_id),
        "forecast_date": forecast_dates.strftime("%Y-%m-%d"),
        "predicted_daily_max_discharge_m3s": prediction,
        "forecast_origin_date": last_date.strftime("%Y-%m-%d"),
        "model_type": "research-only discharge LSTM",
    })
    result.to_csv(args.output, index=False)

    now_date = dt.datetime.now(dt.timezone.utc).date()
    observation_age_days = (now_date - last_date.date()).days
    metadata = {
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "station_id": str(args.station_id),
        "last_observed_date": last_date.strftime("%Y-%m-%d"),
        "observation_age_days": observation_age_days,
        "freshness_status": "recent_observations" if observation_age_days <= 14 else "stale_historical_observations",
        "forecast_horizon_days": args.lead_days,
        "output_file": str(args.output),
        "operational_status": "research_only_not_validated_for_public_warnings",
        "target": "daily maximum observed discharge (m3/s)",
        "warnings": [
            "This model uses historical discharge only; no rainfall or future-weather forecasts are included.",
            "Predictions are discharge estimates, not river level, flood probability, or inundation extent.",
            "If observations are stale, the output is a historical extrapolation and must not be presented as a live forecast.",
            "Do not use for public warnings without independent event-based validation and human review.",
        ],
    }
    args.output.with_suffix(args.output.suffix + ".metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
