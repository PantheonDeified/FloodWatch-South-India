#!/usr/bin/env python3
"""Experimental regional discharge LSTM; no weather forcing or inundation model."""
from __future__ import annotations
import argparse, datetime as dt, json, os, pathlib, random, time
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
STATES = ["Andhra Pradesh", "Karnataka", "Kerala", "Tamil Nadu", "Telangana"]

class RegionalLSTM(nn.Module):
    def __init__(self, horizon, hidden_size=48, num_layers=1):
        super().__init__()
        if horizon < 1 or hidden_size < 8 or num_layers < 1:
            raise ValueError("horizon must be positive; hidden_size >= 8; num_layers >= 1")
        self.lstm = nn.LSTM(
            6, hidden_size, num_layers=num_layers,
            dropout=0.1 if num_layers > 1 else 0.0, batch_first=True
        )
        self.head = nn.Sequential(
            nn.LayerNorm(hidden_size), nn.Linear(hidden_size, hidden_size),
            nn.GELU(), nn.Dropout(0.1), nn.Linear(hidden_size, horizon)
        )
    def forward(self, x):
        seq, _ = self.lstm(x)
        return self.head(seq[:, -1])

def metrics(a, p):
    a, p = np.asarray(a, float).ravel(), np.asarray(p, float).ravel()
    err = p - a
    denom = float(((a - a.mean()) ** 2).sum())
    return {"mae_m3s": float(np.abs(err).mean()),
            "rmse_m3s": float(np.sqrt((err ** 2).mean())),
            "nse": float(1 - (err ** 2).sum() / denom) if denom else None,
            "samples": int(a.size)}

def choose_alpha_on_validation(actual, model_prediction, baseline_prediction):
    """Choose neural-network blend weight on chronological validation data only."""
    actual = np.asarray(actual, dtype=float)
    model_prediction = np.asarray(model_prediction, dtype=float)
    baseline_prediction = np.asarray(baseline_prediction, dtype=float)
    if actual.shape != model_prediction.shape or actual.shape != baseline_prediction.shape:
        raise ValueError("Validation arrays must have matching shapes.")
    if actual.size == 0 or not (np.isfinite(actual).all() and np.isfinite(model_prediction).all() and np.isfinite(baseline_prediction).all()):
        raise ValueError("Validation arrays must be non-empty and finite.")
    best_alpha = 0.0
    best_rmse = metrics(actual, baseline_prediction)["rmse_m3s"]
    for alpha in np.linspace(0.0, 1.0, 21):
        blended = np.maximum((1.0-alpha)*baseline_prediction + alpha*model_prediction, 0.0)
        candidate_rmse = metrics(actual, blended)["rmse_m3s"]
        if candidate_rmse < best_rmse - 1e-9:
            best_alpha, best_rmse = float(alpha), float(candidate_rmse)
    return best_alpha, float(best_rmse)

