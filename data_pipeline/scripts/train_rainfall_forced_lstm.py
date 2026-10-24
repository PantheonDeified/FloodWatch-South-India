#!/usr/bin/env python3
"""Train an experimental discharge LSTM conditioned on rainfall over its forecast horizon.

The historical reanalysis rainfall used for backtesting is observed after each
forecast origin. Results are therefore a perfect-rainfall-forcing upper-bound
experiment, not a deployable weather forecast skill estimate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import random
import re

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


class RainfallForcedLSTM(nn.Module):
    def __init__(self, n_features: int, hidden: int, lead_days: int):
        super().__init__()
        self.lead_days = lead_days
        self.encoder = nn.LSTM(n_features, hidden, batch_first=True)
        self.head = nn.Sequential(
            nn.Linear(hidden + lead_days, hidden), nn.GELU(), nn.Dropout(.1),
            nn.Linear(hidden, hidden // 2), nn.GELU(), nn.Linear(hidden // 2, lead_days),
        )

    def forward(self, history, future_rain):
        sequence, _ = self.encoder(history)
        return self.head(torch.cat([sequence[:, -1, :], future_rain], dim=1))


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    error = predicted - actual
    denom = float(np.sum((actual - actual.mean()) ** 2))
    return {
        "mae_m3s": float(np.mean(np.abs(error))),
        "rmse_m3s": float(np.sqrt(np.mean(error ** 2))),
        "nse": float(1 - np.sum(error ** 2) / denom) if denom > 0 else None,
        "samples": int(actual.size),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", required=True, type=pathlib.Path,
                    help="Daily table from build_event_features.py with verified gauge weather and discharge.")
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
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(args.seed)

    frame = pd.read_csv(args.features, dtype={"station_id": str})
    if "station_id" not in frame or "date" not in frame:
        raise SystemExit("Feature file needs station_id and date columns.")
    frame = frame[frame["station_id"].astype(str).eq(str(args.station_id))].copy()
    missing = [c for c in [*FEATURES, "date"] if c not in frame.columns]
    if missing:
        raise SystemExit(f"Feature file misses columns {missing}; run build_event_features.py with weather and discharge observations.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    for column in FEATURES: frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame.empty: raise SystemExit("No feature rows for this station.")
    full = frame.set_index("date").asfreq("D")
    n_days = len(full)
    lookback, lead = args.lookback_days, args.lead_days
    if n_days < lookback + lead + 120:
        raise SystemExit("Not enough daily history; need lookback + lead + 120 calendar days.")

    x_values = full[FEATURES].to_numpy(dtype=np.float64)
    y_values = full[TARGET].to_numpy(dtype=np.float64)
    rain_values = pd.to_numeric(full["precipitation_sum"], errors="coerce").to_numpy(dtype=np.float64)
    rain_values[rain_values < 0] = np.nan
    tr, va = int(n_days * .70), int(n_days * .85)
    records = {"train": [], "validation": [], "test": []}
    for origin in range(lookback - 1, n_days - lead):
        start = origin - lookback + 1
        x = x_values[start:origin + 1]
        future_rain = rain_values[origin + 1:origin + lead + 1]
        target = y_values[origin + 1:origin + lead + 1]
        if not np.isfinite(x).all() or not np.isfinite(future_rain).all() or not np.isfinite(target).all():
            continue
        if np.any(target < 0): continue
        last = origin + lead
        split = "train" if last < tr else "validation" if origin >= tr and last < va else "test" if origin >= va else None
        if split:
            records[split].append((origin, x.astype(np.float32), np.log1p(future_rain).astype(np.float32), np.log1p(target).astype(np.float32), target.astype(np.float32), float(y_values[origin])))
    for split, minimum in (("train", 100), ("validation", 20), ("test", 20)):
        if len(records[split]) < minimum:
            raise SystemExit(f"Only {len(records[split])} complete {split} windows; need {minimum}. Missing rainfall or discharge days may be limiting coverage.")

    x_train_raw = np.concatenate([r[1] for r in records["train"]], axis=0)
    rain_train_raw = np.concatenate([r[2] for r in records["train"]], axis=0)
    y_train_raw = np.concatenate([r[3] for r in records["train"]], axis=0)
    x_mean = x_train_raw.mean(axis=0); x_std = x_train_raw.std(axis=0)
    x_std = np.where(x_std < 1e-6, 1.0, x_std)
    rain_mean = float(rain_train_raw.mean()); rain_std = float(rain_train_raw.std()) or 1.0
    y_mean = float(y_train_raw.mean()); y_std = float(y_train_raw.std())
    if y_std < 1e-6: raise SystemExit("Training discharge series has near-zero variation.")

    def pack(rows):
        x = np.stack([(r[1] - x_mean) / x_std for r in rows]).astype(np.float32)
        fr = np.stack([(r[2] - rain_mean) / rain_std for r in rows]).astype(np.float32)
        y = np.stack([(r[3] - y_mean) / y_std for r in rows]).astype(np.float32)
        actual = np.stack([r[4] for r in rows]).astype(np.float32)
        baseline = np.repeat(np.asarray([r[5] for r in rows], dtype=np.float32)[:, None], lead, axis=1)
        return x, fr, y, actual, baseline

    x_train, r_train, y_train, _, _ = pack(records["train"])
    x_val, r_val, y_val, actual_val, base_val = pack(records["validation"])
    x_test, r_test, y_test, actual_test, base_test = pack(records["test"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = RainfallForcedLSTM(len(FEATURES), 64, lead).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=7e-4, weight_decay=1e-4)
    loader = DataLoader(TensorDataset(torch.from_numpy(x_train), torch.from_numpy(r_train), torch.from_numpy(y_train)), batch_size=32, shuffle=True)
    xv, rv, yv = torch.from_numpy(x_val).to(device), torch.from_numpy(r_val).to(device), torch.from_numpy(y_val).to(device)
    best = float("inf"); best_state = None; stale = 0; history = []
    for epoch in range(args.epochs):
        model.train(); losses = []
        for xb, rb, yb in loader:
            xb, rb, yb = xb.to(device), rb.to(device), yb.to(device)
            optimizer.zero_grad(set_to_none=True); loss = ((model(xb, rb) - yb) ** 2).mean()
            loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step(); losses.append(float(loss.detach().cpu()))
        model.eval()
        with torch.no_grad(): val_loss = float(((model(xv, rv) - yv) ** 2).mean().cpu())
        history.append({"epoch": epoch + 1, "train_mse": float(np.mean(losses)), "validation_mse": val_loss})
        if val_loss < best:
            best = val_loss; best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}; stale = 0
        else: stale += 1
        if stale >= args.patience: break
    if best_state is None: raise SystemExit("Training did not produce a valid checkpoint.")
    model.load_state_dict(best_state); model.eval()
    with torch.no_grad(): pred_scaled = model(torch.from_numpy(x_test).to(device), torch.from_numpy(r_test).to(device)).cpu().numpy()
    predicted = np.expm1(np.maximum(pred_scaled * y_std + y_mean, 0.0))
    baseline = np.maximum(base_test, 0.0)
    report = {
        "model_type": "single-station rainfall-forced discharge LSTM (experimental research model)",
        "station_id": str(args.station_id), "features": FEATURES,
        "target": TARGET, "future_forcing": "daily precipitation_sum over each forecast lead day",
        "future_forcing_backtest_caveat": "Historical ERA5-Land rainfall occurs after each forecast origin and is used as perfect future forcing; this is an upper-bound experiment, not an operational forecast skill estimate.",
        "lookback_days": lookback, "lead_days": lead, "rows_daily": int(n_days),
        "windows": {k: len(v) for k, v in records.items()},
        "chronological_split_dates": {"train_end_before": str(full.index[tr].date()), "validation_end_before": str(full.index[va].date()), "test_start": str(full.index[va].date())},
        "test_metrics": metrics(actual_test.reshape(-1), predicted.reshape(-1)),
        "persistence_baseline_test_metrics": metrics(actual_test.reshape(-1), baseline.reshape(-1)),
        "rmse_skill_vs_persistence": float(1 - metrics(actual_test.reshape(-1), predicted.reshape(-1))["rmse_m3s"] / metrics(actual_test.reshape(-1), baseline.reshape(-1))["rmse_m3s"]) if metrics(actual_test.reshape(-1), baseline.reshape(-1))["rmse_m3s"] > 0 else None,
        "training_history": history,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "warnings": [
            "Future rainfall during historical backtesting is reanalysis observed after forecast origin; results are optimistic versus real forecast rainfall.",
            "Inference must supply a weather-model precipitation forecast for each lead day; missing forecast days are rejected.",
            "This model predicts discharge only and does not produce flood probabilities, river stage, water depth, inundation or public warnings.",
            "Review station provenance, units, holdout events and performance before considering integration.",
        ],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    safe_station_id = re.sub(r"[^A-Za-z0-9._-]+", "_", str(args.station_id)).strip("._-") or "station"
    prefix = f"rainfall_forced_lstm_{safe_station_id}"
    report["artifact_prefix"] = prefix
    torch.save(model.state_dict(), args.output_dir / f"{prefix}.pt")
    scalers = {
        "features": FEATURES, "lookback_days": lookback, "lead_days": lead,
        "x_mean": x_mean.tolist(), "x_std": x_std.tolist(),
        "rain_mean": rain_mean, "rain_std": rain_std, "y_mean": y_mean, "y_std": y_std,
    }
    (args.output_dir / f"{prefix}.scalers.json").write_text(json.dumps(scalers, indent=2), encoding="utf-8")
    (args.output_dir / f"{prefix}.report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "training_history"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
