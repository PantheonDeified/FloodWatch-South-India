"""Build a full-region, coarse DEM-derived terrain-wetness overlay from Copernicus GLO-90.

The downloaded DSM tiles are genuine public Copernicus elevation data. This workflow
resamples them to a ~2.2 km geographic grid for the five core South Indian states,
computes depression conditioning, D8 flow accumulation, slope and TWI, and exports
a transparent PNG (full raster coverage) plus a spatially thinned GeoJSON popup layer.
This is terrain wetness context, NOT a flood probability, depth or inundation extent.
"""
from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import struct
import sys
import urllib.error
import urllib.request
import zlib

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import Affine, from_origin
from rasterio.warp import reproject, transform_bounds

try:
    from dem_hydrology_engine import DEMHydrologyEngine
except ImportError:
    from backend.dem_hydrology_engine import DEMHydrologyEngine


WEST, SOUTH, EAST, NORTH = 73.5, 7.5, 86.5, 21.5
GRID_DEGREES = 0.02  # approximately 2.2 km; regional overview, not building-scale
CORE_STATES = {"Andhra Pradesh", "Karnataka", "Kerala", "Tamil Nadu", "Telangana"}
S3_BASE = "https://copernicus-dem-90m.s3.amazonaws.com"
TILE_INDEX_URL = S3_BASE + "/tileList.txt"
TILE_RE = re.compile(r"Copernicus_DSM_COG_30_([NS])(\d{2})_00_([EW])(\d{3})_00_DEM")
SOURCE_ATTRIBUTION = (
    "Produced using Copernicus WorldDEM-90 © DLR e.V. 2010–2014 and "
    "© Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS "
    "by the European Union and ESA; all rights reserved."
)


def _request_bytes(url: str, timeout: int = 45) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "FloodWatch-South-India/1.0 (open regional DEM screening)", "Accept": "*/*"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"HTTP {response.status} from {url}")
        return response.read()


def select_tile_names(tile_index_text: str, bbox=(WEST, SOUTH, EAST, NORTH)) -> list[str]:
    """Select only listed GLO-90 tiles intersecting a requested WGS84 bounding box."""
    west, south, east, north = map(float, bbox)
    found: set[str] = set()
    for match in TILE_RE.finditer(tile_index_text):
        ns, lat_digits, ew, lon_digits = match.groups()
        lat = int(lat_digits) * (1 if ns == "N" else -1)
        lon = int(lon_digits) * (1 if ew == "E" else -1)
        if lon < east and lon + 1 > west and lat < north and lat + 1 > south:
            found.add(match.group(0))
    if not found:
        raise RuntimeError(
            "The Copernicus GLO-90 public tile index had no matching tiles. "
            "No fallback or synthetic terrain will be generated."
        )
    return sorted(found)