def sample_station_windows(rows, max_windows, peak_threshold=None):
    """Bound per-station window memory while preserving timeline coverage and some training peaks.

    For validation/test, sampling is uniform in chronological candidate order. For training,
    up to one third of the cap is reserved for evenly spread windows whose target horizon
    includes a station-specific high-flow value derived from the training period only.
    """
    if len(rows) <= max_windows:
        return rows
    selected = set()
    if peak_threshold is not None and np.isfinite(peak_threshold):
        peak_indices = [i for i, row in enumerate(rows)
                        if np.nanmax(np.asarray(row[2], dtype=float)) >= peak_threshold]
        peak_budget = max_windows // 3
        if peak_indices and peak_budget:
            chosen_positions = np.linspace(
                0, len(peak_indices) - 1,
                num=min(peak_budget, len(peak_indices)), dtype=int
            )
            selected.update(peak_indices[int(pos)] for pos in chosen_positions)
    remaining = [i for i in range(len(rows)) if i not in selected]
    slots = max_windows - len(selected)
    if slots > 0 and remaining:
        positions = np.linspace(0, len(remaining) - 1,
                                num=min(slots, len(remaining)), dtype=int)
        selected.update(remaining[int(pos)] for pos in positions)
    return [rows[i] for i in sorted(selected)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--observations", type=pathlib.Path, required=True)
    ap.add_argument("--output-dir", type=pathlib.Path, required=True)
    ap.add_argument("--lookback-days", type=int, default=90)
    ap.add_argument("--lead-days", type=int, default=7)
    ap.add_argument("--window-stride", type=int, default=7, help="Sample forecast origins every N days to control memory and reduce overlapping-window redundancy.")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--hidden-size", type=int, default=48)
    ap.add_argument("--num-layers", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=512)
    ap.add_argument("--patience", type=int, default=5)
    ap.add_argument("--min-stations", type=int, default=5)
    ap.add_argument("--max-missing-fraction", type=float, default=0.2)
    ap.add_argument("--max-windows-per-station-split", type=int, default=180,
                    help="Upper bound on retained windows per station per split to control RAM; train sampling preserves some high-flow horizons.")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if (args.lookback_days < 14 or args.lead_days < 1 or args.epochs < 1
            or args.window_stride < 1 or args.patience < 1
            or args.max_windows_per_station_split < 40 or args.hidden_size < 8
            or args.num_layers < 1 or args.batch_size < 1):
        raise SystemExit("Require lookback >=14, lead >=1, positive epochs/stride/patience/batch/layers, hidden-size >=8 and max-windows-per-station-split >=40.")
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    # Explicit CPU thread caps avoid the severe oversubscription often seen on CI runners.
    torch.set_num_threads(max(1, int(os.environ.get("OMP_NUM_THREADS", "2"))))
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    started_at = time.monotonic()
    cols = ["station_id","state","latitude","longitude","observed_at","discharge_m3_s"]
    try:
        df = pd.read_csv(args.observations, usecols=cols, dtype={"station_id":str,"state":str})
    except (OSError, ValueError) as e:
        raise SystemExit(f"Cannot read normalized observations: {e}") from e
    df = df[df.state.str.casefold().isin({s.casefold() for s in STATES})].copy()
    df["observed_at"] = pd.to_datetime(df.observed_at, errors="coerce")
    df["discharge_m3_s"] = pd.to_numeric(df.discharge_m3_s, errors="coerce")
    df["latitude"] = pd.to_numeric(df.latitude, errors="coerce").fillna(0).clip(-90,90)/90
    df["longitude"] = pd.to_numeric(df.longitude, errors="coerce").fillna(0).clip(-180,180)/180
    df = df.dropna(subset=["station_id","observed_at","discharge_m3_s"])
    df = df[df.discharge_m3_s >= 0]
    if df.empty: raise SystemExit("No valid observations for South-India states.")
    df["date"] = df.observed_at.dt.normalize()
    meta = df.groupby("station_id")[["latitude","longitude"]].median()
    series_by_station = {sid:g.groupby("date").discharge_m3_s.max().sort_index()
                         for sid,g in df.groupby("station_id")}
    start = min(s.index.min() for s in series_by_station.values())
    end = max(s.index.max() for s in series_by_station.values())
    dates = pd.date_range(start,end,freq="D"); n = len(dates)
    if n < args.lookback_days + args.lead_days + 120:
        raise SystemExit(f"Only {n} calendar days; insufficient time span.")
    tr, va = int(n*.70), int(n*.85)
    fit_log = []
    for s in series_by_station.values():
        z = s[s.index < dates[tr]].to_numpy(float)
        if len(z): fit_log.extend(np.log1p(z).tolist())
    if len(fit_log) < 100: raise SystemExit("Too few training-period observations.")
    mu, sd = float(np.mean(fit_log)), float(np.std(fit_log))
    if sd < 1e-6: raise SystemExit("Near-constant training discharge.")
    data = {"train":[],"validation":[],"test":[]}; used=set()
    candidate_counts = {"train":0,"validation":0,"test":0}
    station_peak_thresholds = {}
    for sid,s in series_by_station.items():
        station_dates=pd.date_range(s.index.min(),s.index.max(),freq="D")
        offset=int((station_dates[0]-dates[0]).days)
        raw=s.reindex(station_dates).to_numpy(float)
        log=np.full(len(station_dates),np.nan); ok=np.isfinite(raw); log[ok]=np.log1p(raw[ok])
        # latitude/longitude are already normalized to [-1, 1] in the input-preparation
        # block above. Do not divide them a second time here; inference uses the same scale.
        lat,lon=map(float,meta.loc[sid].tolist())
        # The station-specific high-flow threshold is derived from this station's
        # training-period observations only; never use validation/test targets to select train peaks.
        train_count=max(0,min(len(raw),tr-offset))
        train_values=raw[:train_count]
        train_values=train_values[np.isfinite(train_values)]
        station_peak_thresholds[sid]=float(np.quantile(train_values,0.9)) if len(train_values)>=10 else None
        station_rows = {"train":[],"validation":[],"test":[]}
        for local_end in range(args.lookback_days-1,len(station_dates)-args.lead_days,args.window_stride):
            global_end=offset+local_end
            a=local_end-args.lookback_days+1; hist=log[a:local_end+1]; mask=np.isfinite(hist)
            if mask.mean() < 1-args.max_missing_fraction: continue
            target=log[local_end+1:local_end+args.lead_days+1]
            if not np.isfinite(target).all(): continue
            last_target=global_end+args.lead_days
            if last_target < tr: split="train"
            elif global_end >= tr and last_target < va: split="validation"
            elif global_end >= va: split="test"
            else: continue
            scaled=(hist-mu)/sd; scaled[~mask]=0
            doy=station_dates[a:local_end+1].dayofyear.to_numpy(float); ang=2*np.pi*doy/365.25
            x=np.column_stack([scaled,mask.astype(float),np.sin(ang),np.cos(ang),
                               np.full(len(hist),lat),np.full(len(hist),lon)]).astype("float32")
            y=((target-mu)/sd).astype("float32")
            last=float(raw[a:local_end+1][mask][-1])
            station_rows[split].append((x,y,np.expm1(target).astype("float32"),
                                        np.repeat(last,args.lead_days).astype("float32"),sid))
        if any(station_rows.values()):
            used.add(sid)
        for split, rows in station_rows.items():
            candidate_counts[split] += len(rows)
            if not rows:
                continue
            threshold = station_peak_thresholds.get(sid) if split == "train" else None
            data[split].extend(sample_station_windows(rows, args.max_windows_per_station_split, threshold))
    if len(used)<args.min_stations: raise SystemExit(f"Only {len(used)} stations have usable windows; need {args.min_stations}.")
    for split,minimum in [("train",200),("validation",40),("test",40)]:
        if len(data[split])<minimum: raise SystemExit(f"Only {len(data[split])} {split} windows; need {minimum}.")
    def pack(rows):
        return (np.stack([r[0] for r in rows]),np.stack([r[1] for r in rows]),
                np.stack([r[2] for r in rows]),np.stack([r[3] for r in rows]))
    xt,yt,_,_=pack(data["train"])
    xv,yv,validation_actual,validation_base=pack(data["validation"])
    xs,ys,actual,base=pack(data["test"])
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model=RegionalLSTM(args.lead_days, hidden_size=args.hidden_size, num_layers=args.num_layers).to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=7e-4,weight_decay=1e-4)
    sched=torch.optim.lr_scheduler.ReduceLROnPlateau(opt,patience=3,factor=.5)
    loader=DataLoader(TensorDataset(torch.from_numpy(xt),torch.from_numpy(yt)),batch_size=args.batch_size,shuffle=True)
    xv_t,yv_t=torch.from_numpy(xv).to(device),torch.from_numpy(yv).to(device)
    best=float("inf"); state=None; stale=0; history=[]
    peak=float(np.quantile(yt*sd+mu,.9))
    for epoch in range(args.epochs):
        model.train(); losses=[]
        for xb,yb in loader:
            xb,yb=xb.to(device),yb.to(device); opt.zero_grad(set_to_none=True)
            pred=model(xb); weights=1+1.5*((yb*sd+mu)>=peak).float()
            loss=(weights*(pred-yb)**2).mean(); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(),1.0); opt.step()
            losses.append(float(loss.detach().cpu()))
        model.eval()
        with torch.no_grad(): vl=float(((model(xv_t)-yv_t)**2).mean().cpu())
        sched.step(vl); history.append({"epoch":epoch+1,"train_weighted_mse":float(np.mean(losses)),"validation_mse":vl})
        if vl<best:
            best=vl; state={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}; stale=0
        else: stale+=1
        if stale>=args.patience: break
    if state is None: raise SystemExit("No valid model checkpoint.")
    model.load_state_dict(state); model.eval()
    # Choose the LSTM contribution using validation data only; never tune against test results.
    with torch.no_grad():
        validation_scaled=model(torch.from_numpy(xv).to(device)).cpu().numpy()
    validation_prediction=np.expm1(np.maximum(validation_scaled*sd+mu,0))
    alpha,validation_blend_rmse=choose_alpha_on_validation(validation_actual,validation_prediction,validation_base)
    validation_selected=np.maximum((1.0-alpha)*validation_base+alpha*validation_prediction,0.0)
    validation_selection={
        "method":"minimize chronological validation RMSE over alpha 0.00..1.00 in 0.05 steps; persistence wins ties",
        "alpha":alpha,
        "persistence_metrics":metrics(validation_actual,validation_base),
        "raw_lstm_metrics":metrics(validation_actual,validation_prediction),
        "selected_metrics":metrics(validation_actual,validation_selected),
        "selected_rmse_m3s":validation_blend_rmse,
        "test_set_used_for_selection":False
    }
    with torch.no_grad(): pred=model(torch.from_numpy(xs).to(device)).cpu().numpy()
    pred=np.expm1(np.maximum(pred*sd+mu,0))
    selected_pred=np.maximum((1.0-alpha)*base+alpha*pred,0.0)
    raw_lstm_metrics=metrics(actual,pred)
    m,b=metrics(actual,selected_pred),metrics(actual,base)
    raw_skill=1-raw_lstm_metrics["rmse_m3s"]/b["rmse_m3s"] if b["rmse_m3s"]>0 else None
    skill=1-m["rmse_m3s"]/b["rmse_m3s"] if b["rmse_m3s"]>0 else None
    selected_model_type=("persistence_selected_by_validation" if alpha<=1e-12 else
                         "lstm_persistence_blend" if alpha<1.0-1e-12 else "raw_lstm")
    per_horizon=[{"lead_day":h+1,"selected_model":metrics(actual[:,h],selected_pred[:,h]),
                  "raw_lstm":metrics(actual[:,h],pred[:,h]),
                  "persistence":metrics(actual[:,h],base[:,h])} for h in range(args.lead_days)]

    # A pooled score can hide stations where the LSTM fails. Report every held-out
    # station separately, and assess station-relative high flows using thresholds
    # fitted only to that station's training-period observations (not official alerts).
    test_station_ids = np.asarray([row[4] for row in data["test"]], dtype=str)
    per_station_metrics = {}
    station_high_flow_skill = []
    for sid in sorted(set(test_station_ids.tolist())):
        mask_station = test_station_ids == sid
        station_actual = actual[mask_station]
        station_pred = selected_pred[mask_station]
        station_raw_pred = pred[mask_station]
        station_base = base[mask_station]
        station_model_metrics = metrics(station_actual, station_pred)
        station_raw_metrics = metrics(station_actual, station_raw_pred)
        station_baseline_metrics = metrics(station_actual, station_base)
        station_baseline_rmse = station_baseline_metrics["rmse_m3s"]
        station_model_rmse = station_model_metrics["rmse_m3s"]
        station_skill = (
            float(1 - station_model_rmse / station_baseline_rmse)
            if station_baseline_rmse is not None and station_baseline_rmse > 0 else None
        )
        threshold = station_peak_thresholds.get(sid)
        high_flow_report = None
        high_flow_count = 0
        high_flow_skill = None
        if threshold is not None and np.isfinite(threshold):
            high_mask = station_actual >= threshold
            high_flow_count = int(high_mask.sum())
            if high_flow_count:
                high_actual = station_actual[high_mask]
                high_pred = station_pred[high_mask]
                high_raw_pred = station_raw_pred[high_mask]
                high_base = station_base[high_mask]
                high_model_metrics = metrics(high_actual, high_pred)
                high_raw_metrics = metrics(high_actual, high_raw_pred)
                high_baseline_metrics = metrics(high_actual, high_base)
                baseline_high_rmse = high_baseline_metrics["rmse_m3s"]
                model_high_rmse = high_model_metrics["rmse_m3s"]
                if baseline_high_rmse is not None and baseline_high_rmse > 0:
                    high_flow_skill = float(1 - model_high_rmse / baseline_high_rmse)
                    station_high_flow_skill.append(high_flow_skill)
                high_flow_report = {
                    "selected_model": high_model_metrics,
                    "raw_lstm": high_raw_metrics,
                    "persistence": high_baseline_metrics,
                    "rmse_skill_vs_persistence": high_flow_skill,
                }
        per_station_metrics[sid] = {
            "test_metrics": station_model_metrics,
            "raw_lstm_test_metrics": station_raw_metrics,
            "persistence_baseline_test_metrics": station_baseline_metrics,
            "rmse_skill_vs_persistence": station_skill,
            "training_period_90th_percentile_discharge_m3s": threshold,
            "high_flow_target_points": high_flow_count,
            "high_flow_test_metrics": high_flow_report,
        }
    station_skills = [
        value["rmse_skill_vs_persistence"] for value in per_station_metrics.values()
        if value["rmse_skill_vs_persistence"] is not None
    ]
    per_station_summary = {
        "stations_evaluated": len(per_station_metrics),
        "stations_beating_persistence_on_rmse": sum(value > 0 for value in station_skills),
        "stations_with_comparable_baseline": len(station_skills),
        "high_flow_stations_with_comparable_baseline": len(station_high_flow_skill),
        "high_flow_stations_beating_persistence_on_rmse": sum(value > 0 for value in station_high_flow_skill),
        "note": "High-flow means the station's training-period 90th-percentile discharge, not an official flood-warning threshold.",
    }

    args.output_dir.mkdir(parents=True,exist_ok=True)
    model_path=args.output_dir/"regional_discharge_lstm.pt"
    scaler_path=args.output_dir/"regional_discharge_lstm.scalers.json"
    report_path=args.output_dir/"regional_discharge_lstm.report.json"
    torch.save(model.state_dict(),model_path)
    scaler_path.write_text(json.dumps({
      "version":2,"target_transform":"log1p","global_log1p_mean":mu,"global_log1p_std":sd,
      "validation_blend_alpha":alpha,"validation_blend_selection":validation_selection,
      "lookback_days":args.lookback_days,"lead_days":args.lead_days,
      "input_features":["scaled_log1p_discharge","observation_mask","day_of_year_sin","day_of_year_cos","latitude_div_90","longitude_div_180"],
      "latitude_scaling":"latitude_degrees / 90; normalized to [-1,1]","longitude_scaling":"longitude_degrees / 180; normalized to [-1,1]"
    },indent=2),encoding="utf-8")
    report={"model_type":"regional multi-station masked-input LSTM with validation-selected blend","selected_model_type":selected_model_type,"status":"experimental_research_only",
      "states":STATES,"source_station_count":int(df.station_id.nunique()),"stations_with_windows":len(used),
      "calendar_start":str(dates.min().date()),"calendar_end":str(dates.max().date()),
      "lookback_days":args.lookback_days,"lead_days":args.lead_days,"window_stride_days":args.window_stride,
      "architecture":{"hidden_size":args.hidden_size,"num_layers":args.num_layers,"batch_size":args.batch_size,"epochs_requested":args.epochs,"early_stopping_patience":args.patience,"torch_threads":torch.get_num_threads()},
      "input_features":["scaled log1p discharge","observation mask","day-of-year sin/cos","latitude","longitude"],
      "windows":{k:len(v) for k,v in data.items()},
      "candidate_windows_before_sampling":candidate_counts,
      "max_windows_per_station_split":args.max_windows_per_station_split,
      "window_sampling":{"validation_test":"uniformly spread across available chronological candidates per station; no target-based selection",
        "training":"uniform time coverage plus up to one-third of each station's cap from high-flow target horizons; station threshold is the 90th percentile of training-period observed discharge"},
      "split":{"train_before":str(dates[tr].date()),"validation_before":str(dates[va].date()),"test_from":str(dates[va].date())},
      "test_metrics":m,"raw_lstm_test_metrics":raw_lstm_metrics,"persistence_baseline_test_metrics":b,
      "validation_blend_alpha":alpha,"validation_blend_selection":validation_selection,
      "raw_lstm_rmse_skill_vs_persistence":raw_skill,"rmse_skill_vs_persistence":skill,
      "beats_persistence_baseline_on_rmse":bool(skill is not None and skill>0),
      "selected_model_type":selected_model_type,
      "per_station_summary":per_station_summary,
      "per_station_metrics":per_station_metrics,
      "per_horizon_metrics":per_horizon,
      "training_history":history,"model_file":str(model_path),"scaler_file":str(scaler_path),
      "training_duration_seconds":round(time.monotonic()-started_at,2),"created_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
      "weather_forecast_inputs_available":False,"operational_status":"not_validated_for_public_warnings",
      "limitations":["No rainfall/weather forecast forcing or static basin descriptors.",
      "Window counts are bounded per station/split for CPU/RAM; validation/test windows are evenly time-sampled rather than exhaustive.",
      "High-flow training sampling and high-flow evaluation use each station's training-period 90th percentile, not an official flood danger threshold.",
      "Some stations may have too few held-out high-flow targets for a stable metric; inspect counts before comparing stations.",
      "No flood probability, water depth, or inundation extent.","This research run does not by itself justify public warnings; review per-station and high-flow metrics first."]}
    report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="training_history"},indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
