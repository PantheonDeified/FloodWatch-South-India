#!/usr/bin/env python3
"""Build a regional, low-resolution relative TWI raster from public Terrarium tiles.

This produces a broad regional terrain-context layer, not a calibrated flood
probability, simulated inundation extent, water depth, or operational warning.
The source state polygons are approximate display masks, not legal boundaries.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
import sys
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds, from_origin
from rasterio.warp import Resampling, reproject, transform_geom

from dem_hydrology_engine import DEMHydrologyEngine
from export_hazard_geojson import load_dem_projected, write_float_raster


WEB_MERCATOR_HALF = 20037508.342789244
TILE_SIZE = 256
TERRAIN_BASE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
CORE_STATES = {"Andhra Pradesh", "Karnataka", "Kerala", "Tamil Nadu", "Telangana"}
DEFAULT_BOUNDS = {"west": 73.5, "south": 7.5, "east": 86.5, "north": 21.5}
PALETTE = (
    (0.0, (46, 196, 182)),    # lower relative TWI, teal
    (0.25, (252, 191, 73)),  # moderate relative TWI, amber
    (0.55, (247, 127, 0)),   # high relative TWI, orange
    (0.75, (217, 4, 41)),    # very high relative TWI, red
)


def lon_to_tile_x(longitude: float, zoom: int) -> float:
    return (longitude + 180.0) / 360.0 * (2 ** zoom)


def lat_to_tile_y(latitude: float, zoom: int) -> float:
    latitude = max(-85.05112878, min(85.05112878, latitude))
    lat_radians = math.radians(latitude)
    return (1.0 - math.asinh(math.tan(lat_radians)) / math.pi) / 2.0 * (2 ** zoom)


def decode_terrarium_rgba(rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Decode Mapzen/Tilezen Terrarium RGB heights in metres and a validity mask."""
    pixels = np.asarray(rgba)
    if pixels.ndim != 3 or pixels.shape[-1] < 3:
        raise ValueError("Terrarium tile must be an RGB or RGBA array.")
    rgb = pixels[..., :3].astype(np.float64)
    elevation = rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0
    valid = np.isfinite(elevation)
    if pixels.shape[-1] >= 4:
        valid &= pixels[..., 3] > 0
    return elevation.astype(np.float32), valid


def fetch_tile(zoom: int, x: int, y: int, timeout: float = 30.0) -> tuple[int, int, np.ndarray]:
    url = TERRAIN_BASE_URL.format(z=zoom, x=x, y=y)
    request = Request(url, headers={
        "Accept": "image/png",
        "User-Agent": "FloodWatch-South-India/1.0 (regional terrain screening; open data attribution in repository)",
    })
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Terrain tile returned HTTP {response.status}: z={zoom}/{x}/{y}")
                body = response.read()
            image = Image.open(BytesIO(body)).convert("RGBA")
            if image.size != (TILE_SIZE, TILE_SIZE):
                raise ValueError(f"Terrain tile has unexpected size {image.size}: z={zoom}/{x}/{y}")
            return x, y, np.asarray(image)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not download public terrain tile z={zoom}/{x}/{y}: {last_error}") from last_error