def _download_tile(tile_name: str, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{tile_name}.tif"
    if target.exists() and target.stat().st_size > 4096:
        return target
    url = f"{S3_BASE}/{tile_name}/{tile_name}.tif"
    tmp = target.with_suffix(".tif.part")
    request = urllib.request.Request(
        url, headers={"User-Agent": "FloodWatch-South-India/1.0", "Accept": "image/tiff,*/*"}
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response, tmp.open("wb") as out:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"HTTP {response.status} for tile {tile_name}")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        if tmp.stat().st_size <= 4096:
            raise RuntimeError(f"Copernicus tile {tile_name} returned an empty/short file.")
        tmp.replace(target)
        # Verify it is a readable GeoTIFF before using it.
        with rasterio.open(target) as src:
            if src.crs is None or src.count < 1:
                raise RuntimeError(f"Copernicus tile {tile_name} has no usable CRS/band.")
        return target
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def download_tiles(tile_names: list[str], cache_dir: Path, workers: int = 8) -> list[Path]:
    """Download all indexed region tiles; missing/corrupt listed tiles fail closed."""
    paths: dict[str, Path] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        futures = {pool.submit(_download_tile, name, cache_dir): name for name in tile_names}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            paths[name] = future.result()
    return [paths[name] for name in tile_names]


def _grid_window(bounds, transform, height: int, width: int):
    left, bottom, right, top = bounds
    res_x, res_y = transform.a, -transform.e
    c0 = max(0, int(math.floor((left - transform.c) / res_x)))
    c1 = min(width, int(math.ceil((right - transform.c) / res_x)))
    r0 = max(0, int(math.floor((transform.f - top) / res_y)))
    r1 = min(height, int(math.ceil((transform.f - bottom) / res_y)))
    if c1 <= c0 or r1 <= r0:
        return None
    return r0, r1, c0, c1


def mosaic_tiles_to_coarse_grid(
    tile_paths: list[Path],
    *,
    bbox=(WEST, SOUTH, EAST, NORTH),
    resolution_degrees: float = GRID_DEGREES,
) -> tuple[np.ndarray, Affine]:
    """Warp listed source COGs directly into a coarse regular WGS84 grid."""
    west, south, east, north = map(float, bbox)
    if resolution_degrees <= 0 or not math.isfinite(resolution_degrees):
        raise ValueError("resolution_degrees must be positive and finite.")
    width = int(round((east - west) / resolution_degrees))
    height = int(round((north - south) / resolution_degrees))
    if min(width, height) < 3 or width * height > 2_000_000:
        raise ValueError("Regional target grid is outside the configured safe size.")
    transform = from_origin(west, north, resolution_degrees, resolution_degrees)
    dem = np.full((height, width), np.nan, dtype=np.float32)
    for tile_path in tile_paths:
        with rasterio.open(tile_path) as src:
            src_bounds = transform_bounds(src.crs, CRS.from_epsg(4326), *src.bounds, densify_pts=8)
            window = _grid_window(src_bounds, transform, height, width)
            if window is None:
                continue
            r0, r1, c0, c1 = window
            dest = np.full((r1 - r0, c1 - c0), np.nan, dtype=np.float32)
            dst_transform = transform * Affine.translation(c0, r0)
            band = src.read(1, masked=True).astype(np.float32)
            source = np.asarray(band.filled(np.nan), dtype=np.float32)
            reproject(
                source=source,
                destination=dest,
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=np.nan,
                dst_transform=dst_transform,
                dst_crs=CRS.from_epsg(4326),
                dst_nodata=np.nan,
                resampling=Resampling.average,
                init_dest_nodata=True,
            )
            view = dem[r0:r1, c0:c1]
            use = np.isfinite(dest) & ~np.isfinite(view)
            view[use] = dest[use]
    return dem, transform


def build_state_mask(boundary_geojson: dict, transform: Affine, height: int, width: int) -> np.ndarray:
    """Rasterize only the five core South Indian state polygons."""
    shapes = []
    for feature in boundary_geojson.get("features", []):
        props = feature.get("properties") or {}
        name = props.get("name") or props.get("state") or props.get("NAME_1")
        geom = feature.get("geometry")
        if name in CORE_STATES and geom:
            shapes.append((geom, 1))
    missing = CORE_STATES - {
        (f.get("properties") or {}).get("name")
        for f in boundary_geojson.get("features", [])
        if (f.get("properties") or {}).get("name") in CORE_STATES
    }
    if missing:
        raise RuntimeError("State boundary mask is missing: " + ", ".join(sorted(missing)))
    return rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,
        all_touched=False,
        dtype=np.uint8,
    ).astype(bool)


def normalize_twi(twi: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Normalize TWI by the state's valid 5th/95th percentiles; this is not probability."""
    valid = mask & np.isfinite(twi)
    if int(valid.sum()) < 100:
        raise RuntimeError("There are too few valid state-mask TWI cells to build a regional map.")
    low, high = np.percentile(twi[valid], [5, 95])
    result = np.full(twi.shape, np.nan, dtype=np.float32)
    if high > low:
        result[valid] = np.clip((twi[valid] - low) / (high - low), 0.0, 1.0)
    else:
        result[valid] = 0.0
    return result, float(low), float(high)


def color_for_index(value: float) -> tuple[int, int, int, int]:
    """Match the Leaflet layer's established wetness-index palette."""
    if not math.isfinite(value):
        return (0, 0, 0, 0)
    if value >= 0.75:
        return (217, 4, 41, 150)   # red / very high relative TWI
    if value >= 0.55:
        return (247, 127, 0, 125)  # orange / high relative TWI
    if value >= 0.25:
        return (252, 191, 73, 100) # amber / moderate relative TWI
    return (46, 196, 182, 68)      # teal / lower relative TWI, not safety


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data)) + chunk_type + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def encode_rgba_png(rgba: np.ndarray) -> bytes:
    """Encode a uint8 H×W×4 array to a standards-compliant PNG without extra packages."""
    array = np.asarray(rgba)
    if array.ndim != 3 or array.shape[2] != 4 or array.dtype != np.uint8:
        raise ValueError("rgba must be a uint8 array with shape H×W×4.")
    height, width, _ = array.shape
    raw = b"".join(b"\x00" + array[row].tobytes(order="C") for row in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(raw, 6)) + _png_chunk(b"IEND", b"")


