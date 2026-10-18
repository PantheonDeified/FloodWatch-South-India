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

KIND_PREFIX = {
    "river_level": ("river_level", "m"),
    "reservoir_level": ("reservoir_level", "m"),
    "discharge": ("river_discharge", "m3s"),
    "river_discharge": ("river_discharge", "m3s"),
    "reservoir_discharge": ("reservoir_discharge", "m3s"),
    "storage": ("reservoir_storage", "million_m3"),
    "reservoir_storage": ("reservoir_storage", "million_m3"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weather", required=True, type=pathlib.Path,
                    help="Output of fetch_historical_weather.py.")
    ap.add_argument("--observations", required=True, type=pathlib.Path,
                    help="Output of normalize_cwc_levels.py or the normalized observation table.")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    weather = pd.read_csv(args.weather, dtype={"station_id": str})
    obs = pd.read_csv(args.observations, dtype={"station_id": str})
    if not {"station_id", "date", "precipitation_sum"}.issubset(weather.columns):
        raise SystemExit("Weather file needs station_id, date, precipitation_sum.")
    if not {"station_id", "observed_at", "kind", "value", "unit", "source_url", "source_timezone"}.issubset(obs.columns):
        raise SystemExit("Observations must include station_id, observed_at, kind, value, normalized unit, source_url, and source_timezone.")

    weather["date"] = pd.to_datetime(weather["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    numeric_weather = [
        "precipitation_sum", "temperature_2m_mean", "temperature_2m_max",
        "temperature_2m_min", "wind_speed_10m_max",
    ]
    for col in numeric_weather:
        if col not in weather.columns:
            weather[col] = float("nan")
        weather[col] = pd.to_numeric(weather[col], errors="coerce")
    weather = weather.dropna(subset=["station_id", "date"]).sort_values(["station_id", "date"])
    obs["value"] = pd.to_numeric(obs["value"], errors="coerce")
    if obs["source_url"].fillna("").astype(str).str.strip().eq("").any():
        raise SystemExit("Every observation must retain a source_url; restore provenance before feature building.")
    obs["source_timezone"] = obs["source_timezone"].fillna("unspecified").astype(str).str.strip()
    obs["unit"] = obs["unit"].astype(str).str.strip().str.casefold()
    expected_units = {
        "river_level": {"m"}, "reservoir_level": {"m"},
        "discharge": {"m3/s", "m³/s"}, "river_discharge": {"m3/s", "m³/s"},
        "reservoir_discharge": {"m3/s", "m³/s"},
        "storage": {"million_m3"}, "reservoir_storage": {"million_m3"},
    }
    supported = obs["kind"].astype(str).isin(KIND_PREFIX)
    bad_units = []
    for kind, allowed in expected_units.items():
        bad = obs[(obs["kind"].astype(str) == kind) & ~obs["unit"].isin(allowed)]
        if not bad.empty:
            bad_units.append({"kind": kind, "units": sorted(bad["unit"].dropna().unique().tolist()), "rows": int(len(bad))})
    if bad_units:
        raise SystemExit(
            "Unsupported or unnormalized units found; convert them using normalize_cwc_levels.py "
            f"and verify source metadata before feature building: {bad_units}"
        )
    obs = obs[supported].copy()
    # Preserve the timestamp's reported calendar date. The source timezone is not silently assumed.
    obs["date"] = obs["observed_at"].astype(str).str.slice(0, 10)
    obs = obs.dropna(subset=["station_id", "date", "value"])
    obs = obs[obs["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]

    weather_rows = []
    for station_id, original in weather.groupby("station_id", sort=False):
        original = original.drop_duplicates("date", keep="last").copy()
        original["date_dt"] = pd.to_datetime(original["date"], errors="coerce")
        original = original.dropna(subset=["date_dt"]).set_index("date_dt").sort_index()
        if original.empty:
            continue
        # Insert missing calendar days as NaN, so a 7-day sum can never silently span 9 days.
        full_index = pd.date_range(original.index.min(), original.index.max(), freq="D")
        group = original.reindex(full_index)
        group.index.name = "date_dt"
        group["station_id"] = str(station_id)
        group["date"] = group.index.strftime("%Y-%m-%d")
        for col in ["station_name", "river", "basin", "state", "latitude", "longitude",
                    "dataset", "model", "coordinate_source_url"]:
            if col in group.columns and col in original.columns:
                group[col] = group[col].fillna(original[col].dropna().iloc[0] if original[col].notna().any() else "")
        group["precipitation_1d_mm"] = group["precipitation_sum"]
        for window in (3, 7, 14, 30):
            group[f"rain_sum_{window}d_mm"] = group["precipitation_sum"].rolling(
                window, min_periods=window
            ).sum()
        group["rain_7d_change_vs_previous_7d_mm"] = (
            group["rain_sum_7d_mm"] - group["rain_sum_7d_mm"].shift(7)
        )
        weather_rows.append(group.reset_index(drop=True))
    features = pd.concat(weather_rows, ignore_index=True) if weather_rows else pd.DataFrame()

    # Pivot each observation variable into its own columns to avoid duplicate station/date rows.
    kind_tables = []
    for (station_id, raw_kind), group in obs.groupby(["station_id", "kind"], sort=False):
        if raw_kind not in KIND_PREFIX:
            continue
        prefix, suffix = KIND_PREFIX[raw_kind]
        group = group.sort_values("observed_at").copy()
        group["date"] = group["date"].astype(str)
        daily = group.groupby("date", as_index=False).agg(
            value_last=("value", "last"),
            value_max=("value", "max"),
            value_min=("value", "min"),
            observation_count=("value", "count"),
        ).sort_values("date")
        dates = pd.to_datetime(daily["date"], errors="coerce")
        daily = daily.loc[dates.notna()].copy()
        daily["date_dt"] = pd.to_datetime(daily["date"])
        daily = daily.set_index("date_dt").sort_index()
        complete = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
        daily = daily.reindex(complete)
        daily.index.name = "date_dt"
        daily["station_id"] = str(station_id)
        daily["date"] = daily.index.strftime("%Y-%m-%d")
        daily[f"{prefix}_last_{suffix}"] = daily["value_last"]
        daily[f"{prefix}_max_{suffix}"] = daily["value_max"]
        daily[f"{prefix}_min_{suffix}"] = daily["value_min"]
        daily[f"{prefix}_daily_change_{suffix}"] = daily["value_last"].diff()
        daily[f"{prefix}_change_3d_{suffix}"] = daily["value_last"].diff(3)
        daily[f"{prefix}_change_7d_{suffix}"] = daily["value_last"].diff(7)
        daily[f"{prefix}_7d_max_{suffix}"] = daily["value_max"].rolling(7, min_periods=7).max()
        cols = ["station_id", "date", "observation_count"] + [
            c for c in daily.columns if c.startswith(prefix + "_")
        ]
        kind_tables.append(daily.reset_index(drop=True)[cols])
    if features.empty:
        raise SystemExit("No valid weather rows were available to build feature data.")
    result = features.copy()
    for table in kind_tables:
        # A gauge may have several distinct variables in a day; each is a separate column family.
        duplicates = result.duplicated(["station_id", "date"]).any()
        if duplicates:
            raise SystemExit("Weather input has duplicate station/date rows; resolve upstream first.")
        result = result.merge(table, on=["station_id", "date"], how="left", suffixes=("", "_obs"))
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
        "observation_unit_counts": {
            str(kind): {str(unit): int(count) for unit, count in units.items()}
            for kind, units in obs.groupby("kind")["unit"].value_counts().groupby(level=0)
        },
        "source_urls": sorted(obs["source_url"].dropna().astype(str).unique().tolist()),
        "source_timezones": sorted(obs["source_timezone"].dropna().astype(str).unique().tolist()),
        "missingness_policy": "No missing observations are zero-filled; rolling rainfall totals require complete consecutive calendar windows.",
        "interpretation": "Lagged relationships show temporal association, not proof of causality or flood probability. Verified event labels and independent evaluation are required.",
    }
    args.out.with_suffix(args.out.suffix + ".manifest.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