def build_mosaic(
    *, bounds: dict[str, float], zoom: int, state_mask_path: str | Path,
    output_dem: str | Path, workers: int = 10,
) -> dict:
    if not (bounds["west"] < bounds["east"] and bounds["south"] < bounds["north"]):
        raise ValueError("DEM bounds must have west<east and south<north.")
    if zoom < 5 or zoom > 10:
        raise ValueError("Zoom must be between 5 and 10 for this whole-region workflow.")

    n = 2 ** zoom
    x0 = max(0, int(math.floor(lon_to_tile_x(bounds["west"], zoom))))
    x1 = min(n - 1, int(math.floor(lon_to_tile_x(bounds["east"] - 1e-9, zoom))))
    y0 = max(0, int(math.floor(lat_to_tile_y(bounds["north"], zoom))))
    y1 = min(n - 1, int(math.floor(lat_to_tile_y(bounds["south"] + 1e-9, zoom))))
    tile_cols, tile_rows = x1 - x0 + 1, y1 - y0 + 1
    if tile_cols <= 0 or tile_rows <= 0:
        raise ValueError("Region produced an empty terrain-tile range.")
    height, width = tile_rows * TILE_SIZE, tile_cols * TILE_SIZE
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    total_tiles = tile_cols * tile_rows
    print(f"Downloading {total_tiles} authentic public Terrarium tiles at zoom {zoom}…", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, min(16, int(workers)))) as pool:
        futures = [
            pool.submit(fetch_tile, zoom, x, y)
            for y in range(y0, y1 + 1)
            for x in range(x0, x1 + 1)
        ]
        complete = 0
        for future in as_completed(futures):
            x, y, tile = future.result()
            col, row = x - x0, y - y0
            rgba[row*TILE_SIZE:(row+1)*TILE_SIZE, col*TILE_SIZE:(col+1)*TILE_SIZE] = tile
            complete += 1
            if complete % 20 == 0 or complete == total_tiles:
                print(f"Downloaded {complete}/{total_tiles} terrain tiles", flush=True)

    elevation, valid = decode_terrarium_rgba(rgba)
    del rgba
    world_span = 2.0 * WEB_MERCATOR_HALF
    pixel_size = world_span / (n * TILE_SIZE)
    transform = from_origin(
        -WEB_MERCATOR_HALF + x0 * TILE_SIZE * pixel_size,
        WEB_MERCATOR_HALF - y0 * TILE_SIZE * pixel_size,
        pixel_size,
        pixel_size,
    )

    state_json = json.loads(Path(state_mask_path).read_text(encoding="utf-8"))
    geometries = []
    for feature in state_json.get("features", []):
        name = (feature.get("properties") or {}).get("name")
        geometry = feature.get("geometry")
        if name in CORE_STATES and geometry:
            geometries.append(transform_geom("EPSG:4326", "EPSG:3857", geometry, precision=6))
    present = {
        (f.get("properties") or {}).get("name")
        for f in state_json.get("features", [])
        if (f.get("properties") or {}).get("name") in CORE_STATES and f.get("geometry")
    }
    missing = CORE_STATES - present
    if missing:
        raise ValueError("State mask file is missing expected core states: " + ", ".join(sorted(missing)))
    land = geometry_mask(
        geometries,
        out_shape=(height, width),
        transform=transform,
        all_touched=True,
        invert=True,
    )
    valid &= land
    elevation[~valid] = -9999.0
    if int(valid.sum()) < 100:
        raise ValueError("Too few valid land elevations after applying the five-state mask.")

    output = Path(output_dem)
    output.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff", "height": height, "width": width, "count": 1,
        "dtype": "float32", "crs": CRS.from_epsg(3857), "transform": transform,
        "nodata": -9999.0, "compress": "deflate", "predictor": 3,
    }
    with rasterio.open(output, "w", **profile) as dst:
        dst.write(elevation, 1)
        dst.set_band_description(1, "Terrarium decoded terrain elevation, metres")
        dst.update_tags(
            source="Mapzen/Tilezen Terrain Tiles public AWS dataset",
            source_url="https://registry.opendata.aws/terrain-tiles/",
            zoom=zoom,
            land_mask="five-state project GeoJSON approximation; not legal boundary",
            note="Generalized DEM sampling for regional terrain context only.",
        )
    return {
        "dem_path": str(output), "tile_zoom": zoom, "tile_count": total_tiles,
        "shape": [height, width], "valid_land_source_pixels": int(valid.sum()),
        "pixel_size_source_m": pixel_size,
        "land_mask_states": sorted(CORE_STATES),
    }