def render_index_png(index: np.ndarray, state_mask: np.ndarray, output: str | Path) -> None:
    if index.shape != state_mask.shape:
        raise ValueError("index and state mask shapes must match.")
    rgba = np.zeros((*index.shape, 4), dtype=np.uint8)
    valid_rows, valid_cols = np.nonzero(state_mask & np.isfinite(index))
    for r, c in zip(valid_rows.tolist(), valid_cols.tolist()):
        rgba[r, c] = color_for_index(float(index[r, c]))
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_bytes(encode_rgba_png(rgba))
    tmp.replace(out)


def export_sampled_geojson(
    index: np.ndarray,
    twi: np.ndarray,
    slope: np.ndarray,
    accumulation: np.ndarray,
    state_mask: np.ndarray,
    *,
    transform: Affine,
    output: str | Path,
    tile_count: int,
    valid_state_fraction: float,
    twi_low: float,
    twi_high: float,
    max_features: int = 18000,
    resolution_degrees: float = GRID_DEGREES,
) -> int:
    """Export spatially distributed sample-cell polygons for clickable value popups."""
    candidates = state_mask & np.isfinite(index) & (index >= 0.25)
    count = int(candidates.sum())
    if max_features < 1:
        raise ValueError("max_features must be positive.")
    stride = max(1, int(math.ceil(math.sqrt(max(count, 1) / max_features))))
    rows, cols = np.where(candidates)
    chosen = np.zeros(index.shape, dtype=bool)
    while True:
        chosen[:] = False
        chosen[::stride, ::stride] = True
        chosen &= candidates
        rr, cc = np.where(chosen)
        if len(rr) <= max_features or stride > max(index.shape):
            break
        stride += 1

    features = []
    west, north = transform.c, transform.f
    for r, c in zip(rr.tolist(), cc.tolist()):
        value = float(index[r, c])
        x0, x1 = west + c * resolution_degrees, west + (c + 1) * resolution_degrees
        y1, y0 = north - r * resolution_degrees, north - (r + 1) * resolution_degrees
        features.append({
            "type": "Feature",
            "properties": {
                "hazard_index": round(value, 4),
                "index_percent": int(round(value * 100)),
                "risk_tier": "VERY_HIGH_TWI" if value >= 0.75 else "HIGH_TWI" if value >= 0.55 else "MODERATE_TWI",
                "twi": round(float(twi[r, c]), 4) if np.isfinite(twi[r, c]) else None,
                "slope_degrees": round(float(math.degrees(float(slope[r, c]))), 2) if np.isfinite(slope[r, c]) else None,
                "flow_accumulation_cells": int(round(float(accumulation[r, c]))) if np.isfinite(accumulation[r, c]) else None,
                "index_label": "relative topographic wetness index; not flood probability",
                "grid_resolution_km_approx": round(resolution_degrees * 111.0, 2),
            },
            "geometry": {"type": "Polygon", "coordinates": [[
                [round(x0, 6), round(y0, 6)], [round(x1, 6), round(y0, 6)],
                [round(x1, 6), round(y1, 6)], [round(x0, 6), round(y1, 6)],
                [round(x0, 6), round(y0, 6)],
            ]]},
        })

    metadata = {
        "product": "FloodWatch regional DEM terrain/wetness index",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dem_source": "Copernicus WorldDEM-90 / Copernicus DEM GLO-90 public COG tiles",
        "dem_source_url": "https://registry.opendata.aws/copernicus-dem/",
        "dem_resolution_nominal_m": 90,
        "analysis_grid_resolution_degrees": resolution_degrees,
        "analysis_grid_resolution_km_approx": round(resolution_degrees * 111.0, 2),
        "tile_count": tile_count,
        "bounds": {"west": WEST, "south": SOUTH, "east": EAST, "north": NORTH},
        "state_coverage": sorted(CORE_STATES),
        "state_mask_source": "data/south-india-states.geojson; approximate mask, not official survey boundary",
        "valid_dem_fraction_inside_state_mask": round(valid_state_fraction, 4),
        "twi_normalization_percentiles": {"p05": round(twi_low, 4), "p95": round(twi_high, 4)},
        "features_exported": len(features),
        "candidate_cells_above_index_025": count,
        "feature_sampling_stride_cells": stride,
        "attribution": SOURCE_ATTRIBUTION,
        "note": (
            "Static, relative topographic wetness context from DEM conditioning, slope, D8 flow accumulation "
            "and TWI. It does not include rainfall, river stage, reservoir releases, hydraulic routing or "
            "water depth. Not an inundation extent, calibrated flood probability or official warning. "
            "Raster is resampled to an approximately 2.2 km grid for regional visualization. "
            "Transparent/unmapped areas mean unknown data, not safety."
        ),
    }
    payload = {
        "type": "FeatureCollection",
        "name": "FloodWatch South India DEM terrain/wetness sampling cells",
        "metadata": metadata,
        "features": features,
    }
    dest = Path(output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix(dest.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(dest)
    return len(features)


def build_region(
    boundary_path: str | Path = "data/south-india-states.geojson",
    output_png: str | Path = "data/dem-inundation-zones.png",
    output_geojson: str | Path = "data/dem-inundation-zones.geojson",
    cache_dir: str | Path = "/tmp/floodwatch-copernicus-glo90",
    *,
    resolution_degrees: float = GRID_DEGREES,
    max_features: int = 18000,
) -> dict:
    boundary = json.loads(Path(boundary_path).read_text(encoding="utf-8"))
    with urllib.request.urlopen(TILE_INDEX_URL, timeout=45) as response:
        tile_index_text = response.read().decode("utf-8", errors="replace")
    names = select_tile_names(tile_index_text)
    paths = download_tiles(names, Path(cache_dir))
    dem, transform = mosaic_tiles_to_coarse_grid(paths, resolution_degrees=resolution_degrees)
    height, width = dem.shape
    state_mask = build_state_mask(boundary, transform, height, width)
    valid = np.isfinite(dem)
    denominator = int(state_mask.sum())
    valid_core = state_mask & valid
    coverage = float(valid_core.sum() / denominator) if denominator else 0.0
    if coverage < 0.65:
        raise RuntimeError(
            f"Only {coverage:.1%} of masked state grid cells have DEM values; refusing to publish a mostly empty map."
        )
    mean_lat = (SOUTH + NORTH) / 2.0
    dx = resolution_degrees * 111_320.0 * math.cos(math.radians(mean_lat))
    dy = resolution_degrees * 110_574.0
    engine = DEMHydrologyEngine(
        dem.astype(np.float64),
        cell_size_meters=math.sqrt(dx * dy),
        dx_meters=dx,
        dy_meters=dy,
        valid_mask=valid,
    )
    conditioned = engine.condition_dem()
    slope = engine.calculate_slope()
    accumulation = engine.flow_accumulation()
    twi = engine.compute_twi()
    index, low, high = normalize_twi(twi, valid_core)
    render_index_png(index, state_mask, output_png)
    feature_count = export_sampled_geojson(
        index, twi, slope, accumulation, state_mask,
        transform=transform, output=output_geojson, tile_count=len(paths),
        valid_state_fraction=coverage, twi_low=low, twi_high=high,
        max_features=max_features, resolution_degrees=resolution_degrees,
    )
    return {
        "status": "completed",
        "dem_source": "Copernicus DEM GLO-90",
        "tiles_downloaded": len(paths),
        "grid_shape": [height, width],
        "grid_resolution_degrees": resolution_degrees,
        "approximate_grid_spacing_km": round(resolution_degrees * 111.0, 2),
        "core_state_grid_coverage": round(coverage, 4),
        "png_output": str(output_png),
        "geojson_output": str(output_geojson),
        "sampled_geojson_features": feature_count,
        "conditioned_valid_cells": int(np.isfinite(conditioned).sum()),
        "attribution": SOURCE_ATTRIBUTION,
        "note": "Static DEM-derived wetness context, not flood probability/depth/extent.",
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", default="data/south-india-states.geojson")
    parser.add_argument("--png", default="data/dem-inundation-zones.png")
    parser.add_argument("--geojson", default="data/dem-inundation-zones.geojson")
    parser.add_argument("--cache-dir", default="/tmp/floodwatch-copernicus-glo90")
    parser.add_argument("--resolution-degrees", type=float, default=GRID_DEGREES)
    parser.add_argument("--max-features", type=int, default=18000)
    args = parser.parse_args()
    try:
        report = build_region(
            args.boundary, args.png, args.geojson, args.cache_dir,
            resolution_degrees=args.resolution_degrees, max_features=args.max_features,
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc), "note": "No fabricated terrain output was published."}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
