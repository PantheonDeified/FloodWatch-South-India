#!/usr/bin/env python3
"""Assign verified stations/sites to HydroBASINS polygons and find upstream candidates."""
from __future__ import annotations
import argparse
import json
import pathlib
import sys

import geopandas as gpd
import pandas as pd


def field_name(columns, candidates):
    lookup = {str(c).strip().upper(): c for c in columns}
    for candidate in candidates:
        if candidate.upper() in lookup:
            return lookup[candidate.upper()]
    return None


def verified_rows(path: pathlib.Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"station_id": str})
    required = {"station_id", "latitude", "longitude"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Gauge CSV must contain {sorted(required)}")
    verified = frame.get("coordinate_verified", pd.Series("", index=frame.index)).astype(str).str.lower().isin(
        ["1", "true", "yes", "verified"]
    )
    has_source = frame.get("coordinate_source_url", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip().ne("")
    frame = frame.loc[verified & has_source].copy()
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    frame = frame.dropna(subset=["latitude", "longitude"])
    return frame


def basin_index(basins: gpd.GeoDataFrame):
    id_col = field_name(basins.columns, ["HYBAS_ID", "BASIN_ID", "SUBBASIN_ID"])
    down_col = field_name(basins.columns, ["NEXT_DOWN", "NEXTDOWN", "DOWNSTREAM_ID"])
    if not id_col or not down_col:
        raise ValueError("Basin layer must have HYBAS_ID and NEXT_DOWN (or equivalent) fields.")
    lookup = {}
    for _, row in basins.iterrows():
        try:
            bid = int(row[id_col])
            nxt = int(row[down_col]) if pd.notna(row[down_col]) else 0
        except (TypeError, ValueError, OverflowError):
            continue
        lookup[bid] = nxt
    return id_col, down_col, lookup


def locate_points(frame: pd.DataFrame, id_col: str, label_col: str,
                  basin_layer: gpd.GeoDataFrame) -> pd.DataFrame:
    points = gpd.GeoDataFrame(
        frame.copy(),
        geometry=gpd.points_from_xy(frame["longitude"], frame["latitude"]),
        crs="EPSG:4326",
    ).to_crs(basin_layer.crs)
    joined = gpd.sjoin(
        points,
        basin_layer[[id_col, "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined.drop(columns=["index_right", "geometry"], errors="ignore")
    joined = joined.rename(columns={id_col: "hybas_id"})
    joined["hybas_id"] = pd.to_numeric(joined["hybas_id"], errors="coerce")
    joined[label_col] = joined[label_col].astype(str)
    return pd.DataFrame(joined.drop(columns=["index_left"], errors="ignore"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gauges", required=True, type=pathlib.Path)
    ap.add_argument("--basins", required=True, type=pathlib.Path)
    ap.add_argument("--targets", type=pathlib.Path, help="Optional CSV with target_id,target_name,latitude,longitude.")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    basin = gpd.read_file(args.basins)
    if basin.crs is None:
        raise SystemExit("Basin layer has no CRS. Assign a verified CRS before mapping.")
    id_col, down_col, downstream = basin_index(basin)

    gauges = verified_rows(args.gauges)
    if gauges.empty:
        raise SystemExit("No verified gauge coordinates. Do not substitute guessed stations.")
    gauges["_label"] = gauges["station_id"].astype(str)
    gauge_map = locate_points(gauges, id_col, "_label", basin)
    station_rows = []
    for _, row in gauge_map.iterrows():
        station_rows.append({
            "record_type": "gauge_assignment",
            "station_id": str(row["station_id"]),
            "station_name": row.get("station_name", ""),
            "river": row.get("river", ""),
            "state": row.get("state", ""),
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "hybas_id": int(row["hybas_id"]) if pd.notna(row["hybas_id"]) else "",
            "relationship": "station falls in mapped sub-basin" if pd.notna(row["hybas_id"]) else "unmapped",
            "basin_steps_downstream": 0 if pd.notna(row["hybas_id"]) else "",
            "candidate_status": "needs river-network and station-metadata verification" if pd.notna(row["hybas_id"]) else "no polygon match",
            "coordinate_source_url": row.get("coordinate_source_url", ""),
        })

    output_rows = list(station_rows)
    if args.targets:
        targets = pd.read_csv(args.targets)
        if not {"target_id", "latitude", "longitude"}.issubset(targets.columns):
            raise SystemExit("Targets CSV must contain target_id, latitude and longitude.")
        targets["_label"] = targets["target_id"].astype(str)
        target_map = locate_points(targets, id_col, "_label", basin)
        valid_gauges = gauge_map[pd.notna(gauge_map["hybas_id"])].copy()
        valid_gauges["hybas_id"] = valid_gauges["hybas_id"].astype(int)
        for _, target in target_map.iterrows():
            if pd.isna(target["hybas_id"]):
                output_rows.append({
                    "record_type": "target_mapping", "target_id": target["target_id"],
                    "hybas_id": "", "relationship": "unmapped",
                    "candidate_status": "target coordinate did not fall inside a basin polygon",
                })
                continue
            target_id = int(target["hybas_id"])
            for _, gauge in valid_gauges.iterrows():
                gauge_id = int(gauge["hybas_id"])
                cursor = gauge_id
                seen = set()
                steps = 0
                found = False
                while cursor and cursor not in seen:
                    if cursor == target_id:
                        found = True
                        break
                    seen.add(cursor)
                    cursor = downstream.get(cursor, 0)
                    steps += 1
                    if steps > 1000:
                        break
                if found:
                    output_rows.append({
                        "record_type": "upstream_gauge_candidate",
                        "target_id": target["target_id"],
                        "target_name": target.get("target_name", ""),
                        "target_hybas_id": target_id,
                        "station_id": str(gauge["station_id"]),
                        "station_name": gauge.get("station_name", ""),
                        "river": gauge.get("river", ""),
                        "state": gauge.get("state", ""),
                        "station_hybas_id": gauge_id,
                        "relationship": "same_subbasin" if gauge_id == target_id else "candidate_upstream_subbasin",
                        "basin_steps_downstream": steps,
                        "candidate_status": "requires manual flowline, named-river, dam/diversion and gauge-direction validation",
                        "coordinate_source_url": gauge.get("coordinate_source_url", ""),
                    })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(output_rows).to_csv(args.out, index=False)
    summary = {
        "gauge_rows_input": len(gauges),
        "gauges_mapped": int(gauge_map["hybas_id"].notna().sum()),
        "gauges_unmapped": int(gauge_map["hybas_id"].isna().sum()),
        "targets_input": 0 if not args.targets else len(pd.read_csv(args.targets)),
        "output": str(args.out),
        "warning": "Basin graph matches are candidates, not verified channel connections or a flood forecast.",
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