def colorize_relative_twi(values: np.ndarray, *, low: float, high: float, nodata: float = -9999.0) -> np.ndarray:
    """Return transparent RGBA classes of TWI relative to its regional 5th–95th percentiles."""
    grid = np.asarray(values, dtype=np.float32)
    valid = np.isfinite(grid) & (grid != nodata) & (grid > -9000.0)
    rgba = np.zeros((*grid.shape, 4), dtype=np.uint8)
    if not valid.any():
        raise ValueError("Reprojected TWI has no valid cells to render.")
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        raise ValueError("TWI percentile range must be finite with high>low.")
    norm = np.zeros(grid.shape, dtype=np.float32)
    norm[valid] = np.clip((grid[valid] - low) / (high - low), 0.0, 1.0)
    # Interpolate the palette smoothly; the legend presents convenient break bands.
    stops = np.array([0.0, 0.25, 0.55, 0.75, 1.0], dtype=np.float32)
    colors = np.array([
        [46, 196, 182], [252, 191, 73], [247, 127, 0],
        [217, 4, 41], [217, 4, 41],
    ], dtype=np.float32)
    for channel in range(3):
        rgba[..., channel] = np.interp(norm, stops, colors[:, channel]).astype(np.uint8)
    rgba[valid, 3] = 205
    rgba[~valid] = 0
    return rgba


