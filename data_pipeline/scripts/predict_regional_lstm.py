#!/usr/bin/env python3
"""Emit a research-only regional LSTM discharge forecast from the latest eligible station history.

The model uses historic observed discharge, an observation mask, seasonal encoding and
station coordinates only. This is an inference-integrity smoke test, not a live flood
forecast, flood probability, water-level estimate, or public warning.
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
    parser.add_argument("--station-id", default="", help="Optional exact station ID to forecast.")
    parser.add_argument("--lookback-days", type=int, default=90)
    parser.add_argument("--all-stations", action="store_true", help="Forecast every station with enough recent history; include source coordinates and station-relative peak-flow percentiles.")
    args = parser.parse_args()

    if args.lookback_days < 14:
        raise SystemExit("--lookback-days must be at least 14.")
    for path in (args.observations, args.model_file, args.scalers_file, args.report_file):
        if not path.is_file():
            raise SystemExit(f"Required model/inference input does not exist: {path}")

    report = json.loads(args.report_file.read_text(encoding="utf-8"))
    scalers = json.loads(args.scalers_file.read_text(encoding="utf-8"))
    horizon = int(report.get("lead_days", 7))
    lookback = int(report.get("lookback_days", args.lookback_days))
    if args.lookback_days != lookback:
        raise SystemExit(f"Model requires --lookback-days {lookback}; received {args.lookback_days}.")
    # Current regional trainer's artifact schema uses these exact global transform fields.
    mu = float(scalers["global_log1p_mean"])
    sd = float(scalers["global_log1p_std"])
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
    # Keep inference aligned with the trainer's normalized coordinate features.
    frame["latitude"] = frame["latitude"].clip(-90, 90) / 90.0
    frame["longitude"] = frame["longitude"].clip(-180, 180) / 180.0
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
        lat = float(group["latitude"].median()) if group["latitude"].notna().any() else 0.0
        lon = float(group["longitude"].median()) if group["longitude"].notna().any() else 0.0
        candidates.append((end, str(station_id), str(group["state"].iloc[0]), dates, values, mask, lat, lon, int(mask.sum())))
    if not candidates:
        suffix = f" for station {args.station_id}" if args.station_id else ""
        raise SystemExit(f"No station has at least 80% valid discharge days in the latest {lookback}-day window{suffix}.")

    if not candidates:
        suffix = f" for station {args.station_id}" if args.station_id else ""
        raise SystemExit(f"No station has at least 80% valid discharge days in the latest {lookback}-day window{suffix}.")

    chosen = sorted(candidates, key=lambda row: (row[0], row[8], row[1]), reverse=True)
    if not args.all_stations:
        chosen = chosen[:1]

    architecture = report.get("architecture", {})
    model = RegionalLSTM(
        horizon,
        hidden_size=int(architecture.get("hidden_size", 48)),
        num_layers=int(architecture.get("num_layers", 1)),
    )
    try:
        weights = torch.load(args.model_file, map_location="cpu", weights_only=True)
    except TypeError:
        weights = torch.load(args.model_file, map_location="cpu")
    model.load_state_dict(weights, strict=True)
    model.eval()

    # Match the validation-selected blend saved by the training pipeline.
    blend_alpha = float(scalers.get("validation_blend_alpha", 1.0))
    if not np.isfinite(blend_alpha) or blend_alpha < 0.0 or blend_alpha > 1.0:
        raise SystemExit("Model scaler metadata has an invalid validation_blend_alpha; expected [0,1].")

    station_forecasts = []
    for end, station_id, state, dates, values, mask, lat, lon, valid_days in chosen:
        log_values = np.full(lookback, np.nan, dtype=np.float32)
        log_values[mask] = np.log1p(values[mask]).astype(np.float32)
        scaled = (log_values - mu) / sd
        scaled[~mask] = 0.0
        angle = 2 * np.pi * dates.dayofyear.to_numpy(dtype=float) / 365.25
        x = np.column_stack([
            scaled, mask.astype(float), np.sin(angle), np.cos(angle),
            np.full(lookback, lat), np.full(lookback, lon),
        ]).astype(np.float32)
        if x.shape != (lookback, 6) or not np.isfinite(x).all():
            raise SystemExit(f"Invalid model input tensor for station {station_id}.")

        with torch.inference_mode():
            prediction_scaled = model(torch.from_numpy(x[None, :, :])).cpu().numpy().reshape(-1)
        lstm_prediction = np.expm1(np.maximum(prediction_scaled * sd + mu, 0.0))
        last_observed = float(values[mask][-1])
        persistence = np.full(horizon, last_observed, dtype=float)
        predicted = np.maximum((1.0 - blend_alpha) * persistence + blend_alpha * lstm_prediction, 0.0)
        valid_dates = [(end + pd.Timedelta(days=i)).date().isoformat() for i in range(1, horizon + 1)]
        history_age_days = max(0, (pd.Timestamp.now(tz="UTC").date() - end.date()).days)
        history_freshness = "recent_source_history" if history_age_days <= 3 else "stale_historical_replay"

        # This is a station-relative discharge rank, NOT a calibrated flood probability.
        station_rows = frame.loc[frame["station_id"].astype(str).eq(station_id)]
        hist_values = station_rows.loc[station_rows["observed_at"] < end, "discharge_m3_s"].to_numpy(dtype=float)
        hist_values = hist_values[np.isfinite(hist_values) & (hist_values >= 0)]
        peak = float(np.max(predicted)) if len(predicted) else float("nan")
        peak_percentile = (
            float(100.0 * (np.sum(hist_values < peak) + 0.5 * np.sum(hist_values == peak)) / len(hist_values))
            if len(hist_values) >= 30 and np.isfinite(peak) else None
        )

        station_forecasts.append({
            "station_id": station_id,
            "state": state,
            "station_latitude": float(lat * 90.0) if np.isfinite(lat) else None,
            "station_longitude": float(lon * 180.0) if np.isfinite(lon) else None,
            "coordinates_available": bool(np.isfinite(lat) and np.isfinite(lon) and abs(lat * 90.0) <= 21.8 and 73.0 <= lon * 180.0 <= 87.0),
            "model_type": (
                "persistence_baseline_selected_by_validation"
                if blend_alpha <= 1e-12 else
                "validation_selected_lstm_persistence_blend"
                if blend_alpha < 1.0 - 1e-12 else
                "regional_discharge_lstm"
            ),
            "validation_blend_alpha": blend_alpha,
            "forecast_is_live": bool(history_age_days <= 3),
            "history_freshness": history_freshness,
            "history_age_days": int(history_age_days),
            "forecast_origin_date": end.date().isoformat(),
            "history_window_start": dates[0].date().isoformat(),
            "history_window_end": dates[-1].date().isoformat(),
            "valid_history_days": int(valid_days),
            "history_days_required": lookback,
            "last_observed_discharge_m3_s": last_observed,
            "predicted_peak_discharge_m3_s": peak,
            "peak_discharge_percentile_all_available_history": peak_percentile,
            "history_discharge_sample_count": int(len(hist_values)),
            "forecast": [
                {"date": date, "predicted_discharge_m3_s": float(selected_value),
                 "lstm_discharge_m3_s": float(lstm_value),
                 "persistence_baseline_discharge_m3_s": last_observed}
                for date, selected_value, lstm_value in zip(valid_dates, predicted.tolist(), lstm_prediction.tolist())
            ],
        })

    if not station_forecasts:
        raise SystemExit("No stations produced valid regional forecasts.")
    primary = station_forecasts[0]
    output = {
        **primary,
        "station_forecasts": station_forecasts if args.all_stations else None,
        "forecast_station_count": len(station_forecasts),
        "forecast_mode": "all_eligible_stations" if args.all_stations else "single_latest_eligible_station",
        "model_type": "regional_discharge_lstm_with_validation_selected_persistence_blend",
        "raw_neural_network_model_type": report.get("model_type", "regional discharge LSTM"),
        "validation_blend_selection": scalers.get("validation_blend_selection", "Older artifact: no validation blend metadata; raw LSTM output selected."),
        "status": "experimental_research_only",
        "operational_status": "not_validated_for_public_warnings",
        "model_created_at_utc": report.get("created_at_utc"),
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "warning": "This is a historical-discharge-only forecast. Source-history age is not proof of a live sensor feed. Station-relative discharge percentiles are not calibrated flood probabilities or official warnings.",
        "limitations": [
            "Uses historical discharge only; no future rainfall/weather forcing.",
            "Output is discharge and a station-relative historic discharge rank, not flood probability, water level, depth, inundation extent, or official alert.",
            "Station coordinates, station identity, river routing, source timestamps and catchment transfer require independent review.",
            "Do not use this artifact alone for public warnings or evacuation decisions.",
        ],
        "model_artifact": str(args.model_file),
        "scalers_artifact": str(args.scalers_file),
    }
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
