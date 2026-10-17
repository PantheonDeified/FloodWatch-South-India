#!/usr/bin/env python3
"""Build lagged rainfall/river-response features from normalized source tables.

The resulting table connects rainfall windows to observed water-level/discharge
changes. It is an analysis dataset, not automatically a flood label or warning.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weather", required=True, type=pathlib.Path,
                    help="Output of fetch_historical_weather.py.")
    ap.add_argument("--observations", required=True, type=pathlib.Path,
                    help="Output of normalize_cwc_levels.py, or equivalent normalized observations.")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    weather = pd.read_csv(args.weather, dtype={"station_id": str})
    obs = pd.read_csv(args.observations, dtype={"station_id": str})
    if not {"station_id", "date", "precipitation_sum"}.issubset(weather.columns):
        raise SystemExit("Weather file needs station_id, date, precipitation_sum.")
    if not {"station_id", "observed_at", "kind", "value"}.issubset(obs.columns):
        raise SystemExit("Observations file must use normalized columns station_id, observed_at, kind, value.")

    weather["date"] = pd.to_datetime(weather["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    weather["precipitation_sum"] = pd.to_numeric(weather["precipitation_sum"], errors="coerce")
    weather["temperature_2m_mean"] = pd.to_numeric(weather.get("temperature_2m_mean"), errors="coerce")
    weather = weather.dropna(subset=["station_id", "date"]).sort_values(["station_id", "date"])
    obs["value"] = pd.to_numeric(obs["value"], errors="coerce")
    # Preserve the source-reported date. The timestamp timezone may be unknown; do not silently shift dates.
    obs["date"] = obs["observed_at"].astype(str).str.slice(0, 10)
    obs = obs.dropna(subset=["station_id", "date", "value"])
    obs = obs[obs["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]

    records = []
    for station_id, group in weather.groupby("station_id", sort=False):
        group = group.copy().sort_values("date").drop_duplicates("date", keep="last")
        group["precipitation_1d_mm"] = group["precipitation_sum"]
        # Do not fill missing days; a rolling total is available only for a complete window.
        for window in (3, 7, 14, 30):
            group[f"rain_sum_{window}d_mm"] = group["precipitation_sum"].rolling(window, min_periods=window).sum()
        group["rain_7d_change_vs_previous_7d_mm"] = (
            group["rain_sum_7d_mm"] - group["rain_sum_7d_mm"].shift(7)
        )
        records.append(group)
    features = pd.concat(records, ignore_index=True) if records else pd.DataFrame()

    observed_daily = []
    for (station_id, kind), group in obs.groupby(["station_id", "kind"], sort=False):
        group = group.copy().sort_values("observed_at")
        group["_date"] = group["date"]
        # Preserve level values as levels and discharge values as flow. Never convert between them.
        daily = group.groupby("_date", as_index=False).agg(
            observed_value_last=("value", "last"),
            observed_value_max=("value", "max"),
            observed_value_min=("value", "min"),
            observation_count=("value", "count"),
            source_url=("source_url", "last") if "source_url" in group.columns else ("value", "size"),
            unit=("unit", "last") if "unit" in group.columns else ("kind", "first"),
        )
        daily = daily.rename(columns={"_date": "date"})
        daily["station_id"] = str(station_id)
        daily["kind"] = kind
        daily["observed_daily_change"] = daily["observed_value_last"].diff()
        daily["observed_daily_pct_change"] = daily["observed_value_last"].pct_change() * 100
        daily["observed_3d_change"] = daily["observed_value_last"].diff(3)
        daily["observed_7d_change"] = daily["observed_value_last"].diff(7)
        # Rolling range is a useful rising-water signal, but does not by itself label flooding.
        daily["observed_7d_max"] = daily["observed_value_max"].rolling(7, min_periods=7).max()
        observed_daily.append(daily)
    river = pd.concat(observed_daily, ignore_index=True) if observed_daily else pd.DataFrame()

    if not features.empty and not river.empty:
        result = features.merge(river, on=["station_id", "date"], how="left", suffixes=("", "_observed"))
    else:
        result = features.copy()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.out, index=False)
    metadata = {
        "output": str(args.out),
        "weather_rows": int(len(weather)),
        "observation_rows": int(len(obs)),
        "feature_rows": int(len(result)),
        "stations_weather": int(weather["station_id"].nunique()),
        "stations_observations": int(obs["station_id"].nunique()),
        "observation_kinds": sorted(obs["kind"].dropna().astype(str).unique().tolist()),
        "missingness_policy": "No missing observations are zero-filled; rolling rainfall totals require complete windows.",
        "interpretation": "Associations/lagged signals are not proof of causality or flood probability. Verified event labels and independent evaluation are required.",
    }
    args.out.with_suffix(args.out.suffix + ".manifest.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
