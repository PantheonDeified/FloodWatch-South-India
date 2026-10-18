#!/usr/bin/env python3
"""Train a discharge-only LSTM pilot on verified CWC station history.

Target: daily maximum observed river discharge (m^3/s). This is research-only,
not an operational flood warning, inundation prediction, or flood probability.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import random

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


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


def metric_pack(actual: np.ndarray, predicted: np.ndarray) -> dict:
    a = actual.reshape(-1).astype(np.float64)
    p = predicted.reshape(-1).astype(np.float64)
    e = p - a
    denom = float(np.sum((a - a.mean()) ** 2))
    return {
        "mae_m3s": float(np.mean(np.abs(e))),
        "rmse_m3s": float(np.sqrt(np.mean(e ** 2))),
        "nse": float(1.0 - np.sum(e ** 2) / denom) if denom > 0 else None,
        "samples": int(a.size),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--observations", required=True, type=pathlib.Path)
    ap.add_argument("--station-id", required=True)
    ap.add_argument("--output-dir", required=True, type=pathlib.Path)
    ap.add_argument("--lookback-days", type=int, default=90)
    ap.add_argument("--lead-days", type=int, default=7)
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if args.lookback_days < 14 or args.lead_days < 1 or args.epochs < 1:
        raise SystemExit("Use lookback >=14 days, a positive forecast horizon, and positive epochs.")

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    # Read only the columns needed, then select the requested station.
    try:
        frame = pd.read_csv(
            args.observations,
            usecols=["station_id", "observed_at", "discharge_m3_s"],
            dtype={"station_id": str},
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Could not read normalized CWC observations: {exc}") from exc
    frame = frame[frame["station_id"].astype(str) == str(args.station_id)].copy()
    if frame.empty:
        raise SystemExit(
            f"No rows for station_id={args.station_id!r}. Check the exact station_id in "
            "the CWC station audit/normalized CSV."
        )
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], errors="coerce")
    frame["discharge_m3_s"] = pd.to_numeric(frame["discharge_m3_s"], errors="coerce")
    frame = frame.dropna(subset=["observed_at", "discharge_m3_s"])
    frame = frame[frame["discharge_m3_s"] >= 0]
    if frame.empty:
        raise SystemExit("Station has no valid non-negative discharge observations.")

    # Use the maximum source observation on each reported calendar day to retain
    # high-flow signals. This is explicitly a daily-maximum target, not a daily mean.
    frame["date"] = frame["observed_at"].dt.normalize()
    daily = frame.groupby("date")["discharge_m3_s"].max().sort_index()
    full_index = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    series = daily.reindex(full_index).astype("float64")
    series.index.name = "date"
    n_days = len(series)
    if n_days < args.lookback_days + args.lead_days + 120:
        raise SystemExit(f"Insufficient calendar span ({n_days} days) for an honest chronological split.")

    values = series.to_numpy(dtype=np.float32)
    origins, x_rows, y_rows = [], [], []
    lookback, lead = args.lookback_days, args.lead_days
    for origin in range(lookback - 1, n_days - lead):
        x = values[origin - lookback + 1:origin + 1]
        y = values[origin + 1:origin + lead + 1]
        # Missing days stay missing; never interpolate or turn them into zero.
        if np.isfinite(x).all() and np.isfinite(y).all():
            origins.append(origin)
            x_rows.append(x[:, None])
            y_rows.append(y)
    if len(origins) < 150:
        raise SystemExit(
            f"Only {len(origins)} complete windows. This station needs more contiguous daily data."
        )
    origins = np.asarray(origins)
    x_rows = np.asarray(x_rows, dtype=np.float32)
    y_rows = np.asarray(y_rows, dtype=np.float32)

    train_cut, val_cut = int(n_days * 0.70), int(n_days * 0.85)
    train_mask = origins + lead < train_cut
    val_mask = (origins >= train_cut) & (origins + lead < val_cut)
    test_mask = origins >= val_cut
    if train_mask.sum() < 80 or val_mask.sum() < 20 or test_mask.sum() < 20:
        raise SystemExit("Chronological split lacks enough complete windows; choose a better-covered station.")

    x_train, y_train = x_rows[train_mask], y_rows[train_mask]
    x_val, y_val = x_rows[val_mask], y_rows[val_mask]
    x_test, y_test = x_rows[test_mask], y_rows[test_mask]

    # Scale with training data only.
    x_mean = float(x_train.mean())
    x_std = float(x_train.std())
    y_mean = float(y_train.mean())
    y_std = float(y_train.std())
    if x_std < 1e-6 or y_std < 1e-6:
        raise SystemExit("Training series has near-zero variation; cannot fit a useful model.")
    x_train = (x_train - x_mean) / x_std
    x_val = (x_val - x_mean) / x_std
    x_test = (x_test - x_mean) / x_std
    y_train = (y_train - y_mean) / y_std
    y_val = (y_val - y_mean) / y_std

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = DischargeLSTM(hidden=64, horizon=lead).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-5)
    loss_fn = nn.MSELoss()
    loader = DataLoader(
        TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train)),
        batch_size=128,
        shuffle=True,
    )
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
            loss = loss_fn(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        model.eval()
        with torch.no_grad():
            val_loss = float(loss_fn(model(x_val_t), y_val_t).cpu())
        history.append({
            "epoch": epoch + 1,
            "train_mse_scaled": float(np.mean(losses)),
            "validation_mse_scaled": val_loss,
        })
        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
        if stale >= args.patience:
            break
    if best_state is None:
        raise SystemExit("Training failed to produce a valid checkpoint.")
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        pred_scaled = model(torch.from_numpy(x_test).to(device)).cpu().numpy()
    predicted = np.maximum(pred_scaled * y_std + y_mean, 0.0)

    # Persistence baseline repeats the latest known discharge for all lead days.
    persistence = np.repeat(x_rows[test_mask, -1, 0][:, None], lead, axis=1)
    persistence = np.maximum(persistence, 0.0)
    actual = y_test
    test_metrics = metric_pack(actual, predicted)
    persistence_metrics = metric_pack(actual, persistence)
    base_rmse = persistence_metrics["rmse_m3s"]
    skill = float(1.0 - test_metrics["rmse_m3s"] / base_rmse) if base_rmse > 0 else None

    # Explicit peak-period diagnostic: test targets at/above the 90th percentile
    # of the training target distribution. This is not a warning threshold.
    peak_threshold = float(np.quantile(y_train * y_std + y_mean, 0.90))
    actual_flat = actual.reshape(-1)
    pred_flat = predicted.reshape(-1)
    peak_mask = actual_flat >= peak_threshold
    peak_metrics = metric_pack(actual_flat[peak_mask], pred_flat[peak_mask]) if peak_mask.any() else None

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"discharge_lstm_{args.station_id.replace('|', '_').replace('/', '_')}"
    model_path = args.output_dir / f"{stem}.pt"
    scaler_path = args.output_dir / f"{stem}.scalers.npz"
    report_path = args.output_dir / f"{stem}.report.json"
    torch.save(model.state_dict(), model_path)
    np.savez_compressed(scaler_path, x_mean=np.array(x_mean), x_std=np.array(x_std),
                        y_mean=np.array(y_mean), y_std=np.array(y_std))
    report = {
        "model_type": "single-station univariate LSTM",
        "station_id": str(args.station_id),
        "target": "daily maximum observed river discharge (m3/s)",
        "input": "previous observed daily maximum discharge only; no weather inputs",
        "lookback_days": lookback,
        "lead_days": lead,
        "calendar_days": int(n_days),
        "first_date": str(series.index.min().date()),
        "last_date": str(series.index.max().date()),
        "source_observation_rows": int(len(frame)),
        "observed_days": int(daily.shape[0]),
        "missing_calendar_days": int(series.isna().sum()),
        "complete_windows": int(len(origins)),
        "train_windows": int(train_mask.sum()),
        "validation_windows": int(val_mask.sum()),
        "test_windows": int(test_mask.sum()),
        "chronological_split_dates": {
            "train_ends_before": str(series.index[train_cut].date()),
            "validation_ends_before": str(series.index[min(val_cut, n_days - 1)].date()),
            "test_starts": str(series.index[val_cut].date()),
        },
        "test_metrics": test_metrics,
        "persistence_baseline_test_metrics": persistence_metrics,
        "rmse_skill_vs_persistence": skill,
        "beats_persistence_baseline_on_rmse": bool(skill is not None and skill > 0),
        "peak_period_threshold_m3s": peak_threshold,
        "peak_period_test_metrics": peak_metrics,
        "training_history": history,
        "model_file": str(model_path),
        "scalers_file": str(scaler_path),
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "operational_status": "research_only_not_validated_for_public_warnings",
        "warnings": [
            "Uses past discharge only; no rainfall forecast or future-weather input.",
            "Daily maximum values preserve high-flow observations but are not daily mean discharge.",
            "Station source timestamps have unspecified timezone semantics; dates are preserved as reported.",
            "Evaluate independently across flood events and review source station metadata before any operational use.",
            "This model does not output flood probability, water depth, or inundation extent.",
        ],
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "training_history"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