def render_regional_twi(
    twi_path: str | Path, output_png: str | Path, *,
    bounds: dict[str, float], width: int = 867, height: int = 934,
) -> dict:
    """Warp the analysed TWI raster to WGS84 bounds and write a whole-region RGBA overlay."""
    dest_transform = from_bounds(
        bounds["west"], bounds["south"], bounds["east"], bounds["north"], width, height
    )
    destination = np.full((height, width), -9999.0, dtype=np.float32)
    with rasterio.open(twi_path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=dest_transform,
            dst_crs=CRS.from_epsg(4326),
            dst_nodata=-9999.0,
            resampling=Resampling.bilinear,
            num_threads=2,
        )
    valid = np.isfinite(destination) & (destination > -9000.0) & (destination != -9999.0)
    if int(valid.sum()) < 100:
        raise ValueError("Too few valid TWI cells after reprojection to the South India map extent.")
    low, high = (float(x) for x in np.percentile(destination[valid], [5, 95]))
    rgba = colorize_relative_twi(destination, low=low, high=high)
    png = Path(output_png)
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(png, optimize=True)
    return {
        "image_size_px": [width, height],
        "valid_land_pixels": int(valid.sum()),
        "twi_p05": round(low, 4),
        "twi_p95": round(high, 4),
        "image_bounds_wgs84": bounds,
        "png_size_bytes": png.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-mask", default="data/south-india-states.geojson")
    parser.add_argument("--output-dem", default="/tmp/floodwatch-dem/south-india-dem.tif")
    parser.add_argument("--output-png", default="data/dem-terrain-screening.png")
    parser.add_argument("--output-metadata", default="data/dem-terrain-screening.json")
    parser.add_argument("--diagnostics-dir", default="/tmp/floodwatch-dem/diagnostics")
    parser.add_argument("--zoom", type=int, default=8)
    parser.add_argument("--cell-size-meters", type=float, default=2000.0,
                        help="Regional analysis resolution. 2 km default is intentionally generalized.")
    parser.add_argument("--max-cells", type=int, default=1_250_000)
    parser.add_argument("--tile-workers", type=int, default=10)
    args = parser.parse_args()

    try:
        output_dem = Path(args.output_dem)
        output_dem.parent.mkdir(parents=True, exist_ok=True)
        mosaic_info = build_mosaic(
            bounds=DEFAULT_BOUNDS, zoom=args.zoom, state_mask_path=args.state_mask,
            output_dem=output_dem, workers=args.tile_workers,
        )
        dem, valid, affine, crs, dx, dy = load_dem_projected(
            output_dem,
            cell_size_meters=args.cell_size_meters,
            max_cells=args.max_cells,
        )
        engine = DEMHydrologyEngine(
            dem, cell_size_meters=args.cell_size_meters,
            dx_meters=dx, dy_meters=dy, valid_mask=valid,
        )
        conditioned = engine.condition_dem()
        slope = engine.calculate_slope()
        accumulation = engine.flow_accumulation()
        area = engine.specific_catchment_area()
        twi = engine.compute_twi()

        diagnostics = Path(args.diagnostics_dir)
        write_float_raster(diagnostics / "conditioned_dem.tif", conditioned, transform=affine, crs=crs, valid_mask=valid, description="Priority-flood conditioned elevation, metres")
        write_float_raster(diagnostics / "slope_radians.tif", slope, transform=affine, crs=crs, valid_mask=valid, description="Slope angle in radians")
        write_float_raster(diagnostics / "flow_accumulation_cells.tif", accumulation, transform=affine, crs=crs, valid_mask=valid, description="Approximate D8 contributing cell count")
        write_float_raster(diagnostics / "specific_catchment_area_m.tif", area, transform=affine, crs=crs, valid_mask=valid, description="Approximate D8 specific catchment area, metres")
        twi_path = diagnostics / "twi.tif"
        write_float_raster(twi_path, twi, transform=affine, crs=crs, valid_mask=valid, description="Topographic Wetness Index ln(SCA/tan(slope))")
        terrain_info = render_regional_twi(twi_path, args.output_png, bounds=DEFAULT_BOUNDS)

        metadata = {
            "schema_version": 1,
            "product": "FloodWatch regional relative topographic wetness index",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "Mapzen/Tilezen Terrain Tiles, public AWS dataset",
            "source_url": "https://registry.opendata.aws/terrain-tiles/",
            "source_attribution": "Mapzen/Tilezen Terrain Tiles; follow the dataset attribution terms at https://github.com/tilezen/joerd/blob/master/docs/attribution.md. Underlying terrain source/resolution can vary by tile.",
            "tile_format": "Terrarium RGB elevation, decoded in metres",
            "tile_zoom": args.zoom,
            "analysis_cell_size_meters": args.cell_size_meters,
            "analysis_crs": str(crs),
            "coverage_states": sorted(CORE_STATES),
            "state_mask_source": "data/south-india-states.geojson; approximate map mask, not legal boundary",
            "bounds_wgs84": DEFAULT_BOUNDS,
            "twi_normalization": "Regional 5th–95th percentile of analysed TWI; relative classes, not probability.",
            "twi_p05": terrain_info["twi_p05"],
            "twi_p95": terrain_info["twi_p95"],
            "rainfall_applied_to_base_layer": False,
            "image_file": Path(args.output_png).name,
            "image_size_px": terrain_info["image_size_px"],
            "valid_land_pixels": terrain_info["valid_land_pixels"],
            "note": (
                "Regional overview, derived from authentic public terrain tiles and a generalized 2 km analysis grid. "
                "Colours show relative terrain wetness (TWI), not live rainfall, calibrated flood probability, "
                "river overflow, inundation depth/extent, or an official warning. Low index does not mean safe. "
                "Fine-scale drains, buildings, channels, hydraulic conditions and local catchment boundaries are not resolved. "
                "Live rain/river context is shown in separate FloodWatch layers."
            ),
            "generator": "backend/build_regional_dem_overlay.py",
        }
        metadata_path = Path(args.output_metadata)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report = {
            "status": "completed",
            "mosaic": mosaic_info,
            "analysis_shape": list(dem.shape),
            "analysis_valid_cells": int(valid.sum()),
            "analysis_cell_size_meters": {"x": dx, "y": dy},
            "twi": terrain_info,
            "output_png": args.output_png,
            "output_metadata": args.output_metadata,
            "diagnostics_dir": str(diagnostics),
            "interpretation": metadata["note"],
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error": str(exc),
            "note": "No synthetic or guessed elevation layer was produced.",
        }, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
