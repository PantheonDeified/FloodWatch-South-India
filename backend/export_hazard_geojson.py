"""Export DEM-derived wetness screening indices to Leaflet GeoJSON.

Example:
  python backend/export_hazard_geojson.py --dem /path/to/real_dem.tif

If --rainfall-24h-mm is omitted, the script fetches the last 24 completed hours
from Open-Meteo at the projected DEM tile centre. No synthetic terrain or rain
fallback is used. The GeoJSON contains a terrain/rainfall screening index, not a
calibrated flood or inundation probability.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject, transform as warp_transform

try:
    from dem_hydrology_engine import DEMHydrologyEngine
except ImportError:  # Running as a package/module from the repository root.
    from backend.dem_hydrology_engine import DEMHydrologyEngine


def local_utm_crs(longitude: float, latitude: float) -> CRS:
    """Choose the local UTM zone for metric slope/area calculations."""
    if not (-180 <= longitude <= 180 and -80 <= latitude <= 84):
        raise ValueError("DEM centre is outside the normal UTM latitude/longitude domain.")
    zone = max(1, min(60, int(math.floor((longitude + 180.0) / 6.0)) + 1))
    epsg = (32600 if latitude >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def load_dem_projected(
    dem_path: str | Path,
    *,
    cell_size_meters: float = 30.0,
    max_cells: int = 1_000_000,
):
    """Read a georeferenced DEM and reproject to a local UTM grid in metres."""
    path = Path(dem_path)
    if not path.is_file():
        raise FileNotFoundError(f"DEM file does not exist: {path}")
    if cell_size_meters <= 0 or not math.isfinite(cell_size_meters):
        raise ValueError("cell_size_meters must be positive and finite.")
    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError("DEM has no CRS/projection. Provide a georeferenced GeoTIFF.")
        if src.count < 1 or src.width < 3 or src.height < 3:
            raise ValueError("DEM needs at least one band and a grid of 3 by 3 cells.")
        x_center, y_center = src.xy(src.height // 2, src.width // 2)
        lon_list, lat_list = warp_transform(src.crs, "EPSG:4326", [x_center], [y_center])
        longitude, latitude = float(lon_list[0]), float(lat_list[0])
        target_crs = local_utm_crs(longitude, latitude)
        destination_transform, width, height = calculate_default_transform(
            src.crs, target_crs, src.width, src.height, *src.bounds,
            resolution=cell_size_meters,
        )
        cell_count = int(width) * int(height)
        if cell_count > max_cells:
            raise ValueError(
                f"Projected DEM has {cell_count:,} cells, above --max-cells={max_cells:,}. "
                "Clip the input to a smaller basin/area or deliberately raise the limit."
            )
        if width < 3 or height < 3:
            raise ValueError("Projected DEM is too small at the selected resolution.")
        source = src.read(1, masked=True).astype(np.float32)
        source_data = np.asarray(source.filled(np.nan), dtype=np.float32)
        destination = np.full((height, width), np.nan, dtype=np.float32)
        reproject(
            source=source_data,
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=np.nan,
            dst_transform=destination_transform,
            dst_crs=target_crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
            init_dest_nodata=True,
        )
        valid = np.isfinite(destination)
        if int(valid.sum()) < 9:
            raise ValueError("DEM has too few valid elevation cells after reprojection.")
        dx = math.hypot(destination_transform.a, destination_transform.d)
        dy = math.hypot(destination_transform.b, destination_transform.e)
        if dx <= 0 or dy <= 0:
            raise ValueError("Could not establish projected DEM cell dimensions.")
        return destination.astype(np.float64), valid, destination_transform, target_crs, dx, dy


def fetch_open_meteo_precipitation24h(
    latitude: float,
    longitude: float,
    *,
    timeout_seconds: float = 15.0,
) -> float:
    """Fetch a modelled rainfall estimate from the last 24 completed UTC hours."""
    query = urlencode({
        "latitude": f"{latitude:.6f}",
        "longitude": f"{longitude:.6f}",
        "hourly": "precipitation",
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "UTC",
    })
    url = "https://api.open-meteo.com/v1/forecast?" + query
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "FloodWatch-South-India/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Open-Meteo returned HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    hourly = payload.get("hourly") or {}
    times, rain = hourly.get("time"), hourly.get("precipitation")
    if not isinstance(times, list) or not isinstance(rain, list) or len(times) != len(rain):
        raise RuntimeError("Open-Meteo response has no aligned hourly precipitation series.")
    now = datetime.now(timezone.utc)
    end = now.replace(minute=0, second=0, microsecond=0)
    start = end.timestamp() - 24 * 3600
    end_stamp = end.timestamp()
    count = 0
    total = 0.0
    for time_value, rain_value in zip(times, rain):
        if not isinstance(time_value, str):
            continue
        try:
            parsed = datetime.fromisoformat(time_value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            stamp = parsed.astimezone(timezone.utc).timestamp()
        except ValueError:
            continue
        if not (start < stamp <= end_stamp):
            continue
        if isinstance(rain_value, bool) or not isinstance(rain_value, (int, float)):
            continue
        if not math.isfinite(float(rain_value)) or float(rain_value) < 0:
            continue
        total += float(rain_value)
        count += 1
    if count < 22:
        raise RuntimeError(
            f"Open-Meteo supplied only {count} valid values for the last 24 completed hours; refusing to invent rainfall."
        )
    return round(total, 1)


def write_float_raster(
    path: str | Path,
    array: np.ndarray,
    *,
    transform,
    crs: CRS,
    valid_mask: np.ndarray,
    description: str,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nodata = -9999.0
    values = np.asarray(array, dtype=np.float32).copy()
    values[~valid_mask | ~np.isfinite(values)] = nodata
    profile = {
        "driver": "GTiff",
        "height": values.shape[0],
        "width": values.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
        "compress": "deflate",
        "predictor": 3,
    }
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(values, 1)
        dst.set_band_description(1, description)
        dst.update_tags(
            product="FloodWatch DEM-derived experimental terrain screening",
            note="Not a calibrated flood probability or official warning.",
        )


def _risk_tier(value: float) -> str:
    if value >= 0.75:
        return "CRITICAL_INDEX"
    if value >= 0.55:
        return "HIGH_INDEX"
    if value >= 0.25:
        return "MODERATE_INDEX"
    return "LOW_INDEX"


def export_hazard_raster_to_geojson(
    hazard_grid: np.ndarray,
    *,
    affine_transform,
    source_crs: CRS,
    output_filename: str | Path,
    twi_grid: np.ndarray | None = None,
    slope_radians: np.ndarray | None = None,
    flow_accumulation: np.ndarray | None = None,
    rainfall_24h_mm: float,
    rainfall_source: str,
    dem_source: str,
    min_index: float = 0.25,
    max_features: int = 25_000,
) -> int:
    """Export georeferenced cell polygons with safe feature-count limiting."""
    hazard = np.asarray(hazard_grid, dtype=np.float64)
    if hazard.ndim != 2:
        raise ValueError("hazard_grid must be a 2-D array.")
    if not 0 <= min_index <= 1:
        raise ValueError("min_index must be between 0 and 1.")
    if max_features < 1:
        raise ValueError("max_features must be positive.")
    valid = np.isfinite(hazard) & (hazard >= min_index)
    candidate_cells = np.argwhere(valid)
    if candidate_cells.shape[0] > max_features:
        # Evenly sample the row-major candidate list, keeping the layer bounded
        # for Leaflet rather than silently publishing a multi-megabyte feature list.
        keep = np.linspace(0, candidate_cells.shape[0] - 1, max_features, dtype=np.int64)
        candidate_cells = candidate_cells[keep]

    rows = candidate_cells[:, 0] if len(candidate_cells) else np.array([], dtype=int)
    cols = candidate_cells[:, 1] if len(candidate_cells) else np.array([], dtype=int)
    cols5 = np.column_stack((cols, cols + 1, cols + 1, cols, cols))
    rows5 = np.column_stack((rows, rows, rows + 1, rows + 1, rows))
    xs = affine_transform.c + cols5 * affine_transform.a + rows5 * affine_transform.b
    ys = affine_transform.f + cols5 * affine_transform.d + rows5 * affine_transform.e
    if len(candidate_cells):
        lons, lats = warp_transform(
            source_crs, CRS.from_epsg(4326), xs.ravel().tolist(), ys.ravel().tolist()
        )
    else:
        lons, lats = [], []

    features = []
    for i, (r, c) in enumerate(candidate_cells):
        value = float(hazard[r, c])
        coords = [
            [round(float(lons[i * 5 + j]), 6), round(float(lats[i * 5 + j]), 6)]
            for j in range(5)
        ]
        props = {
            "hazard_index": round(value, 4),
            "index_percent": int(round(value * 100)),
            "risk_tier": _risk_tier(value),
            "twi": round(float(twi_grid[r, c]), 4) if twi_grid is not None and np.isfinite(twi_grid[r, c]) else None,
            "slope_degrees": round(float(math.degrees(slope_radians[r, c])), 3)
                if slope_radians is not None and np.isfinite(slope_radians[r, c]) else None,
            "flow_accumulation_cells": int(round(float(flow_accumulation[r, c])))
                if flow_accumulation is not None and np.isfinite(flow_accumulation[r, c]) else None,
            "rainfall_24h_mm": round(float(rainfall_24h_mm), 1),
            "index_label": "experimental terrain/rainfall screening index; not inundation probability",
        }
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        })

    metadata = {
        "product": "FloodWatch DEM hydrological terrain screening index",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dem_source": Path(dem_source).name,
        "source_crs": str(source_crs),
        "display_crs": "EPSG:4326",
        "rainfall_24h_mm": round(float(rainfall_24h_mm), 1),
        "rainfall_source": rainfall_source,
        "min_index_shown": min_index,
        "features_exported": len(features),
        "candidate_cells_above_threshold": int(valid.sum()),
        "feature_limit": max_features,
        "note": (
            "This is a terrain-relative index scaled by one rainfall estimate. It is not a calibrated "
            "inundation probability, hydraulic flood extent, forecast, or official warning. "
            "It does not simulate river channel routing, water depth, structures, drainage capacity, "
            "or floodplain boundary conditions. Transparent/unmapped areas mean unknown, not safe."
        ),
    }
    geojson_data = {
        "type": "FeatureCollection",
        "name": "FloodWatch DEM terrain/rainfall screening index",
        "metadata": metadata,
        "features": features,
    }
    output_path = Path(output_filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_suffix(output_path.suffix + ".tmp")
    temp.write_text(json.dumps(geojson_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(output_path)
    return len(features)


def run_pipeline(
    dem_path: str | Path,
    output_geojson: str | Path,
    *,
    rainfall_24h_mm: float | None = None,
    cell_size_meters: float = 30.0,
    max_cells: int = 1_000_000,
    min_index: float = 0.25,
    max_features: int = 25_000,
    diagnostics_dir: str | Path = "backend/output/dem",
) -> dict:
    dem, valid, affine, crs, dx, dy = load_dem_projected(
        dem_path, cell_size_meters=cell_size_meters, max_cells=max_cells
    )
    engine = DEMHydrologyEngine(
        dem, cell_size_meters=cell_size_meters, dx_meters=dx, dy_meters=dy, valid_mask=valid
    )
    conditioned = engine.condition_dem()
    slope = engine.calculate_slope()
    accumulation = engine.flow_accumulation()
    area = engine.specific_catchment_area()
    twi = engine.compute_twi()

    if rainfall_24h_mm is None:
        centre_x = affine.c + (dem.shape[1] / 2) * affine.a + (dem.shape[0] / 2) * affine.b
        centre_y = affine.f + (dem.shape[1] / 2) * affine.d + (dem.shape[0] / 2) * affine.e
        lon, lat = warp_transform(crs, CRS.from_epsg(4326), [centre_x], [centre_y])
        rainfall_24h_mm = fetch_open_meteo_precipitation24h(float(lat[0]), float(lon[0]))
        rainfall_source = "Open-Meteo hourly precipitation model estimate at DEM tile centre"
    else:
        rainfall_source = "user-supplied 24-hour rainfall input"
    if not math.isfinite(float(rainfall_24h_mm)) or float(rainfall_24h_mm) < 0:
        raise ValueError("24-hour rainfall must be a finite, non-negative number.")
    hazard = engine.generate_hazard_grid(twi, float(rainfall_24h_mm))

    diag = Path(diagnostics_dir)
    write_float_raster(diag / "conditioned_dem.tif", conditioned, transform=affine, crs=crs, valid_mask=valid, description="Pit-filled DEM elevation in metres")
    write_float_raster(diag / "slope_radians.tif", slope, transform=affine, crs=crs, valid_mask=valid, description="Terrain slope angle in radians")
    write_float_raster(diag / "flow_accumulation_cells.tif", accumulation, transform=affine, crs=crs, valid_mask=valid, description="D8 contributing cell count including current cell")
    write_float_raster(diag / "specific_catchment_area_m.tif", area, transform=affine, crs=crs, valid_mask=valid, description="Approximate specific contributing area in metres")
    write_float_raster(diag / "twi.tif", twi, transform=affine, crs=crs, valid_mask=valid, description="Topographic Wetness Index ln(SCA/tan(slope))")
    write_float_raster(diag / "hazard_index.tif", hazard, transform=affine, crs=crs, valid_mask=valid, description="Experimental terrain/rainfall screening index 0..1")

    features = export_hazard_raster_to_geojson(
        hazard,
        affine_transform=affine,
        source_crs=crs,
        output_filename=output_geojson,
        twi_grid=twi,
        slope_radians=slope,
        flow_accumulation=accumulation,
        rainfall_24h_mm=float(rainfall_24h_mm),
        rainfall_source=rainfall_source,
        dem_source=str(dem_path),
        min_index=min_index,
        max_features=max_features,
    )
    return {
        "status": "completed",
        "dem_source": str(dem_path),
        "projected_crs": str(crs),
        "shape": list(dem.shape),
        "valid_cells": int(valid.sum()),
        "cell_size_m": {"x": dx, "y": dy},
        "rainfall_24h_mm": round(float(rainfall_24h_mm), 1),
        "rainfall_source": rainfall_source,
        "geojson_output": str(output_geojson),
        "geojson_features": features,
        "diagnostics_dir": str(diag),
        "interpretation": "Experimental screening index, not inundation probability.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", required=True, help="Path to a real, georeferenced DEM GeoTIFF (for example SRTM/Copernicus DEM).")
    parser.add_argument("--output", default="data/dem-inundation-zones.geojson", help="Leaflet GeoJSON output path.")
    parser.add_argument("--rainfall-24h-mm", type=float, default=None, help="Optional verified/user-supplied 24-hour rainfall; otherwise fetch Open-Meteo.")
    parser.add_argument("--cell-size-meters", type=float, default=30.0, help="Projected DEM output resolution in metres (default 30).")
    parser.add_argument("--max-cells", type=int, default=1_000_000, help="Maximum projected grid cells for priority-flood/D8 processing.")
    parser.add_argument("--min-index", type=float, default=0.25, help="Minimum terrain/rainfall index to export (0..1).")
    parser.add_argument("--max-features", type=int, default=25_000, help="Feature cap for browser-friendly GeoJSON.")
    parser.add_argument("--diagnostics-dir", default="backend/output/dem", help="Directory for conditioned DEM/slope/flow/TWI/index GeoTIFFs.")
    args = parser.parse_args()
    try:
        result = run_pipeline(
            args.dem,
            args.output,
            rainfall_24h_mm=args.rainfall_24h_mm,
            cell_size_meters=args.cell_size_meters,
            max_cells=args.max_cells,
            min_index=args.min_index,
            max_features=args.max_features,
            diagnostics_dir=args.diagnostics_dir,
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc), "note": "No fallback/synthetic hazard layer was generated."}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
