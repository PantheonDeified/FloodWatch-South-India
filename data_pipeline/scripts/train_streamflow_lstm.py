#!/usr/bin/env python3
"""Train a research-only daily streamflow LSTM for one verified gauge.

This is a small pilot model, not Google's complete Mean Embedding Forecast LSTM.
It uses observed discharge and recent historical weather to forecast the next
seven daily discharge values. It requires real station discharge, not water levels.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import random
import sys

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

FEATURES = [
    "precipitation_sum", "temperature_2m_mean", "temperature_2m_max",
    "temperature_2m_min", "wind_speed_10m_max", "rain_sum_3d_mm",
    "rain_sum_7d_mm", "rain_sum_14d_mm", "rain_sum_30d_mm",
    "river_discharge_last_m3s",
]
TARGET = "river_discharge_last_m3s"


class StreamflowLSTM(nn.Module):
    def __init__(self, n_features: int, hidden: int, lead_days: int):
        super().__init__()
        self.encoder = nn.LSTM(n_features, hidden, batch_first=True)
        self.dropout = nn.Dropout(0.15)
        self.head = nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, lead_days))

    def forward(self, x):
        sequence, _ = self.encoder(x)
        return self.head(self.dropout(sequence[:, -1, :]))


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    error = predicted - actual
    rmse = float(np.sqrt(np.mean(error ** 2)))
    mae = float(np.mean(np.abs(error)))
    denom = float(np.sum((actual - actual.mean()) ** 2))
    nse = float(1.0 - np.sum(error ** 2) / denom) if denom > 0 else None
    return {"mae_m3s": mae, "rmse_m3s": rmse, "nse": nse, "samples": int(actual.size)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", required=True, type=pathlib.Path)
    ap.add_argument("--station-id", required=True)
    ap.add_argument("--output-dir", required=True, type=pathlib.Path)
    ap.add_argument("--lookback-days", type=int, default=90)
    ap.add_argument("--lead-days", type=int, default=7)
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--patience", type=int, default=12)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if args.lookback_days < 14 or args.lead_days < 1:
        raise SystemExit("Use at least 14 history days and a positive forecast horizon.")
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    frame = pd.read_csv(args.features, dtype={"station_id": str})
    frame = frame[frame["station_id"].astype(str) == str(args.station_id)].copy()
    missing_cols = [c for c in ["date", *FEATURES] if c not in frame.columns]
    if missing_cols:
        raise SystemExit(f"Feature file misses required columns: {missing_cols}. Did build_event_features.py run with daily discharge?")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    for col in FEATURES:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if frame.empty:
        raise SystemExit("No rows for this station.")
    if len(frame) < args.lookback_days + args.lead_days + 120:
        raise SystemExit("Not enough data. Need at least lookback + forecast horizon + 120 daily records before evaluating a model.")
    # Do not fill observation gaps; insert calendar days and leave target/inputs missing.
    full = frame.set_index("date").asfreq("D")
    full["station_id"] = str(args.station_id)
    dates = full.index
    x_values = full[FEATURES].to_numpy(dtype=np.float32)
    y_values = full[TARGET].to_numpy(dtype=np.float32)

    origins, x_seq, y_seq = [], [], []
    lookback, lead = args.lookback_days, args.lead_days
    for origin in range(lookback - 1, len(full) - lead):
        start, end = origin - lookback + 1, origin + lead + 1
        hx = x_values[start:origin + 1]
        fy = y_values[origin + 1:origin + lead + 1]
        if hx.shape[0] != lookback or fy.shape[0] != lead:
            continue
        if not np.isfinite(hx).all() or not np.isfinite(fy).all():
            continue
        origins.append(origin)
        x_seq.append(hx)
        y_seq.append(fy)
    if len(origins) < 100:
        raise SystemExit(f"Only {len(origins)} complete sequence windows. Need at least 100; check gauge discharge continuity and daily weather alignment.")
    origins = np.asarray(origins)
    x_seq = np.asarray(x_seq, dtype=np.float32)
    y_seq = np.asarray(y_seq, dtype=np.float32)
    n_days = len(full)
    train_cut, val_cut = int(n_days * 0.70), int(n_days * 0.85)
    train_mask = origins + lead < train_cut
    val_mask = (origins >= train_cut) & (origins + lead < val_cut)
    test_mask = origins >= val_cut
    if train_mask.sum() < 50 or val_mask.sum() < 10 or test_mask.sum() < 10:
        raise SystemExit("Chronological split is too small for honest evaluation; use a longer discharge record.")
    x_train, y_train = x_seq[train_mask], y_seq[train_mask]
    x_val, y_val = x_seq[val_mask], y_seq[val_mask]
    x_test, y_test = x_seq[test_mask], y_seq[test_mask]

    # Fit normalizers on training observations only to avoid test-period leakage.
    x_mean = x_train.reshape(-1, len(FEATURES)).mean(axis=0)
    x_std = x_train.reshape(-1, len(FEATURES)).std(axis=0)
    x_std[x_std < 1e-6] = 1.0
    y_mean = float(y_train.mean())
    y_std = float(y_train.std())
    if y_std < 1e-6:
        raise SystemExit("Training discharge target has near-zero variation.")
    x_train = (x_train - x_mean) / x_std
    x_val = (x_val - x_mean) / x_std
    x_test = (x_test - x_mean) / x_std
    y_train = (y_train - y_mean) / y_std
    y_val = (y_val - y_mean) / y_std
    y_test_scaled = y_test.copy()
    y_train = (y_train - 0.0)
    y_val = (y_val - 0.0)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = StreamflowLSTM(len(FEATURES), hidden=64, lead_days=lead).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-5)
    loss_fn = nn.MSELoss()
    train_ds = TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train))
    loader = DataLoader(train_ds, batch_size=32, shuffle=True)
    x_val_t = torch.from_numpy(x_val).to(device)
    y_val_t = torch.from_numpy(y_val).to(device)
    best_val, best_state, stale = float("inf"), None, 0
    history = []
    for epoch in range(args.epochs):
        model.train()
        losses = []
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad(set_to_none=True)
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        model.eval()
        with torch.no_grad():
            val_loss = float(loss_fn(model(x_val_t), y_val_t).cpu())
        history.append({"epoch": epoch + 1, "train_mse_scaled": float(np.mean(losses)), "validation_mse_scaled": val_loss})
        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
        if stale >= args.patience:
            break
    if best_state is None:
        raise SystemExit("Model training did not produce a finite validation score.")
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        pred_test_scaled = model(torch.from_numpy(x_test).to(device)).cpu().numpy()
    pred_test = pred_test_scaled * y_std + y_mean
    # Physical discharge cannot be negative; clip only at final output/evaluation.
    pred_test = np.maximum(pred_test, 0.0)
    actual_test = y_test_scaled
    test_metrics = metrics(actual_test.reshape(-1), pred_test.reshape(-1))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.output_dir / f"streamflow_lstm_{args.station_id}.pt"
    torch.save(model.state_dict(), model_path)
    report = {
        "model_type": "single-station research LSTM; not Google's production model",
        "station_id": str(args.station_id),
        "lookback_days": lookback,
        "lead_days": lead,
        "features": FEATURES,
        "target": TARGET,
        "rows_daily": len(full),
        "complete_windows": int(len(origins)),
        "train_windows": int(train_mask.sum()),
        "validation_windows": int(val_mask.sum()),
        "test_windows": int(test_mask.sum()),
        "chronological_split_dates": {
            "train_ends_before": str(dates[train_cut].date()),
            "validation_ends_before": str(dates[min(val_cut, len(dates)-1)].date()),
            "test_starts": str(dates[val_cut].date()),
        },
        "test_metrics": test_metrics,
        "training_history": history,
        "model_file": str(model_path),
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "warnings": [
            "Uses historical meteorology and observed discharge only; no future-weather forecast input is included.",
            "Requires independent event-period evaluation before use in public warnings.",
            "This pilot does not produce inundation maps or a calibrated probability of flooding.",
        ],
    }
    (args.output_dir / f"streamflow_lstm_{args.station_id}.report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    np.savez_compressed(
        args.output_dir / f"streamflow_lstm_{args.station_id}.scalers.npz",
        x_mean=x_mean, x_std=x_std, y_mean=np.array(y_mean), y_std=np.array(y_std),
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
