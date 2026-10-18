#!/usr/bin/env python3
"""Experimental regional discharge LSTM; no weather forcing or inundation model."""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, random
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
STATES = ["Andhra Pradesh", "Karnataka", "Kerala", "Tamil Nadu",
          "Telangana", "Puducherry", "Goa"]

class RegionalLSTM(nn.Module):
    def __init__(self, horizon):
        super().__init__()
        self.lstm = nn.LSTM(6, 96, num_layers=2, dropout=0.2, batch_first=True)
        self.head = nn.Sequential(nn.LayerNorm(96), nn.Linear(96, 96),
                                  nn.GELU(), nn.Dropout(0.15), nn.Linear(96, horizon))
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

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--observations", type=pathlib.Path, required=True)
    ap.add_argument("--output-dir", type=pathlib.Path, required=True)
    ap.add_argument("--lookback-days", type=int, default=90)
    ap.add_argument("--lead-days", type=int, default=7)
    ap.add_argument("--window-stride", type=int, default=7, help="Sample forecast origins every N days to control memory and reduce overlapping-window redundancy.")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--min-stations", type=int, default=5)
    ap.add_argument("--max-missing-fraction", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if args.lookback_days < 14 or args.lead_days < 1 or args.epochs < 1 or args.window_stride < 1:
        raise SystemExit("Require lookback >=14, lead >=1, epochs >=1 and window-stride >=1.")
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
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
    for sid,s in series_by_station.items():
        station_dates=pd.date_range(s.index.min(),s.index.max(),freq="D")
        offset=int((station_dates[0]-dates[0]).days)
        raw=s.reindex(station_dates).to_numpy(float)
        log=np.full(len(station_dates),np.nan); ok=np.isfinite(raw); log[ok]=np.log1p(raw[ok])
        lat,lon=map(float,meta.loc[sid].tolist())
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
            data[split].append((x,y,np.expm1(target).astype("float32"),
                                np.repeat(last,args.lead_days).astype("float32"),sid))
            used.add(sid)
    if len(used)<args.min_stations: raise SystemExit(f"Only {len(used)} stations have usable windows; need {args.min_stations}.")
    for split,minimum in [("train",200),("validation",40),("test",40)]:
        if len(data[split])<minimum: raise SystemExit(f"Only {len(data[split])} {split} windows; need {minimum}.")
    def pack(rows):
        return (np.stack([r[0] for r in rows]),np.stack([r[1] for r in rows]),
                np.stack([r[2] for r in rows]),np.stack([r[3] for r in rows]))
    xt,yt,_,_=pack(data["train"]); xv,yv,_,_=pack(data["validation"])
    xs,ys,actual,base=pack(data["test"])
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model=RegionalLSTM(args.lead_days).to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=7e-4,weight_decay=1e-4)
    sched=torch.optim.lr_scheduler.ReduceLROnPlateau(opt,patience=3,factor=.5)
    loader=DataLoader(TensorDataset(torch.from_numpy(xt),torch.from_numpy(yt)),batch_size=256,shuffle=True)
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
    with torch.no_grad(): pred=model(torch.from_numpy(xs).to(device)).cpu().numpy()
    pred=np.expm1(np.maximum(pred*sd+mu,0))
    m,b=metrics(actual,pred),metrics(actual,base)
    skill=1-m["rmse_m3s"]/b["rmse_m3s"] if b["rmse_m3s"]>0 else None
    per_horizon=[{"lead_day":h+1,"model":metrics(actual[:,h],pred[:,h]),
                  "persistence":metrics(actual[:,h],base[:,h])} for h in range(args.lead_days)]
    args.output_dir.mkdir(parents=True,exist_ok=True)
    model_path=args.output_dir/"regional_discharge_lstm.pt"
    report_path=args.output_dir/"regional_discharge_lstm.report.json"
    torch.save(model.state_dict(),model_path)
    report={"model_type":"regional multi-station masked-input LSTM","status":"experimental_research_only",
      "states":STATES,"source_station_count":int(df.station_id.nunique()),"stations_with_windows":len(used),
      "calendar_start":str(dates.min().date()),"calendar_end":str(dates.max().date()),
      "lookback_days":args.lookback_days,"lead_days":args.lead_days,"window_stride_days":args.window_stride,
      "input_features":["scaled log1p discharge","observation mask","day-of-year sin/cos","latitude","longitude"],
      "windows":{k:len(v) for k,v in data.items()},
      "split":{"train_before":str(dates[tr].date()),"validation_before":str(dates[va].date()),"test_from":str(dates[va].date())},
      "test_metrics":m,"persistence_baseline_test_metrics":b,"rmse_skill_vs_persistence":skill,
      "beats_persistence_baseline_on_rmse":bool(skill is not None and skill>0),"per_horizon_metrics":per_horizon,
      "training_history":history,"model_file":str(model_path),"created_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
      "weather_forecast_inputs_available":False,"operational_status":"not_validated_for_public_warnings",
      "limitations":["No rainfall/weather forecast forcing or static basin descriptors.",
      "No flood probability, water depth, or inundation extent.","Compare station-wise and flood-event metrics before any operational use."]}
    report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="training_history"},indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
